#!/usr/bin/env python
import os
import shutil
from datetime import datetime, timedelta
import copy
import inspect
import zipfile
import collections
import pdb

import numpy as np

from colander import (SchemaNode,
                      String, Float, Int, Bool, List,
                      drop, OneOf, SequenceSchema)

from gnome.environment import Environment

import gnome.utilities.cache
from gnome.utilities.time_utils import round_time
from gnome.utilities.orderedcollection import OrderedCollection

from gnome.basic_types import oil_status, fate
from gnome.spill_container import SpillContainerPair
from gnome.environment import Wind
from gnome.movers import Mover
from gnome.weatherers import (weatherer_sort,
                              Weatherer,
                              WeatheringData,
                              FayGravityViscous,
                              Langmuir,
                              weatherer_schemas)
from gnome.outputters import Outputter, NetCDFOutput, WeatheringOutput
from gnome.persist import (extend_colander,
                           validators,
                           References)
from gnome.persist.base_schema import (ObjTypeSchema,
                                       CollectionItemsList,
    GeneralGnomeObjectSchema)
from gnome.exceptions import ReferencedObjectNotSet, GnomeRuntimeError
from gnome.spill.spill import SpillSchema
from gnome.gnomeobject import GnomeId, allowzip64, Refs
from gnome.persist.extend_colander import OrderedCollectionSchema
from gnome.map import GnomeMapSchema, MapFromBNASchema, ParamMapSchema, MapFromUGridSchema


class ModelSchema(ObjTypeSchema):
    'Colander schema for Model object'
    time_step = SchemaNode(Float())
    weathering_substeps = SchemaNode(Int())
    start_time = SchemaNode(
        extend_colander.LocalDateTime(),
        validator=validators.convertible_to_seconds
    )
    duration = SchemaNode(
        extend_colander.TimeDelta()
    )
    uncertain = SchemaNode(Bool())
    cache_enabled = SchemaNode(Bool())
    num_time_steps = SchemaNode(Int(), read_only=True)
    make_default_refs = SchemaNode(Bool())
    mode = SchemaNode(
        String(), validator=OneOf(['gnome', 'adios', 'roc'])
    )
    location = SchemaNode(
        List(), missing=drop,

    )
    map = GeneralGnomeObjectSchema(
        acceptable_schemas=(GnomeMapSchema,
                            MapFromBNASchema,
                            ParamMapSchema,
                            MapFromUGridSchema),
        save_reference=True
    )
    spills = OrderedCollectionSchema(
        GeneralGnomeObjectSchema(acceptable_schemas=[SpillSchema]),
        save_reference=True, test_equal=False
    )
#     uncertain_spills = OrderedCollectionSchema(
#         GeneralGnomeObjectSchema(acceptable_schemas=[SpillSchema]),
#         save_reference=True, test_equal=False
#     )
    movers = OrderedCollectionSchema(
        GeneralGnomeObjectSchema(acceptable_schemas=gnome.movers.mover_schemas),
        save_reference=True
    )
    weatherers = OrderedCollectionSchema(
        GeneralGnomeObjectSchema(acceptable_schemas=weatherer_schemas),
        save_reference=True
    )
    environment = OrderedCollectionSchema(
        GeneralGnomeObjectSchema(acceptable_schemas=gnome.environment.schemas),
        save_reference=True
    )
    outputters = OrderedCollectionSchema(
        GeneralGnomeObjectSchema(acceptable_schemas=gnome.outputters.schemas),
        save_reference=True
    )


class Model(GnomeId):
    '''
    PyGnome Model Class
    '''
    _schema = ModelSchema

    # list of OrderedCollections
    _oc_list = ['movers', 'weatherers', 'environment', 'outputters']

    modes = {'gnome', 'adios', 'roc'}

    @classmethod
#     def new_from_dict(cls, dict_):
#         'Finalize model construction from deserialized json or save file'
#
#         new_model = super(Model, cls).new_from_dict(dict_)
#         for oc in _oc_list:
#             pass
#
#         json_ = dict_.pop('json_')
#         l_env = dict_.pop('environment', [])
#         l_out = dict_.pop('outputters', [])
#         g_objects = dict_.pop('movers', [])
#         l_weatherers = dict_.pop('weatherers', [])
#         c_spills = dict_.pop('spills', [])
#
#         if 'uncertain_spills' in dict_:
#             u_spills = dict_.pop('uncertain_spills')
#             l_spills = zip(c_spills, u_spills)
#         else:
#             l_spills = c_spills
#
#         # define defaults for properties that a location file may not contain
#         kwargs = inspect.getargspec(cls.__init__)
#         default_restore = dict(zip(kwargs[0][1:], kwargs[3]))
#
#         if json_ == 'webapi':
#             # default is to disable cache
#             default_restore['cache_enabled'] = False
#
#         for key in default_restore:
#             default_restore[key] = dict_.pop(key, default_restore[key])
#
#         model = object.__new__(cls)
#         model.__restore__(**default_restore)
#
#         [model.environment.add(obj) for obj in l_env]
#         [model.outputters.add(obj) for obj in l_out]
#         [model.spills.add(obj) for obj in l_spills]
#         [model.movers.add(obj) for obj in g_objects]
#         [model.weatherers.add(obj) for obj in l_weatherers]
#
#         # register callbacks with OrderedCollections after objects are added
#         model._register_callbacks()
#
#         # OrderedCollections are being used so maintain order.
#         if json_ == 'webapi':
#             model.update_from_dict(dict_)
#         else:
#             cls._restore_attr_from_save(model, dict_)
#
#         # restore the spill data outside this method - let's not try to find
#         # the saveloc here
#         msg = ("{0._pid}'new_from_dict' created new model: "
#                "{0.name}").format(model)
#         model.logger.info(msg)
#         return model
    @classmethod
    def load_savefile(cls, filename):
        """
        Load a model instance from a save file

        :param filename: the filename of the save file -- usually a zip file,
                         but can also be a directry with the full contents of
                         a zip file

        :return: a model instance all set up from the savefile.

        This is simply a utility wrapper around: ``gnome.persist.save_load.load()``
        """

        model = gnome.persist.save_load.load(filename)

        # check that this actually loaded a model object
        #  load() will load any gnome object from json...
        if not isinstance(model, cls):
            msg = "This does not appear to be a save file for a model\n"
            msg += "loaded a %s instead" % type(model)
            raise ValueError(msg)
        else:
            return model

    def __init__(self,
                 name='Model',
                 time_step=None,
                 start_time=round_time(datetime.now(), 3600),
                 duration=timedelta(days=1),
                 weathering_substeps=1,
                 map=None,
                 uncertain=False,
                 cache_enabled=False,
                 mode=None,
                 location=[],
                 environment=[],
                 outputters=[],
                 movers=[],
                 weatherers=[],
                 spills=[],
                 uncertain_spills=[],
                 **kwargs):
        '''
        Initializes a model.
        All arguments have a default.

        :param time_step=timedelta(minutes=15): model time step in seconds
                                                or as a timedelta object

        :param start_time=datetime.now(): start time of model, datetime
                                          object. Rounded to the nearest hour.

        :param duration=timedelta(days=1): How long to run the model,
                                           a timedelta object.

        :param weathering_substeps=1: How many weathering substeps to
                                          run inside a single model time step.

        :param map=gnome.map.GnomeMap(): The land-water map.

        :param uncertain=False: Flag for setting uncertainty.

        :param cache_enabled=False: Flag for setting whether the model should
                                    cache results to disk.

        :param mode='Gnome': The runtime 'mode' that the model should use.
                             This is a value that the Web Client uses to
                             decide which UI views it should present.
        '''
        # making sure basic stuff is in place before properties are set
        self.environment = OrderedCollection(dtype=Environment)
        self.movers = OrderedCollection(dtype=Mover)
        self.weatherers = OrderedCollection(dtype=Weatherer)
        self.outputters = OrderedCollection(dtype=Outputter)

        self.environment.add(environment)
        self.movers.add(movers)
        self.weatherers.add(weatherers)
        self.outputters.add(outputters)

        # contains both certain/uncertain spills
        self.spills = SpillContainerPair(uncertain)
        if len(uncertain_spills) > 0:
            _spills = zip(spills, uncertain_spills)
        else:
            _spills = spills
        self.spills.add(_spills)

        self._cache = gnome.utilities.cache.ElementCache()
        self._cache.enabled = cache_enabled

        # default to now, rounded to the nearest hour
        self._start_time = start_time
        self._duration = duration
        self.weathering_substeps = weathering_substeps

        self._name = name

        if not map:
            map = gnome.map.GnomeMap()
        self._map = map

        if mode is not None:
            if mode in Model.modes:
                self.mode = mode
            else:
                raise ValueError('Model mode ({}) invalid, '
                                 'should be one of {{{}}}'
                                 .format(mode, ', '.join(Model.modes)))
        else:
            self.mode = 'gnome'


        # reset _current_time_step
        self._current_time_step = -1
        self._time_step = None
        if time_step is not None:
            self.time_step = time_step  # this calls rewind() !
        self._reset_num_time_steps()

        # default is to zip save file
        self.zipsave = True

        # model creates references to weatherers/environment if
        # make_default_refs is True
        self.make_default_refs = True

        self.location = location
        self._register_callbacks()

    def _register_callbacks(self):

        '''
        Register callbacks with the OrderedCollections
        '''
        self.movers.register_callback(self._callback_add_mover,
                                      ('add', 'replace'))
        self.weatherers.register_callback(self._callback_add_weatherer_env,
                                          ('add', 'replace'))
        self.environment.register_callback(self._callback_add_weatherer_env,
                                           ('add', 'replace'))
        self.outputters.register_callback(self._callback_add_outputter,
                                          ('add', 'replace'))

        self.movers.register_callback(self._callback_add_spill,
                                      ('add', 'replace', 'remove'))

    def reset(self, **kwargs):
        '''
        Resets model to defaults -- Caution -- clears all movers, spills, etc.
        Takes same keyword arguments as :meth:`__init__()`
        '''
        self.__init__(**kwargs)

    def rewind(self):
        '''
        Rewinds the model to the beginning (start_time)
        '''
        self._current_time_step = -1
        self.model_time = self._start_time

        # fixme: do the movers need re-setting? -- or wait for
        #        prepare_for_model_run?

        # note: This may be redundant.  They will get reset in
        #       setup_model_run() anyway..
        self.spills.rewind()

        # set rand before each call so windages are set correctly
        gnome.utilities.rand.seed(1)

        # clear the cache:
        self._cache.rewind()

        for outputter in self.outputters:
            outputter.rewind()

        self.logger.info(self._pid + "rewound model - " + self.name)

#    def write_from_cache(self, filetype='netcdf', time_step='all'):
#        """
#        write the already-cached data to an output files.
#        """

    def update_from_dict(self, dict_, refs=None):
        """
        functions in common_object.
        """
        if refs is None:
            refs = Refs()
            self._schema.register_refs(self._schema(), self, refs)
        updatable = self._schema().get_nodes_by_attr('update')
        attrs = copy.copy(dict_)
        updated = False
        for k in attrs.keys():
            if k not in updatable:
                attrs.pop(k)

        for name in updatable:
            node = self._schema().get(name)
            if name in attrs:
                if name != 'spills':
                    attrs[name] = self._schema.process_subnode(node, self, getattr(self, name), name, attrs, attrs[name], refs)
                    if attrs[name] is drop:
                        del attrs[name]
                else:
                    oldspills = OrderedCollection(self.spills._spill_container.spills[:], dtype=self.spills._spill_container.spills.dtype)
                    new_spills = ObjTypeSchema.process_subnode(node, self, self.spills._spill_container.spills, 'spills', attrs, attrs[name], refs)
                    if not updated and self._attr_changed(oldspills, new_spills):
                        updated = True
                    attrs.pop(name)

        for k, v in attrs.items():
            if hasattr(self, k):
                if not updated and self._attr_changed(getattr(self, k), v):
                    updated = True
                setattr(self, k, v)
        return updated

    @property
    def uncertain(self):
        '''
        Uncertainty attribute of the model. If flag is toggled, rewind model
        '''
        return self.spills.uncertain

    @uncertain.setter
    def uncertain(self, uncertain_value):
        '''
        Uncertainty attribute of the model
        '''
        if self.spills.uncertain != uncertain_value:
            self.spills.uncertain = uncertain_value  # update uncertainty
            self.rewind()

    @property
    def uncertain_spills(self):
        return self.spills.to_dict().get('uncertain_spills', [])

    @property
    def cache_enabled(self):
        '''
        If True, then generated data is cached
        '''
        return self._cache.enabled

    @cache_enabled.setter
    def cache_enabled(self, enabled):
        self._cache.enabled = enabled

    @property
    def has_weathering_uncertainty(self):
        return (any([w.on for w in self.weatherers]) and
                len([o for o in self.outputters
                     if isinstance(o, WeatheringOutput)]) > 0 and
                (any([s.amount_uncertainty_scale > 0.0
                     for s in self.spills]) or
                 any([w.speed_uncertainty_scale > 0.0
                     for w in self.environment
                     if isinstance(w, Wind)]))
                )

    @property
    def start_time(self):
        '''
        Start time of the simulation
        '''
        return self._start_time

    @start_time.setter
    def start_time(self, start_time):
        self._start_time = start_time
        self.rewind()

    @property
    def time_step(self):
        '''
        time step over which the dynamics is computed
        '''
        return self._time_step

    @time_step.setter
    def time_step(self, time_step):
        '''
        Sets the time step, and rewinds the model

        :param time_step: The timestep can be a timedelta object
                          or integer seconds.
        '''
        try:
            self._time_step = time_step.total_seconds()
        except AttributeError:
            self._time_step = int(time_step)

        self._reset_num_time_steps()
        self.rewind()

    @property
    def current_time_step(self):
        '''
        Current timestep of the simulation
        '''
        return self._current_time_step

    @current_time_step.setter
    def current_time_step(self, step):
        self.model_time = self._start_time + timedelta(seconds=step *
                                                       self.time_step)
        self._current_time_step = step

    @property
    def duration(self):
        '''
        total duration of the model run
        '''
        return self._duration

    @duration.setter
    def duration(self, duration):
        if duration < self._duration:
            # only need to rewind if shorter than it was...
            # fixme: actually, only need to rewind if current model time
            # is beyond new time...
            self.rewind()
        self._duration = duration
        self._reset_num_time_steps()

    @property
    def map(self):
        '''
        land water map used for simulation
        '''
        return self._map

    @map.setter
    def map(self, map_in):
        self._map = map_in
        self.rewind()

    @property
    def num_time_steps(self):
        '''
        Read only attribute
        computed number of timesteps based on py:attribute:`duration` and
        py:attribute:`time_step`
        '''
        return self._num_time_steps

    def _reset_num_time_steps(self):
        '''
        reset number of time steps if duration, or time_step change
        '''
        # We do not count any remainder time.
        if self.duration is not None and self.time_step is not None:
            initial_0th_step = 1
            self._num_time_steps = (initial_0th_step +
                                    int(self.duration.total_seconds() //
                                        self.time_step))
        else:
            self._num_time_steps = None

    def contains_object(self, obj_id):
        if self.map.id == obj_id:
            return True

        for collection in (self.environment,
                           self.spills,
                           self.movers,
                           self.weatherers,
                           self.outputters):
            for o in collection:
                if obj_id == o.id:
                    return True

                if (hasattr(o, 'contains_object') and
                        o.contains_object(obj_id)):
                    return True

        return False

    def find_by_class(self, obj, collection, ret_all=False):
        '''
        Look for an object that isinstance() of obj in specified colleciton.
        By default, it will return the first object of this type.
        To get all obects of this type, set ret_all to True
        '''
        all_objs = []
        for item in collection:
            if isinstance(item, obj):
                if not ret_all:
                    return obj
                else:
                    all_objs.append(obj)

        if len(all_objs) == 0:
            return None

        return all_objs

    def find_by_attr(self, attr, value, collection, allitems=False):
        '''
        find first object in collection where the 'attr' attribute matches
        'value'. This is primarily used to find 'wind', 'water', 'waves'
        objects in environment collection. Use the '_ref_as' attribute to
        search.

        Ignore AttributeError since all objects in collection may not contain
        the attribute over which we are searching.

        :param str attr: attribute whose value must match
        :param str value: desired value of the attribute
        :param OrderedCollection collection: the ordered collection in which
            to search
        '''
        items = []
        for item in collection:
            try:
                if not isinstance(getattr(item, attr), basestring):
                    if any([value == v for v in getattr(item, attr)]):
                        if allitems:
                            items.append(item)
                        else:
                            return item
                else:
                    if getattr(item, attr) == value:
                        if allitems:
                            items.append(item)
                        else:
                            return item
            except AttributeError:
                pass
        items = None if items == [] else items

        return items

    def _order_weatherers(self):
        'use weatherer_sort to sort the weatherers'
        s_weatherers = sorted(self.weatherers, key=weatherer_sort)
        if self.weatherers.values() != s_weatherers:
            self.weatherers.clear()
            self.weatherers += s_weatherers

    def _attach_references(self):
        '''
        attach references
        '''
        attr = {}
        attr['wind'] = self.find_by_attr('_ref_as', 'wind', self.environment)
        attr['water'] = self.find_by_attr('_ref_as', 'water', self.environment)
        attr['waves'] = self.find_by_attr('_ref_as', 'waves', self.environment)
        attr['current'] = self.find_by_attr('_ref_as', 'current', self.environment)

        weather_data = set()
        wd = None
        spread = None
        langmuir = None
        for coll in ('environment', 'weatherers', 'movers'):
            for item in getattr(self, coll):
                if hasattr(item, '_req_refs'):
                    ref_dict = {}
                    for var in item._req_refs.keys():
                        inst = self.find_by_attr('_ref_as', var,
                                                 self.environment)
                        if inst is not None:
                            ref_dict[var] = inst
                    if len(ref_dict) > 0:
                        item._attach_default_refs(ref_dict)
                else:
                    if coll == 'weatherers':
                        # by default turn WeatheringData and spreading object
                        # off
                        if isinstance(item, WeatheringData):
                            item.on = False
                            wd = item

                        try:
                            if item._ref_as == 'spreading':
                                item.on = False
                                spread = item

                        except AttributeError:
                            pass

                        try:
                            if item._ref_as == 'langmuir':
                                item.on = False
                                langmuir = item

                        except AttributeError:
                            pass

                        if item.on:
                            weather_data.update(item.array_types)

                    if hasattr(item, 'on') and not item.on:
                        # no need to setup references if item is not on
                        continue

                    for name, val in attr.iteritems():
                        if (hasattr(item, name) and
                                getattr(item, name) is None and
                                item.make_default_refs):
                            setattr(item, name, val)

        all_spills = [sp
                      for sc in self.spills.items()
                      for sp in sc.spills.values()]

        for spill in all_spills:
            for name, val in attr.iteritems():
                if (hasattr(spill, name) and
                        getattr(spill, name) is None and
                        spill.make_default_refs):
                    setattr(spill, name, val)

        # if WeatheringData object and FayGravityViscous (spreading object)
        # are not defined by user, add them automatically because most
        # weatherers will need these
        if len(weather_data) > 0:
            if wd is None:
                self.weatherers += WeatheringData(attr['water'])
            else:
                # turn mass_balance on and make references
                wd.on = True
                if wd.make_default_refs:
                    wd.water = attr['water']

        # if a weatherer is using 'area' array, make sure it is being set.
        # Objects that set 'area' are referenced as 'spreading'
        if 'area' in weather_data:
            if spread is None:
                self.weatherers += FayGravityViscous(attr['water'])
            else:
                # turn spreading on and make references
                spread.on = True
                if spread.make_default_refs:
                    for at in attr:
                        if hasattr(spread, at):
                            spread.water = attr['water']

            if langmuir is None:
                self.weatherers += Langmuir(attr['water'], attr['wind'])
            else:
                # turn spreading on and make references
                langmuir.on = True
                if langmuir.make_default_refs:
                    for at in attr:
                        if hasattr(langmuir, at):
                            langmuir.water = attr['water']
                            langmuir.wind = attr['wind']

    def setup_model_run(self):
        '''
        Sets up each mover for the model run
        '''
        # use a set since we only want to add unique 'names' for data_arrays
        # that will be added
        array_types = set()

        # attach references so objects don't raise ReferencedObjectNotSet error
        # in prepare_for_model_run()
        self._attach_references()
        self.spills.rewind()  # why is rewind for spills here?

        # remake orderedcollections defined by model
        for oc in [self.movers, self.weatherers,
                   self.outputters, self.environment]:
            oc.remake()

        for op in self.outputters:
            array_types.update(op.array_types)

        # order weatherers collection
        self._order_weatherers()
        transport = False
        for mover in self.movers:
            if mover.on:
                mover.prepare_for_model_run()
                transport = True
                array_types.update(mover.array_types)

        weathering = False
        for w in self.weatherers:
            for sc in self.spills.items():
                # weatherers will initialize 'mass_balance' key/values
                # to 0.0
                if w.on:
                    w.prepare_for_model_run(sc)
                    weathering = True
                    array_types.update(w.array_types)

        for environment in self.environment:
            environment.prepare_for_model_run(self.start_time)

        if self.time_step is None:
            # for now hard-code this; however, it should depend on weathering
            # note: do not set time_step attribute because we don't want to
            # rewind because that will reset spill_container data
            if transport:
                self._time_step = 900
            elif weathering and not transport:
                # todo: 1 hour
                self._time_step = 3600
            else:
                # simple case with no weatherers or movers
                self._time_step = 900
            self._reset_num_time_steps()

        for sc in self.spills.items():
            sc.prepare_for_model_run(array_types)

        # outputters need array_types, so this needs to come after those
        # have been updated.
        for outputter in self.outputters:
            outputter.prepare_for_model_run(model_start_time=self.start_time,
                                            cache=self._cache,
                                            uncertain=self.uncertain,
                                            spills=self.spills,
                                            model_time_step=self.time_step)
        self.logger.debug("{0._pid} setup_model_run complete for: "
                          "{0.name}".format(self))

    def post_model_run(self):
        '''
        A place where the model goes through all collections and calls
        post_model_run if the object has it.
        '''
        for env in self.environment:
            env.post_model_run()
        for mov in self.movers:
            if mov.on:
                mov.post_model_run()
        for out in self.outputters:
            if out.on:
                out.post_model_run()
        for wea in self.weatherers:
            if wea.on:
                wea.post_model_run()

    def setup_time_step(self):
        '''
        sets up everything for the current time_step:
        '''
        # initialize movers differently if model uncertainty is on
        for m in self.movers:
            for sc in self.spills.items():
                m.prepare_for_model_step(sc, self.time_step, self.model_time)

        for w in self.weatherers:
            for sc in self.spills.items():
                # maybe we will setup a super-sampling step here???
                w.prepare_for_model_step(sc, self.time_step, self.model_time)

        for environment in self.environment:
            environment.prepare_for_model_step(self.model_time)

        for outputter in self.outputters:
            outputter.prepare_for_model_step(self.time_step, self.model_time)

    def move_elements(self):
        '''
        Moves elements:
         - loops through all the movers. and moves the elements
         - sets new_position array for each spill
         - calls the beaching code to beach the elements that need beaching.
         - sets the new position
        '''
        for sc in self.spills.items():
            if sc.num_released > 0:  # can this check be removed?

                # possibly refloat elements
                self.map.refloat_elements(sc, self.time_step)

                # reset next_positions
                (sc['next_positions'])[:] = sc['positions']

                # loop through the movers
                for m in self.movers:
                    delta = m.get_move(sc, self.time_step, self.model_time)
                    sc['next_positions'] += delta

                self.map.beach_elements(sc)

                # let model mark these particles to be removed
                tbr_mask = sc['status_codes'] == oil_status.off_maps
                sc['status_codes'][tbr_mask] = oil_status.to_be_removed

                substances = sc.get_substances(False)
                if len(substances)>0:
                    self._update_fate_status(sc)

                # the final move to the new positions
                (sc['positions'])[:] = sc['next_positions']

    def _update_fate_status(self, sc):
        '''
        WeatheringData used to perform this operation in weather_elements;
        however, WeatheringData is one of the objects in weatherers collection
        so just let model do this for now. Eventually, we want to get rid
        of 'fate_status' array and only manipulate 'status_codes'. Until then,
        update fate_status in move_elements
        '''
        if 'fate_status' in sc:
            non_w_mask = sc['status_codes'] == oil_status.on_land
            sc['fate_status'][non_w_mask] = fate.non_weather

            w_mask = ((sc['status_codes'] == oil_status.in_water)
                 & ~(sc['fate_status'] & fate.skim == fate.skim)
                 & ~(sc['fate_status'] & fate.burn == fate.burn)
                 & ~(sc['fate_status'] & fate.disperse == fate.disperse))

            surf_mask = np.logical_and(w_mask, sc['positions'][:, 2] == 0)
            subs_mask = np.logical_and(w_mask, sc['positions'][:, 2] > 0)

            sc['fate_status'][surf_mask] = fate.surface_weather
            sc['fate_status'][subs_mask] = fate.subsurf_weather

    def weather_elements(self):
        '''
        Weathers elements:

        - loops through all the weatherers, passing in the spill_container
          and the time range
        - a weatherer modifies the data arrays in the spill container, so a
          particular time range should not be run multiple times.  It is
          expected that we are processing a sequence of contiguous time ranges.
        - Note: If there are multiple sequential weathering processes, some
          inaccuracy could occur.  A proposed solution is to
          'super-sample' the model time step so that it will be replaced
          with many smaller time steps.  We'll have to see if this pans
          out in practice.

        '''
        if len(self.weatherers) == 0:
            # if no weatherers then mass_components array may not be defined
            return

        for sc in self.spills.items():
            # elements may have beached to update fate_status

            sc.reset_fate_dataview()

            for w in self.weatherers:
                for model_time, time_step in self._split_into_substeps():
                    # change 'mass_components' in weatherer
                    w.weather_elements(sc, time_step, model_time)

    def _split_into_substeps(self):
        '''
        :return: sequence of (datetime, timestep)
         (Note: we divide evenly on second boundaries.
                   Thus, there will likely be a remainder
                   that needs to be included.  We include
                   this remainder, which results in
                   1 more sub-step than we requested.)
        '''
        time_step = int(self._time_step)
        sub_step = time_step / self.weathering_substeps

        indexes = [idx for idx in range(0, time_step + 1, sub_step)]
        res = [(idx, next_idx - idx)
               for idx, next_idx in zip(indexes, indexes[1:])]

        if sum(res[-1]) < time_step:
            # collect the remaining slice
            res.append((sum(res[-1]), time_step % sub_step))

        res = [(self.model_time + timedelta(seconds=idx), delta)
               for idx, delta in res]

        return res

    def step_is_done(self):
        '''
        Loop through movers and weatherers and call model_step_is_done

        Remove elements that marked for removal

        Output data
        '''
        for mover in self.movers:
            for sc in self.spills.items():
                mover.model_step_is_done(sc)

        for w in self.weatherers:
            for sc in self.spills.items():
                w.model_step_is_done(sc)

        for outputter in self.outputters:
            outputter.model_step_is_done()

        for sc in self.spills.items():
            '''
            removes elements with oil_status.to_be_removed
            '''
            sc.model_step_is_done()

            # age remaining particles
            sc['age'][:] = sc['age'][:] + self.time_step

    def write_output(self, valid, messages=None):
        output_info = {'step_num': self.current_time_step}

        for outputter in self.outputters:
            if self.current_time_step == self.num_time_steps - 1:
                output = outputter.write_output(self.current_time_step, True)
            else:
                output = outputter.write_output(self.current_time_step)

            if output is not None:
                output_info[outputter.__class__.__name__] = output

        if len(output_info) > 1:
            # append 'valid' flag to output
            output_info['valid'] = valid

        return output_info

    def step(self):
        '''
        Steps the model forward (or backward) in time. Needs testing for
        hind casting.
        '''
        isvalid = True
        for sc in self.spills.items():
            # Set the current time stamp only after current_time_step is
            # incremented and before the output is written. Set it to None here
            # just so we're not carrying around the old time_stamp
            sc.current_time_stamp = None

        if self.current_time_step == -1:
            # that's all we need to do for the zeroth time step
            self.setup_model_run()

            # let each object raise appropriate error if obj is incomplete
            # validate and send validation flag if model is invalid
            (msgs, isvalid) = self.check_inputs()
            if not isvalid:
                raise RuntimeError("Setup model run complete but model "
                                   "is invalid", msgs)
            # (msgs, isvalid) = self.validate()
            # if not isvalid:
            #    raise StopIteration("Setup model run complete but model "
            #                        "is invalid", msgs)

        elif self.current_time_step >= self._num_time_steps - 1:
            # _num_time_steps is set when self.time_step is set. If user does
            # not specify time_step, then setup_model_run() automatically
            # initializes it. Thus, do StopIteration check after
            # setup_model_run() is invoked
            self.post_model_run()
            raise StopIteration("Run complete for {0}".format(self.name))

        else:
            self.setup_time_step()
            self.move_elements()
            self.weather_elements()
            self.step_is_done()

        self.current_time_step += 1

        # this is where the new step begins!
        # the elements released are during the time period:
        #    self.model_time + self.time_step
        # The else part of the loop computes values for data_arrays that
        # correspond with time_stamp:
        #    self.model_time + self.time_step
        # This is the current_time_stamp attribute of the SpillContainer
        #     [sc.current_time_stamp for sc in self.spills.items()]
        for sc in self.spills.items():
            sc.current_time_stamp = self.model_time

            # release particles for next step - these particles will be aged
            # in the next step
            num_released = sc.release_elements(self.time_step, self.model_time)

            # initialize data - currently only weatherers do this so cycle
            # over weatherers collection - in future, maybe movers can also do
            # this
            if num_released > 0:
                for item in self.weatherers:
                    item.initialize_data(sc, num_released)

            self.logger.debug("{1._pid} released {0} new elements for step:"
                              " {1.current_time_step} for {1.name}".
                              format(num_released, self))

        # cache the results - current_time_step is incremented but the
        # current_time_stamp in spill_containers (self.spills) is not updated
        # till we go through the prepare_for_model_step
        self._cache.save_timestep(self.current_time_step, self.spills)
        output_info = self.write_output(isvalid)

        self.logger.debug('{0._pid} '
                          'Completed step: {0.current_time_step} for {0.name}'
                          .format(self))

        return output_info

    def __iter__(self):
        '''
        Rewinds the model and returns itself so it can be iterated over.
        '''
        self.rewind()

        return self

    def next(self):
        '''
        (This method satisfies Python's iterator and generator protocols)

        :return: the step number
        '''
        try:
            return self.step()
        except StopIteration:
            self.post_model_run()
            raise

    def full_run(self, rewind=True):
        '''
        Do a full run of the model.

        :param rewind=True: whether to rewind the model first -- if set to
            false, model will be run from the current step to the end
        :returns: list of outputter info dicts
        '''
        if rewind:
            self.rewind()

        # run the model
        output_data = []
        while True:
            try:
                results = self.step()
                self.logger.info(results)

                output_data.append(results)
            except StopIteration:
                self.post_model_run()
                self.logger.info('Run Complete: Stop Iteration')
                break

        return output_data

    def _add_to_environ_collec(self, obj_added):
        '''
        if an environment object exists in obj_added, but not in the Model's
        environment collection, then add it automatically.
        todo: maybe we don't want to do this - revisit this requirement
        '''
        if hasattr(obj_added, 'wind') and obj_added.wind is not None:
            if obj_added.wind.id not in self.environment:
                self.environment += obj_added.wind

        if hasattr(obj_added, 'tide') and obj_added.tide is not None:
            if obj_added.tide.id not in self.environment:
                self.environment += obj_added.tide

        if hasattr(obj_added, 'waves') and obj_added.waves is not None:
            if obj_added.waves.id not in self.environment:
                self.environment += obj_added.waves

        if hasattr(obj_added, 'water') and obj_added.water is not None:
            if obj_added.water.id not in self.environment:
                self.environment += obj_added.water
        if hasattr(obj_added, 'current') and obj_added.current is not None:
            if obj_added.current.id not in self.environment:
                self.environment += obj_added.current

    def _callback_add_mover(self, obj_added):
        'Callback after mover has been added'
        self._add_to_environ_collec(obj_added)
        self.rewind()  # rewind model if a new mover is added

    def _callback_add_outputter(self, obj_added):
        'Callback after outputter has been added'
        # hook up the cache
        obj_added.cache = self._cache

    def _callback_add_weatherer_env(self, obj_added):
        '''
        Callback after weatherer/environment object has been added. 'waves'
        environment object contains 'wind' and 'water' so add those to
        environment collection and the 'water' attribute.
        todo: simplify this
        '''
        self._add_to_environ_collec(obj_added)
        self.rewind()  # rewind model if a new weatherer is added

    def _callback_add_spill(self, obj_added):
        self.rewind()

    def __eq__(self, other):
        check = super(Model, self).__eq__(other)
        if check:
            # also check the data in ordered collections
            if not isinstance(self.spills, other.spills.__class__):
                return False

            if self.spills != other.spills:
                return False

        return check

    def __ne__(self, other):
        return not self == other

    '''
    Following methods are for saving a Model instance or creating a new
    model instance from a saved location
    '''

    def spills_update_from_dict(self, value):
        'invoke SpillContainerPair().update_from_dict'
        # containers don't need to be serializable; however, it was easiest to
        # put an update_from_dict method in the SpillContainerPair. Keep the
        # interface for this the same, so make it a dict
        return self.spills.update_from_dict({'spills': value})

    def _create_zip(self, saveloc, name):
        '''
        create a zipfile and update saveloc to point to it. This is now
        passed down to all the objects contained within the Model so they can
        save themselves to zipfile
        '''
        if self.zipsave:
            if name is None and self.name is None:
                z_name = 'Model.zip'
            else:
                z_name = name if name is not None else self.name + '.zip'

            # create the zipfile and update saveloc - _json_to_saveloc checks
            # to see if saveloc is a zipfile
            saveloc = os.path.join(saveloc, z_name)
            z = zipfile.ZipFile(saveloc, 'w',
                                compression=zipfile.ZIP_DEFLATED,
                                allowZip64=self._allowzip64)
            z.close()

        return saveloc

    def save(self, saveloc='.', refs=None, overwrite=True):
        '''
        save the model state in saveloc. If self.zipsave is True, then a
        zip archive is created and model files are saved to the archive.

        This overrides the base class save(). Model contains collections and
        model must invoke save for each object in the collection. It must also
        save the data in the SpillContainer's if it is a mid-run save.

        :param saveloc: zip archive or a valid directory. Model files are
            either persisted here or a new model is re-created from the files
            stored here. The files are clobbered when save() is called.
        :type saveloc: A path as a string or unicode

        :param filename=None: If data is saved to zipfile (default behavior), then
            this is filename of zip file. For a zipfile, the model's state is
            always contained in Model.json. If zipsave is False, then model's
            json is stored in filename.json
        :type filename: str

        :param references: dict of references mapping 'id' to a string used for
            the reference. The value could be a unique integer or it could be
            a filename. It is upto the creator of the reference list to decide
            how to reference a nested object.

        :returns: references
        '''
        json_, saveloc, refs = super(Model, self).save(saveloc=saveloc, refs=refs, overwrite=overwrite)

        #because a model can be saved mid-run and the SpillContainer data required to reload
        #is not covered in the schema, need to add the SpillContainer data afterwards
        if self.current_time_step > -1:
            '''
            hard code the filename - can make this an attribute if user wants
            to change it - but not sure if that will ever be needed?
            '''
            self._save_spill_data(saveloc, 'spills_data_arrays.nc')

        return json_, saveloc, refs

    def _save_spill_data(self, saveloc, nc_filename):
        """
        save the data arrays for current timestep to NetCDF
        If saveloc is zipfile, then move NetCDF to zipfile
        """
        nc_out = NetCDFOutput(nc_filename, which_data='all', cache=self._cache)
        nc_out.prepare_for_model_run(model_start_time=self.start_time,
                                     uncertain=self.uncertain,
                                     spills=self.spills)
        nc_out.write_output(self.current_time_step)

        if isinstance(saveloc, zipfile.ZipFile):
            saveloc.write(nc_filename, nc_filename)
            if self.uncertain:
                u_file = nc_out.uncertain_filename
                saveloc.write(u_file, os.path.split(u_file)[1])
        elif zipfile.is_zipfile(saveloc):
            with zipfile.ZipFile(saveloc, 'a',
                                 compression=zipfile.ZIP_DEFLATED,
                                 allowZip64=allowzip64) as z:
                z.write(nc_filename, nc_filename)
                if self.uncertain:
                    u_file = nc_out.uncertain_filename
                    z.write(u_file, os.path.split(u_file)[1])
        if self.uncertain:
            os.remove(u_file)
        os.remove(nc_filename)

    @classmethod
    def load(cls, saveloc='.', filename=None, refs=None):
        '''
        Load an instance of this class from an archive or folder

        :param saveloc: Can be an open zipfile.ZipFile archive, a folder, or a
                        filename. If it is an open zipfile or folder, it must
                        contain a ``.json`` file that describes an instance of
                        this object type. If ``filename`` is not specified, it
                        will load the first instance of this object discovered.
                        If a filename, it must be a zip archive or a json file
                        describing an object of this type.

        :param filename: If saveloc is an open zipfile or folder, this indicates
                         the name of the file to be loaded. If saveloc is a filename,
                         is parameter is ignored.

        :param refs: A dictionary of id -> object instances that will be used to
                     complete references, if available.
        '''

        new_model = super(Model, cls).load(saveloc=saveloc, filename=filename, refs=refs)
        # Since the model may have saved mid-run, need to try and load spill data
        # new_model._load_spill_data(saveloc, filename, 'spills_data_arrays.nc')

        return new_model

    def _load_spill_data(self, saveloc, filename, nc_file):
        """
        load NetCDF file and add spill data back in - designed for savefiles
        """
        spill_data = None
        if isinstance(saveloc, zipfile.ZipFile):
            #saveloc is an open zipfile instance
            if nc_file not in saveloc.namelist():
                return

            spill_data = saveloc.extract(nc_file)
            if self.uncertain:
                spill_data_fname, ext = os.path.splitext(nc_file)
                ufname = '{0}_uncertain{1}'.format(spill_data_fname, ext)
                u_spill_data = saveloc.extract(ufname)
        else:
            if os.path.isdir(saveloc):
                if filename:
                    saveloc = os.path.join(saveloc, filename)
                    with zipfile.ZipFile(saveloc, 'r') as z:
                        if nc_file not in z.namelist():
                            return
                        spill_data = z.extract(nc_file)
                        if self.uncertain:
                            spill_data_fname, ext = os.path.splitext(nc_file)
                            fname = '{0}_uncertain{1}'.format(spill_data_fname, ext)
                            u_spill_data = z.extract(fname)

        if spill_data is None:
            return
        array_types = set()

        for m in self.movers:
            array_types.update(m.array_types)

        for w in self.weatherers:
            array_types.update(w.array_types)

        for sc in self.spills.items():
            sc.prepare_for_model_run(array_types)
            if sc.uncertain:
                (data, weather_data) = NetCDFOutput.read_data(u_spill_data,
                                                              time=None,
                                                              which_data='all')
            else:
                (data, weather_data) = NetCDFOutput.read_data(spill_data,
                                                              time=None,
                                                              which_data='all')

            sc.current_time_stamp = data.pop('current_time_stamp').item()
            sc._data_arrays = data
            sc.mass_balance = weather_data

        # delete file after data is loaded - since no longer needed
        os.remove(spill_data)
        if self.uncertain:
            os.remove(u_spill_data)

    def merge(self, model):
        '''
        merge 'model' into self
        '''
        for attr in self.__dict__:
            if (getattr(self, attr) is None and
                    getattr(model, attr) is not None):
                setattr(self, attr, getattr(model, attr))

        # update orderedcollections
        for oc in self._oc_list:
            my_oc = getattr(self, oc)
            new_oc = getattr(model, oc)
            for item in new_oc:
                if item not in my_oc:
                    my_oc += item

        # update forecast spills in SpillContainerPair
        # Uncertain spills automatically be created if uncertainty is on
        for spill in model.spills:
            if spill not in self.spills:
                self.spills += spill

        # force rewind after merge?
        self.rewind()

    def check_inputs(self):
        '''
        check the user inputs before running the model
        raise an exception if user can't run the model
        todo: check if all spills start after model ends
        '''
        (msgs, isvalid) = self.validate()

        someSpillIntersectsModel = False
        num_spills = len(self.spills)
        if num_spills == 0:
            msg = '{0} contains no spills'.format(self.name)
            self.logger.warning(msg)
            msgs.append(self._warn_pre + msg)

        num_spills_on = 0
        for spill in self.spills:
            msg = None
            if spill.on:
                num_spills_on += 1
                if spill.release_time < self.start_time + self.duration:
                    someSpillIntersectsModel = True

                if spill.release_time > self.start_time:
                    msg = ('{0} has release time after model start time'.
                           format(spill.name))
                    self.logger.warning(msg)

                    msgs.append(self._warn_pre + msg)

                elif spill.release_time < self.start_time:
                    msg = ('{0} has release time before model start time'
                           .format(spill.name))
                    self.logger.error(msg)

                    msgs.append('error: {}: {}'
                                .format(self.__class__.__name__, msg))
                    isvalid = False

                if spill.substance is not None:
                    # min_k1 = spill.substance.get('pour_point_min_k')
                    pour_point = spill.substance.pour_point()

                    if spill.water is not None:
                        water_temp = spill.water.get('temperature')

                        if water_temp < pour_point[0]:
                            msg = ('The water temperature, {0} K, '
                                   'is less than the minimum pour point '
                                   'of the selected oil, {1} K.  '
                                   'The results may be unreliable.'
                                   .format(water_temp, pour_point[0]))

                            self.logger.warning(msg)
                            msgs.append(self._warn_pre + msg)

                        rho_h2o = spill.water.get('density')
                        rho_oil = spill.substance.density_at_temp(water_temp)

                        if np.any(rho_h2o < rho_oil):
                            msg = ('Found particles with '
                                   'relative_buoyancy < 0. Oil is a sinker')
                            raise GnomeRuntimeError(msg)

        if num_spills_on > 0 and not someSpillIntersectsModel:
            if num_spills > 1:
                msg = ('All of the spills are released after the '
                       'time interval being modeled.')
            else:
                msg = ('The spill is released after the time interval '
                       'being modeled.')

            self.logger.warning(msg)  # for now make this a warning
            # self.logger.error(msg)
            msgs.append('warning: ' + self.__class__.__name__ + ': ' + msg)
            # isvalid = False

        return (msgs, isvalid)

    def validate(self):
        '''
        invoke validate for all gnome objects contained in model
        todo: should also check wind, water, waves are defined if weatherers
        are defined
        '''
        # since model does not contain wind, waves, water attributes, no need
        # to call base class method - model requires following only if an
        # object in collection requires it
        env_req = set()
        msgs = []
        isvalid = True
        for oc in self._oc_list:
            for item in getattr(self, oc):
                # if item is not on, no need to validate it
                if hasattr(item, 'on') and not item.on:
                    continue

                # validate item
                (msg, i_isvalid) = item.validate()
                if not i_isvalid:
                    isvalid = i_isvalid

                msgs.extend(msg)

                # add to set of required env objects if item's
                # make_default_refs is True
                if item.make_default_refs:
                    for attr in ('wind', 'water', 'waves'):
                        if hasattr(item, attr):
                            env_req.update({attr})

        # ensure that required objects are present in environment collection
        if len(env_req) > 0:
            (ref_msgs, ref_isvalid) = \
                self._validate_env_coll(env_req)
            if not ref_isvalid:
                isvalid = ref_isvalid
            msgs.extend(ref_msgs)

        return (msgs, isvalid)

    def _validate_env_coll(self, refs, raise_exc=False):
        '''
        validate refs + log warnings or raise error if required refs not found.
        If refs is None, model must query its weatherers/movers/environment
        collections to figure out what objects it needs to have in environment.
        '''
        msgs = []
        isvalid = True

        if refs is None:
            # need to go through orderedcollections to see if water, waves
            # and wind refs are required
            raise NotImplementedError("validate_refs() incomplete")

        for ref in refs:
            obj = self.find_by_attr('_ref_as', ref, self.environment)
            if obj is None:
                msg = ("{0} not found in environment collection".
                       format(ref))
                if raise_exc:
                    raise ReferencedObjectNotSet(msg)
                else:
                    self.logger.warning(msg)
                    msgs.append(self._warn_pre + msg)
                    isvalid = False

        return (msgs, isvalid)

    def set_make_default_refs(self, value):
        '''
        make default refs for all items in ('weatherers', 'movers',
        'environment') collections
        '''
        for attr in ('weatherers', 'movers', 'environment'):
            oc = getattr(self, attr)
            for item in oc:
                item.make_default_refs = value

    def list_spill_properties(self):
        '''
        Convenience method to list properties of a spill that
        can be retrived using get_spill_property

        '''

        return self.spills.items()[0].data_arrays.keys()

    def get_spill_property(self, prop_name, ucert=0):
        '''
        Convenience method to allow user to look up properties of a spill.
        User can specify ucert as 'ucert' or 1
        '''
        if ucert == 'ucert':
            ucert = 1
        return self.spills.items()[ucert][prop_name]

    def get_spill_data(self, target_properties, conditions, ucert=0):
        """
        Convenience method to allow user to write an expression to filter
        raw spill data

        Example case::

          get_spill_data('position && mass',
                         'position > 50 && spill_num == 1 || status_codes == 1'
                         )

        WARNING: EXPENSIVE! USE AT YOUR OWN RISK ON LARGE num_elements!

        Example spill element properties are below. This list may not contain
        all properties tracked by the model.

        'positions', 'next_positions', 'last_water_positions', 'status_codes',
        'spill_num', 'id', 'mass', 'age'

        """

        if ucert == 'ucert':
            ucert = 1

        def elem_val(prop, index):
            '''
            Gets the column containing the information on one element
            '''
            val = self.spills.items()[ucert].data_arrays[prop][index]
            return val

        def test_phrase(phrase):
            for sub_cond in phrase:
                cond = sub_cond.rsplit()
                prop_val = elem_val(cond[0], i)
                op = cond[1]
                test_num = cond[2]
                if test(prop_val, op, test_num):
                    return True

            return False

        def test(elem_value, op, test_val):
            if op in {'<', '<=', '>', '>=', '=='}:
                return eval(str(int(elem_value)) + op + test_val)

        def num(s):
            try:
                return int(s)
            except ValueError:
                return float(s)

        conditions = conditions.rsplit('&&')
        conditions = [str(cond).rsplit('||') for cond in conditions]

        sc = self.spills.items()[ucert]
        result = {}

        for t in target_properties:
            result[t] = []

        for i in range(0, len(sc)):
            test_result = True

            for phrase in conditions:
                if not test_phrase(phrase):
                    test_result = False
                    break

            if test_result:
                for k in result.keys():
                    n = elem_val(k, i)
                    result[k].append(n)

        return result

    def add_env(self, env, quash=False):
        for item in env:
            if not quash:
                self.environment.add(item)
            else:
                for o in self.environment:
                    if o.__class__ == item.__class__:
                        idx = self.environment.index(o)
                        self.environment[idx] = item
                        break
                else:
                    self.environment.add(item)

#     def env_from_netCDF(self, filename=None, dataset=None, grid_file=None, data_file=None, _cls_list=None, **kwargs):
#         def attempt_from_netCDF(cls, **kwargs):
#             obj = None
#             try:
#                 obj = c.from_netCDF(filename=filename, dataset=dataset, grid_file=grid_file, data_file=data_file, **clskwargs)
#             except Exception as e:
#                 self.logger.warn('''Class {0} could not be constituted from netCDF file
#                                         Exception: {1}'''.format(c.__name__, e))
#             return obj
#
#         from gnome.utilities.file_tools.data_helpers import _get_dataset
#         from gnome.environment.environment_objects import GriddedProp, GridVectorProp
#         from gnome.environment import PyGrid
#
#         if filename is not None:
#             data_file = filename
#             grid_file = filename
#
#         ds = None
#         dg = None
#         if dataset is None:
#             if grid_file == data_file:
#                 ds = dg = _get_dataset(grid_file)
#             else:
#                 ds = _get_dataset(data_file)
#                 dg = _get_dataset(grid_file)
#         else:
#             if grid_file is not None:
#                 dg = _get_dataset(grid_file)
#             else:
#                 dg = dataset
#             ds = dataset
#         dataset = ds
#
#         grid = kwargs.pop('grid', None)
#         if grid is None:
#             grid = PyGrid.from_netCDF(filename=filename, dataset=dg, **kwargs)
#             kwargs['grid'] = grid
#         scs = copy.copy(Environment._subclasses) if _cls_list is None else _cls_list
#         for c in scs:
#             if issubclass(c, (GriddedProp, GridVectorProp)) and not any([isinstance(o, c) for o in self.environment]):
#                 clskwargs = copy.copy(kwargs)
#                 obj = None
#                 try:
#                     req_refs = c._req_refs
#                 except AttributeError:
#                     req_refs = None
#
#                 if req_refs is not None:
#                     for ref, klass in req_refs.items():
#                         for o in self.environment:
#                             if isinstance(o, klass):
#                                 clskwargs[ref] = o
#                                 break
#                         if ref in clskwargs.keys():
#                             continue
#                         else:
#                             obj = attempt_from_netCDF(c, filename=filename, dataset=dataset, grid_file=grid_file, data_file=data_file, **clskwargs)
#                             clskwargs[ref] = obj
#                             self.environment.append(obj)
#
#                 obj = attempt_from_netCDF(c, filename=filename, dataset=dataset, grid_file=grid_file, data_file=data_file, **clskwargs)
#                 if obj is not None:
#                     self.environment.append(obj)
#
#     def ice_env_from_netCDF(self, filename=None, **kwargs):
#         cls_list = Environment._subclasses
#         ice_cls_list = self.find_by_attr('_ref_as', 'ice_aware', cls_list, allitems=True)
# #         for c in cls_list:
# #             if hasattr(c, '_ref_as'):
# #                 if ((not isinstance(c._ref_as, basestring) and
# #                         any(['ice_aware' in r for r in c._ref_as])) or
# #                         'ice_aware' in c._ref_as):
# #                     ice_cls_list.append(c)
#         self.env_from_netCDF(filename=filename, _cls_list=ice_cls_list, **kwargs)
