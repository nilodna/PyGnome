'''
GeoJson outputter
Does not contain a schema for persistence yet
'''
import copy
import os
from glob import glob
from itertools import izip

import numpy as np

from geojson import Feature, FeatureCollection, dump, MultiPoint, Point
from colander import SchemaNode, String, drop, Int, Bool

from gnome.utilities.time_utils import date_to_sec
from gnome.utilities.serializable import Serializable, Field
from gnome.persist import class_from_objtype, References
from gnome.persist.base_schema import CollectionItemsList

from .outputter import Outputter, BaseSchema


class TrajectoryGeoJsonSchema(BaseSchema):
    '''
    Nothing is required for initialization
    '''
    round_data = SchemaNode(Bool(), missing=drop)
    round_to = SchemaNode(Int(), missing=drop)
    output_dir = SchemaNode(String(), missing=drop)


class TrajectoryGeoJsonOutput(Outputter, Serializable):
    '''
    class that outputs GNOME results in a geojson format. The output is a
    collection of Features. Each Feature contains a Point object with
    associated properties. Following is the format for a particle - the
    data in <> are the results for each element.

    ::

        {
        "type": "FeatureCollection",
        "features": [
            {
                "geometry": {
                    "type": "Point",
                    "coordinates": [
                        <LONGITUDE>,
                        <LATITUDE>
                    ]
                },
                "type": "Feature",
                "id": <PARTICLE_ID>,
                "properties": {::
                    "current_time": <TIME IN SEC SINCE EPOCH>,
                    "status_code": <>,
                    "spill_id": <UUID OF SPILL OBJECT THAT RELEASED PARTICLE>,
                    "depth": <DEPTH>,
                    "spill_type": <FORECAST OR UNCERTAIN>,
                    "step_num": <OUTPUT ASSOCIATED WITH THIS STEP NUMBER>
                }
            },
            ...
        }

    '''
    _state = copy.deepcopy(Outputter._state)

    # need a schema and also need to override save so output_dir
    # is saved correctly - maybe point it to saveloc
    _state += [Field('round_data', update=True, save=True),
               Field('round_to', update=True, save=True),
               Field('output_dir', update=True, save=True)]
    _schema = TrajectoryGeoJsonSchema

    def __init__(self, round_data=True, round_to=4, output_dir=None,
                 **kwargs):
        '''
        :param bool round_data=True: if True, then round the numpy arrays
            containing float to number of digits specified by 'round_to'.
            Default is True
        :param int round_to=4: round float arrays to these number of digits.
            Default is 4.
        :param str output_dir=None: output directory for geojson files. Default
            is None since data is returned in dict for webapi. For using
            write_output_post_run(), this must be set

        use super to pass optional \*\*kwargs to base class __init__ method
        '''
        self.round_data = round_data
        self.round_to = round_to
        self.output_dir = output_dir

        super(TrajectoryGeoJsonOutput, self).__init__(**kwargs)

    def write_output(self, step_num, islast_step=False):
        'dump data in geojson format'
        super(TrajectoryGeoJsonOutput, self).write_output(step_num,
                                                          islast_step)

        if not self._write_step:
            return None

        # one feature per element client; replaced with multipoint
        # because client performance is much more stable with one
        # feature per step rather than (n) features per step.
        features = []
        for sc in self.cache.load_timestep(step_num).items():
            sc_type = 'uncertain' if sc.uncertain else 'forecast'

            # only display lat/long for now
            lat_long = self._dataarray_p_types(sc['positions'][:, :2])
            feature = Feature(geometry=MultiPoint(lat_long),
                              id="1",
                              properties={'sc_type': sc_type})
            if sc.uncertain:
                features.insert(0, feature)
            else:
                features.append(feature)

        geojson = FeatureCollection(features)
        # default geojson should not output data to file
        # read data from file and send it to web client
        output_info = {'step_num': step_num,
                       'time_stamp': sc.current_time_stamp.isoformat(),
                       'feature_collection': geojson
                       }

        if self.output_dir:
            output_filename = self.output_to_file(geojson, step_num)
            output_info.update({'output_filename': output_filename})

        return output_info

    def output_to_file(self, json_content, step_num):
        file_format = 'geojson_{0:06d}.geojson'
        filename = os.path.join(self.output_dir,
                                file_format.format(step_num))

        with open(filename, 'w') as outfile:
            dump(json_content, outfile, indent=True)

        return filename

    def _dataarray_p_types(self, data_array):
        '''
        return array as list with appropriate python dtype
        This is partly to make sure the dtype of the list elements is a python
        data type else geojson fails
        '''
        p_type = type(np.asscalar(data_array.dtype.type(0)))

        if p_type is long:
            'geojson expects int - it fails for a long'
            p_type = int

        if p_type is float and self.round_data:
            data = data_array.round(self.round_to).astype(p_type).tolist()
        else:
            data = data_array.astype(p_type).tolist()
        return data

    def rewind(self):
        'remove previously written files'
        super(TrajectoryGeoJsonOutput, self).rewind()
        self.clean_output_files()

    def clean_output_files(self):
        if self.output_dir:
            files = glob(os.path.join(self.output_dir, 'geojson_*.geojson'))
            for f in files:
                os.remove(f)


class CurrentGeoJsonSchema(BaseSchema):
    '''
    Nothing is required for initialization
    '''


class CurrentGeoJsonOutput(Outputter, Serializable):
    '''
    Class that outputs GNOME current velocity results for each current mover
    in a geojson format.  The output is a collection of Features.
    Each Feature contains a Point object with associated properties.
    Following is the output format - the data in <> are the results
    for each element.

    ::
    {
     "time_stamp": <TIME IN ISO FORMAT>,
     "step_num": <OUTPUT ASSOCIATED WITH THIS STEP NUMBER>,
     "feature_collections": {<mover_id>: {"type": "FeatureCollection",
                                          "features": [{"type": "Feature",
                                                        "id": <PARTICLE_ID>,
                                                        "properties": {"velocity": [u, v]
                                                                       },
                                                        "geometry": {"type": "Point",
                                                                     "coordinates": [<LONG>, <LAT>]
                                                                     },
                                                        },
                                                        ...
                                                       ],
                                          },
                             ...
                             }
    '''
    _state = copy.deepcopy(Outputter._state)

    # need a schema and also need to override save so output_dir
    # is saved correctly - maybe point it to saveloc
    _state.add_field(Field('current_movers', save=True, update=True,
                           iscollection=True))

    _schema = CurrentGeoJsonSchema

    def __init__(self, current_movers, **kwargs):
        '''
        :param list current_movers: A list or collection of current grid mover
                                    objects.

        use super to pass optional \*\*kwargs to base class __init__ method
        '''
        self.current_movers = current_movers

        super(CurrentGeoJsonOutput, self).__init__(**kwargs)

    def write_output(self, step_num, islast_step=False):
        'dump data in geojson format'
        super(CurrentGeoJsonOutput, self).write_output(step_num, islast_step)

        if self.on is False or not self._write_step:
            return None

        for sc in self.cache.load_timestep(step_num).items():
            pass

        model_time = date_to_sec(sc.current_time_stamp)

        geojson = {}
        for cm in self.current_movers:
            features = []
            centers = cm.mover._get_center_points()

            velocities = cm.get_scaled_velocities(model_time)
            rounded_velocities = self.get_rounded_velocities(velocities)
            unique_velocities = self.get_unique_velocities(rounded_velocities)

            for v in unique_velocities:
                matching = self.get_matching_velocities(rounded_velocities, v)
                points = centers[matching]
                feature = Feature(geometry=MultiPoint(coordinates=[p.tolist()
                                                                   for p
                                                                   in points]),
                                  id="1",
                                  properties={'velocity': list(v)})
                features.append(feature)

            geojson[cm.id] = FeatureCollection(features)

        # default geojson should not output data to file
        # read data from file and send it to web client
        output_info = {'step_num': step_num,
                       'time_stamp': sc.current_time_stamp.isoformat(),
                       'feature_collections': geojson
                       }

        return output_info

    def get_rounded_velocities(self, velocities):
        return np.vstack((velocities['u'].round(decimals=1),
                          velocities['v'].round(decimals=1))).T

    def get_unique_velocities(self, velocities):
        '''
            In order to make numpy perform this function fast, we will use a
            contiguous structured array using a view of a void type that
            joins the whole row into a single item.
        '''
        dtype = np.dtype((np.void,
                          velocities.dtype.itemsize * velocities.shape[1]))

        voidtype_array = np.ascontiguousarray(velocities).view(dtype)

        _, idx = np.unique(voidtype_array, return_index=True)

        return velocities[idx]

    def get_matching_velocities(self, velocities, v):
        return np.where((velocities == v).all(axis=1))

    def rewind(self):
        'remove previously written files'
        super(CurrentGeoJsonOutput, self).rewind()

    def current_movers_to_dict(self):
        '''
        a dict containing 'obj_type' and 'id' for each object in
        list/collection
        '''
        return self._collection_to_dict(self.current_movers)


class IceGeoJsonSchema(BaseSchema):
    '''
    Nothing is required for initialization
    '''


class IceGeoJsonOutput(Outputter, Serializable):
    '''
    Class that outputs GNOME ice velocity results for each ice mover
    in a geojson format.  The output is a collection of Features.
    Each Feature contains a Point object with associated properties.
    Following is the output format - the data in <> are the results
    for each element.

    ::
    {
     "time_stamp": <TIME IN ISO FORMAT>,
     "step_num": <OUTPUT ASSOCIATED WITH THIS STEP NUMBER>,
     "feature_collections": {<mover_id>: {"type": "FeatureCollection",
                                          "features": [{"type": "Feature",
                                                        "id": <PARTICLE_ID>,
                                                        "properties": {"ice_fraction": <FRACTION>,
                                                                       "ice_thickness": <METERS>,
                                                                       "water_velocity": [u, v],
                                                                       "ice_velocity": [u, v]
                                                                       },
                                                        "geometry": {"type": "Point",
                                                                     "coordinates": [<LONG>, <LAT>]
                                                                     },
                                                        },
                                                        ...
                                                       ],
                                          },
                             ...
                             }
    '''
    _state = copy.deepcopy(Outputter._state)

    # need a schema and also need to override save so output_dir
    # is saved correctly - maybe point it to saveloc
    _state.add_field(Field('ice_movers',
                           save=True, update=True, iscollection=True))

    _schema = IceGeoJsonSchema

    def __init__(self, ice_movers, **kwargs):
        '''
        :param list current_movers: A list or collection of current grid mover
                                    objects.

        use super to pass optional \*\*kwargs to base class __init__ method
        '''
        self.ice_movers = ice_movers

        super(IceGeoJsonOutput, self).__init__(**kwargs)

    def write_output(self, step_num, islast_step=False):
        'dump data in geojson format'
        super(IceGeoJsonOutput, self).write_output(step_num, islast_step)

        if self.on is False or not self._write_step:
            return None

        for sc in self.cache.load_timestep(step_num).items():
            pass

        model_time = date_to_sec(sc.current_time_stamp)

        geojson = {}
        for mover in self.ice_movers:
            features = []
            ice_thickness, ice_coverage = mover.get_ice_fields(model_time)
            centers = mover.mover._get_center_points()

            for t, c, cp in izip(ice_thickness, ice_coverage, centers):
                features.append(Feature(id="1",
                                        properties={'thickness': t,
                                                    'coverage': c},
                                        geometry=Point(list(cp))
                                        ))

            geojson[mover.id] = FeatureCollection(features)

        # default geojson should not output data to file
        # read data from file and send it to web client
        output_info = {'step_num': step_num,
                       'time_stamp': sc.current_time_stamp.isoformat(),
                       'feature_collections': geojson
                       }

        return output_info

    def rewind(self):
        'remove previously written files'
        super(IceGeoJsonOutput, self).rewind()

    def serialize(self, json_='webapi'):
        """
            Serialize our current velocities outputter to JSON
        """
        dict_ = self.to_serialize(json_)
        schema = self.__class__._schema()
        json_out = schema.serialize(dict_)

        json_out['ice_movers'] = []

        for cm in self.ice_movers:
            json_out['ice_movers'].append(cm.serialize(json_))

        return json_out

    @classmethod
    def deserialize(cls, json_):
        """
        append correct schema for current mover
        """
        schema = cls._schema()
        _to_dict = schema.deserialize(json_)

        if 'ice_movers' in json_:
            _to_dict['ice_movers'] = []
            for i, cm in enumerate(json_['ice_movers']):
                cm_cls = class_from_objtype(cm['obj_type'])
                cm_dict = cm_cls.deserialize(json_['ice_movers'][i])

                _to_dict['ice_movers'].append(cm_dict)

        return _to_dict
