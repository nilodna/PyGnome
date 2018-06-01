import pdb
import datetime
import zipfile
import six
import io
import collections
import os
import json
import tempfile

from colander import (SchemaNode, deferred, drop, required, Invalid, UnsupportedFields,
                      SequenceSchema, TupleSchema, MappingSchema,
                      String, Float, Int, SchemaType, Sequence, Tuple, Positional, null)

from extend_colander import NumpyFixedLenSchema

from gnome.gnomeobject import GnomeId, Refs, class_from_objtype
from gnome.persist.extend_colander import OrderedCollectionType


@deferred
def now(node, kw):
    """
    Used by TimeseriesValueSchema - assume it defers the calculation of
                                    datetime.datetime.now to when it is called
                                    in Schema
    """
    return datetime.datetime.now().replace(microsecond=0)


class ObjType(SchemaType):

    def __init__(self, unknown='ignore'):
        self.unknown = unknown

    def _set_unknown(self, value):
        if not value in ('ignore', 'raise', 'preserve'):
            raise ValueError(
                'unknown attribute must be one of "ignore", "raise", '
                'or "preserve"')
        self._unknown = value

    def _get_unknown(self):
        return self._unknown

    unknown = property(_get_unknown, _set_unknown)

    def cstruct_children(self, node, cstruct):
        if cstruct is None:
            value = {}
        else:
            value = self._validate(node, cstruct)
        children = []
        for subnode in node.children:
            name = subnode.name
            subval = value.get(name, required)
            if subval is required:
                subval = subnode.serialize(null)
            children.append(subval)
        return children

    def _impl(self, node, value, callback):
        error = None
        result = {}

        for num, subnode in enumerate(node.children):
            name = subnode.name
            subval = None
            if self.unknown == 'ignore':
                subval = value.get(name, None)
            else:
                subval = value.pop(name, None)
            if subval is None: #deserialization
                if subnode.missing == drop:
                    continue
                sub_result = subnode.missing
            elif subval is null: #serialization
                if subnode.default == drop:
                    continue
                sub_result = subnode.default if subnode.default is not null else None
            else:
                sub_result = callback(subnode,subval)
#             try:
#             except Invalid as e:
#                 raise e
#                 if error is None:
#                     error = Invalid(node)
#                 error.add(e, num)
#             else:
            #if sub_result is None:
            #    continue
            result[name] = sub_result

        if self.unknown == 'raise':
            if value:
                raise UnsupportedFields(
                    node, value,
                    msg=_('Unrecognized keys in mapping: "${val}"',
                          mapping={'val': value}))

        elif self.unknown == 'preserve':
            result.update(value)

        if error is not None:
            raise error

        return result

    def _ser(self, node, value):
        try:
            if hasattr(value, 'to_dict'):
                dict_ = value.to_dict('webapi')
                for k in dict_.keys():
                    if dict_[k] is None:
                        dict_[k] = null
                return dict_

            else:
                raise TypeError('Object does not have a to_dict function')
        except Exception as e:
            raise e
            raise Invalid(node, '{0}" does not implement GnomeObj functionality: {1}'.format(value, e))

    def serialize(self, node, appstruct):
#         if appstruct is None:
#             appstruct = None

        def callback(subnode, subappstruct):
            return subnode.serialize(subappstruct)

        value = self._ser(node, appstruct)
        return self._impl(node, value, callback)

    def _deser(self, node, value, refs):
#         try:
            if value is None:
                return None
            if type(value) is dict and 'obj_type' in value:
                id_ = value['id']
                if value['id'] not in refs:
                    obj_type = class_from_objtype(value['obj_type'])
                    refs[id_] = obj_type.new_from_dict(value)
                return refs[id_]
            else:
                raise TypeError('{0} is not dictionary, or does not have an obj_type'.format(value))
#         except Exception as e:
#             raise e
#             raise Invalid(node, '{0}" does not implement GnomeObj functionality: {1}'.format(value, e))

    def deserialize(self, node, cstruct, refs):
        if cstruct is None:
            return None

        def callback(subnode, subcstruct):
            if subnode.typ.__class__ is ObjType:
                return subnode.deserialize(subcstruct, refs)
            else:
                #This needs to become more flexible! It needs to detect subclasses of Sequence!
                if ((subnode.schema_type is Sequence or subnode.schema_type is OrderedCollectionType) and
                    isinstance(subnode.children[0], ObjTypeSchema)):
                    #To deal with iterable schemas that do not have a deserialize with refs function
                    scalar = hasattr(subnode.typ, 'accept_scalar') and subnode.typ.accept_scalar
                    return subnode.typ._impl(subnode, subcstruct, callback, scalar)
                elif (subnode.schema_type is Tuple):
                    return subnode.typ._impl(subnode, subcstruct, callback)
                else:
                    return subnode.deserialize(subcstruct)

        result = self._impl(node, cstruct, callback)
        return self._deser(node, result, refs)

    def _upd(self, node, obj, dict_):
        if hasattr(obj, 'update_from_dict'):
            return obj.update_from_dict(dict_)
        else:
            raise TypeError('{0} does not have an update_from_dict'.format(obj))

    def _update(self, node, appstruct=None, cstruct=None, refs=None):

        def callback(subnode, subcstruct):
            if subnode.typ.__class__ is self.__class__:
                #subnode is schema for a gnome object
                subnode._update(cstruct)
                if ['obj_type'] in subcstruct:
                if subappstruct is not None:
                    if subcstruct is None:
                        #trying to set this to None. return null so this can be detected
                        #by the parent node
                        return null
                    else:
                        subnode._update(subappstruct, subcstruct)
                        return subappstruct
                else:
                    #updating a GnomeID variable that is set to None
                    #Try to create a valid object from the cstruct
                    return subnode.deserialize(subcstruct)

            elif ((subnode.schema_type is Sequence) and
                    isinstance(subnode.children[0], ObjTypeSchema)):
                #subnode is List or OrderedCollection
                scalar = hasattr(subnode.typ, 'accept_scalar') and subnode.typ.accept_scalar
                while(len(subcstruct) < len(subappstruct)):
                    subcstruct.append({})
                rv = subnode.typ._impl(subnode, zip(subappstruct, subcstruct), callback, scalar)
                for i, e in enumerate(rv):
                    if e is null:
                        rv[i] = None
                return rv
            elif (subnode.schema_type is OrderedCollectionType):
                #OrderedCollections ordering can be updated using .update, so they
                #need to be special cased. In essence, treat them as a 'primitive' type
                #and let it handle all the changes internally.
                #return None to cause the parent node to skip this subnode
                subappstruct.update_from_dict(subcstruct)
                return None
            elif (subnode.schema_type is Tuple):
                return subnode.typ._impl(subnode, zip(subappstruct, subcstruct), callback)
            else:
                #Float, String, etc
                return subnode.deserialize(subcstruct)

        result = self._upd_impl(node, cstruct, callback)
        return self._upd(node, appstruct, result)

    def _upd_impl(self, node, cstruct, callback):
        #because update needs to handle 'sparse' dictionaries, it cannot raise
        #errors on nodes that aren't present in the data and do not have
        #missing=drop set
        result = {}

        for num, subnode in enumerate(node.children):
            name = subnode.name
            subcstr = cstruct.get(name, null) #update is where a destructive approach makes most sense
            if subcstr == null: #attr is not present in cstruct dict, so skip
                continue
            elif subcstr == None:
                result[name] = subcstr
            else:
                sub_result = callback(subnode, subcstr)
                result[name] = sub_result

        return result

    def flatten(self, node, appstruct, prefix='', listitem=False):
        result = {}
        if listitem:
            selfprefix = prefix
        else:
            if node.name:
                selfprefix = '%s%s.' % (prefix, node.name)
            else:
                selfprefix = prefix

        for subnode in node.children:
            name = subnode.name
            substruct = appstruct.get(name, None)
            result.update(subnode.typ.flatten(subnode, substruct,
                                              prefix=selfprefix))
        return result

    def unflatten(self, node, paths, fstruct):
        return super(ObjType, self).unflatten(node, paths, fstruct)

    def set_value(self, node, appstruct, path, value):
        if '.' in path:
            next_name, rest = path.split('.', 1)
            next_node = node[next_name]
            next_appstruct = appstruct[next_name]
            appstruct[next_name] = next_node.typ.set_value(
                next_node, next_appstruct, rest, value)
        else:
            appstruct[path] = value
        return appstruct

    def get_value(self, node, appstruct, path):
        if '.' in path:
            name, rest = path.split('.', 1)
            next_node = node[name]
            return next_node.typ.get_value(next_node, appstruct[name], rest)
        return appstruct[path]

    def _prepare_save(self, node, raw_object, saveloc, refs):
        #Gets the json for the object, as if this were being serialized
        obj_json = None
        if hasattr(raw_object, 'to_dict'):
            #Passing the 'save' in case a class wants to do some special stuff on
            #saving specifically.
            dict_ = raw_object.to_dict('save')
            for k in dict_.keys():
                if dict_[k] is None:
                    dict_[k] = null
            return dict_
        else:
            raise TypeError('Object does not have a to_dict function')
        #also adds the object to refs by id
        refs[raw_object.id] = raw_object

        #note you cannot immediately strip out attributes that wont get saved here
        #because they are still needed by _impl
        return obj_json

    def _save(self, node, json_, zipfile_, refs):
        #strips out any entries that do not need saving. They're still in refs,
        #but that shouldn't do any harm.
        savable_attrs = node.get_nodes_by_attr('save')
        for k in json_.keys():
            subnode = node.get(k)
            #Need to exclude lists from this culling, unless explicitly set save=false
            t1 = not isinstance(subnode, SequenceSchema) and not isinstance(subnode, TupleSchema)
            t2 = hasattr(subnode, 'save') and subnode.save == False
            t3 = k not in savable_attrs
            if (t1 and t2 and t3 and k in json_):
                json_.pop(k)

        #replace all save_reference json with just the json filename containing said object
        refd_names = node.get_nodes_by_attr('save_reference')
        for n in refd_names:
            if n in json_: #if a 'save_reference' attr is None, it will hit this
                if json_[n] is None:
                    continue
                elif isinstance(json_[n], list):
                    #this is a SequenceSchema or TupleSchema tagged with save_reference
                    for i, subjson in enumerate(json_[n]):
                        json_[n][i] = subjson['name'] + '.json'
                else:
                    #single reference
                    json_[n] = json_[n]['name'] + '.json'

        #Put supporting files into the zipfile and edit their paths in the json
        datafiles = node.get_nodes_by_attr('isdatafile')
        for d in datafiles:
            if d in json_:
                if json_[d] is None:
                    continue
                elif isinstance(json_[d], six.string_types):
                    json_[d] = self._process_supporting_file(json_[d], zipfile_)
                elif isinstance(json_[d], collections.Iterable):
                    #List, tuple, etc
                    for i, filename in enumerate(json_[d]):
                        json_[d][i] = self._process_supporting_file(filename, zipfile_)

        #Finally, write the json itself to the zipfile, and return the json
        if json_['name'] + '.json' not in zipfile_.namelist():
            zipfile_.writestr(str(json_['name']) + '.json', json.dumps(json_, indent=True))
        return json_

    def save(self, node, appstruct, zipfile_, refs):
        def callback(subnode, subappstruct):
            if not hasattr(subnode, '_save'):
                #This happens when it goes into non-gnome object attributes (Strings, Numbers, etc)
                if (subnode.schema_type is Sequence or subnode.schema_type is OrderedCollectionType):
#                     issubclass(subnode.children[0].__class__, ObjTypeSchema):
                    #To be able to continue saving inside iterables, whose schema does not contain a
                    #save function, call the subnode typ _impl with this function as callback
                    #Doing that will execute this function against each item in the iterable,
                    #and should continue the chain if it contains further iterables.
                    scalar = hasattr(subnode.typ, 'accept_scalar') and subnode.typ.accept_scalar
                    return subnode.typ._impl(subnode, subappstruct, callback, scalar)
                elif (subnode.schema_type is Tuple):
                    return subnode.typ._impl(subnode, subappstruct, callback)
                else:
                    #Not an iterable containing Gnome objects, so simply return
                    #the serialization of this non-GNOME object.
                    return subnode.serialize(subappstruct)
            else:
                #This is the path for Gnome objects
                return subnode._save(subappstruct,
                                    zipfile_=zipfile_,
                                    refs=refs)

        #gets the dictionary representation of the object, 'save' is passed
        dict_ = self._prepare_save(node, appstruct, zipfile_, refs)
        #Recursively serializes each node, producing the object's json
        preprocessed_json = self._impl(node, dict_, callback)
        #Processes references, adds supporting files to the zipfile, and writes
        #the json to the zip, and returns the json of the object.
        return self._save(node, preprocessed_json, zipfile_, refs)

    def _process_supporting_file(self, raw_path, zipfile_):
        '''
        raw_path is the filename stored on the object
        zipfile is an open zipfile.Zipfile in append mode
        returns the name of the file in the archive
        '''
        d_fname = os.path.split(raw_path)[1]
        # add datafile to zip archive

        if d_fname not in zipfile_.namelist():
            zipfile_.write(raw_path, d_fname)

        return d_fname

    def load(self, node, cstruct, saveloc, refs):
        def callback(subnode, subcstruct):
            if not hasattr(subnode, 'load'):
                #This is the path for non-gnome attributes
                if ((subnode.schema_type is Sequence or subnode.schema_type is OrderedCollectionType) and
                    isinstance(subnode.children[0], ObjTypeSchema)):
                    #To deal with iterable schemas that do not have a load function
                    scalar = hasattr(subnode.typ, 'accept_scalar') and subnode.typ.accept_scalar
                    return subnode.typ._impl(subnode, subcstruct, callback, scalar)
                elif (subnode.schema_type is Tuple):
                    return subnode.typ._impl(subnode, subcstruct, callback)
                else:
                    return subnode.deserialize(subcstruct)
            else:
                #this is the path for Gnome attributes
                return subnode.load(subcstruct, saveloc=saveloc, refs=refs)

        #takes the obj_json with references and replaces the references
        #with the un-hydrated obj_json from each file.
        hydrated_json = self.hydrate_json(node, cstruct, saveloc, refs)
        #Recursively loads each node. After this, the hydrated json is
        #an object dict
        dict_ = self._impl(node, hydrated_json, callback)
        #instantiates the object exactly as deserialize would do
        return self._deser(node, dict_, refs)

    def hydrate_json(self, node, cstruct, saveloc, refs):
        #Get all the save_reference attributes and load the files
        refd_attrs = node.get_nodes_by_attr('save_reference')
        for r in refd_attrs:
            if r in cstruct:
                if isinstance(cstruct[r], list):
                    #Need to turn this into a list of unhydrated object json
                    for i, fn in enumerate(cstruct[r]):
                        cstruct[r][i] = self._load_json_from_file(fn, saveloc)
                        cstruct[r][i]['id'] = fn
                else:
                    fn = cstruct[r]
                    if fn is not None:
                        cstruct[r] = self._load_json_from_file(fn, saveloc)
                        cstruct[r]['id'] = fn
                #since object id is not saved, but we need a means to ID this object
                #during deserialization, append filename as object id. It's removed
                #later
        #extract any isdatafile attributes to a temporary directory and amend the
        #entry in json with this path.
        tmpdir = None
        datafiles = node.get_nodes_by_attr('isdatafile')
        if len(datafiles) > 0:
            tmpdir = tempfile.mkdtemp()
        for d in datafiles:
            if d in cstruct:
                if isinstance(cstruct[d], six.string_types):
                    cstruct[d] = self._load_supporting_file(cstruct[d], saveloc, tmpdir)
                elif isinstance(cstruct[d], collections.Iterable):
                    #List, tuple, etc
                    for i, filename in enumerate(cstruct[d]):
                        cstruct[d][i] = self._load_supporting_file(filename, saveloc, tmpdir)
        return cstruct

    def _load_supporting_file(self, filename, saveloc, tmpdir):
        '''
        filename is the name of the file in the zip
        saveloc can be a folder or open zipfile.ZipFile object
        if saveloc is a folder and the filename exists inside,
        this does not return an altered name, nor does it extract to the temporary directory.
        An altered filename is returned if it cannot find the filename directly
        or if saveloc is an open zipfile
        in a temporary directory
        '''
        if filename is None:
            return
        if isinstance(saveloc, zipfile.ZipFile):
            return saveloc.extract(filename, tmpdir)
        elif os.path.exists(os.path.join(saveloc, filename)):
            return os.path.join(saveloc, filename)
        elif os.path.exists(filename):
            return filename
        else:
            return filename


    def _load_json_from_file(self, fname, saveloc):
        '''
        filename is the name of the file in the zip
        saveloc can be a folder or open zipfile.ZipFile object
        '''
        if fname is None:
            return
        fp = None
        if isinstance(saveloc, zipfile.ZipFile):
            fp = saveloc.open(fname, 'rU')
        else:
            fname = os.path.join(saveloc, fname)
            fp = saveloc.open(fp, 'rU')
        return json.load(fp, parse_float=True, parse_int=True)

class ObjTypeSchema(MappingSchema):
    schema_type = ObjType

    '''
    These are the default schema settings for GnomeId objects.
    Put them in your schema declaration if an override is desired.
    '''

    save=True               #Attr will appear in save files
    update=True             #Attr is updatable through .update
    read_only=False         #Attr is read only. This supersedes update
    test_equal=True         #Attr will be ignored in == tests
    isdatafile = False      #Attr references filenames to be added to save files
    save_reference = True   #Attr is a link to another GnomeId and should be
                            #saved as a reference in save files
    default = null          #(Colander) Set default = drop to skip this attribute
                            #if it is None during serialization
    missing = drop            #(Colander) If not present in cstruct, ignore. This
                            #attribute is NOT required for correct deserialization
                            #set missing=required for all attributes that ARE
                            #required for object init.

    #These are the defaults automatically applied to children of this node
    #if not defined already
    _colander_defaults = {'save':save,
                          'update':update,
                          'read_only':read_only,
                          'test_equal':test_equal,
                          'isdatafile':isdatafile,
                          'missing':missing,
                          'default':default
                          }

    '''
    defines the obj_type which is stored by all gnome objects when persisting
    to save files
    It also optionally stores the 'id' if present
    '''
    id = SchemaNode(
        String(), save=False, read_only=True
    )
    obj_type = SchemaNode(
        String(), missing=required, read_only=True
    )
    name = SchemaNode(
        String()
    )

    def __init__(self, *args, **kwargs):
        super(ObjTypeSchema, self).__init__(*args, **kwargs)
        for c in self.children:
            for k,v in self._colander_defaults.items():
                if not hasattr(c, k):
                    setattr(c, k, v)
                elif hasattr(c, k) and hasattr(c.__class__, k) and getattr(c, k) is getattr(c.__class__, k):
                    #things like missing, which by default are 'required' on the class
                    #if overridden, it will be on the instance instead
                    setattr(c, k, v)
            if c.read_only and c.update:
                c.update=False

    def _update(self, cstruct=None, refs=None):
        if refs is None:
            refs = Refs()
        return self.typ._update(self,
                               cstruct=cstruct)

    def deserialize(self, cstruct=None, refs=None):
        if refs is None:
            refs = Refs()
        appstruct = self.typ.deserialize(self, cstruct, refs=refs)
        return appstruct

    def _save(self, obj, zipfile_=None, refs=None):
        '''
        Saves the object passed in to a zip file. Note that ths name of this
        function is '_save' to allow the attribute 'save' to be used to specify
        if this SchemaNode represents an attribute that should be saved.

        :param obj: Gnome object to be saved
        :param zipfile_: an open zipfile.Zipfile object, in append mode
        :param name: unless specified, uses name of obj
        :param refs: references dict

        :returns Processed json representation of the object.
        When this returns, zipfile_ should be a complete zip savefile of obj,
        and refs will be a dictionary of all GNOME objects keyed by id.
        '''
        if obj is None:
            raise ValueError(self.__class__.__name__ + ': Cannot save a None')
        if not issubclass(obj.__class__, GnomeId) and not isinstance(obj, GnomeId):
            raise TypeError('This schema cannot save {0}, a non-GNOME object'.format(obj.__class__))
        if obj._schema is not self.__class__:
            raise TypeError('A {0} cannot save a {1}'.format(self.__class__.__name__, obj.__class__.__name__))

        if zipfile is None:
            raise ValueError('Must pass an open zipfile.Zipfile in append mode to zipfile_')
        if refs is None:
            refs = Refs()

        obj_json = self.typ.save(self, obj, zipfile_, refs)
        return obj_json

    def load(self, obj_json, saveloc=None, refs=None):
        if obj_json is None:
            raise ValueError(self.__class__.__name__ + ': Cannot load a None')
        cls = class_from_objtype(obj_json['obj_type'])
        if cls._schema is not self.__class__:
            raise TypeError('A {0} cannot save a {1}'.format(self.__class__.__name__, cls.__name__))
        if zipfile is None:
            raise ValueError('Must pass an open zipfile.Zipfile in append mode to saveloc')

        obj = self.typ.load(self, obj_json, saveloc, refs)
        return obj


    def get_nodes_by_attr(self, attr):
        '''
        Returns a list of child node names that have the specified attr set on them
        This replaces the State and Field mechanisms from the old serialization paradigm
        Now such attributes are on the schema directly

        If attr is 'all' it just returns a list of all child node names
        '''
        if attr == 'all':
            return [n.name for n in self.children]
        else:
            names = [n.name for n in filter(lambda c: hasattr(c, attr) and getattr(c, attr), self.children)]
            #sequences need to be taken into account. If present they will
            #considered to always have 'save' and 'update' as true, read as false,
            return names


class GeneralGnomeObjectSchema(ObjTypeSchema):
    '''
    The purpose of this schema is to be a placeholder in situations where you
    need to specify that an attribute may be one of many different types.

    For example, a PyCurrentMover's .current may be a GridCurrent, an
    IceAwareGridCurrent, a TimeseriesCurrent, etc. Alternatively, you may
    be composing an attribute from several types of Gnome object
    '''

    def __init__(self, acceptable_schemas=None, **kwargs):
        if not acceptable_schemas:
            raise ValueError('Must provide a list of at least one valid schema')
        self.acceptable_schemas = acceptable_schemas
        super(GeneralGnomeObjectSchema, self).__init__(**kwargs)

    def validate_input_schema(self, obj_or_json):
        '''
        Takes an object or json dict and determines if it can be represented by
        this schema instance. Returns an instance of the schema of the object,
        or raises an error if the object cannot be used with this schema.
        '''
        if type(obj_or_json) is dict:
            json_ = obj_or_json
            obj_type = class_from_objtype(json_['obj_type'])
            if obj_type._schema in self.acceptable_schemas:
                return obj_type._schema()
            else:
                raise TypeError('This type of json is not supported')
        else:
            obj = obj_or_json
            schema = obj.__class__._schema
            if schema in self.acceptable_schemas:
                return schema()
            else:
                raise TypeError('This type of object is not supported')

    def _update(self, appstruct=None, cstruct=None):
        substitute_schema = self.validate_input_schema(appstruct)
        return substitute_schema.typ._update(substitute_schema, appstruct, cstruct)

    def serialize(self, appstruct=None):
        substitute_schema = self.validate_input_schema(appstruct)
        return substitute_schema.typ.serialize(substitute_schema, appstruct)

    def deserialize(self, cstruct=None, refs=None):
        if refs is None:
            refs = Refs()
        substitute_schema = self.validate_input_schema(cstruct)
        return substitute_schema.typ.deserialize(substitute_schema, cstruct, refs=refs)

    def _save(self, obj, zipfile_=None, refs=None):
        if refs is None:
            refs = Refs()
        substitute_schema = self.validate_input_schema(obj)
        return substitute_schema.typ.save(substitute_schema, obj, zipfile_=zipfile_, refs=refs)

    def load(self, obj_json, saveloc=None, refs=None):
        if refs is None:
            refs = Refs()
        substitute_schema = self.validate_input_schema(obj_json)
        return substitute_schema.typ.load(substitute_schema, obj_json, saveloc=saveloc, refs=refs)


class CollectionItemMap(MappingSchema):
    '''
    This stores the obj_type and obj_index
    '''
    obj_type = SchemaNode(String())
    id = SchemaNode(String(), missing=drop)


class CollectionItemsList(SequenceSchema):
    item = CollectionItemMap()


class LongLat(TupleSchema):
    'Only contains 2D (long, lat) positions'
    long = SchemaNode(Float())
    lat = SchemaNode(Float())


class LongLatBounds(SequenceSchema):
    'Used to define bounds on a map'
    bounds = LongLat()


Polygon = LongLatBounds


class PolygonSet(SequenceSchema):
    polygonset = Polygon()


class WorldPoint(LongLat):
    'Used to define reference points. 3D positions (long,lat,z)'
    z = SchemaNode(Float(), default=0.0)


class WorldPointNumpy(NumpyFixedLenSchema):
    '''
    Define same schema as WorldPoint; however, the base class
    NumpyFixedLenSchema serializes/deserializes it from/to a numpy array
    '''
    long = SchemaNode(Float())
    lat = SchemaNode(Float())
    z = SchemaNode(Float())


class ImageSize(TupleSchema):
    'Only contains 2D (long, lat) positions'
    width = SchemaNode(Int())
    height = SchemaNode(Int())
