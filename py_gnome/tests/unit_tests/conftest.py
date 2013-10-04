"""
Defines test fixtures as well as functions that are used by multiple tests
and test modules

The scope="module" on the fixtures ensures it is only invoked once per test module
"""

import os
from datetime import datetime, timedelta
import copy

import numpy as np
import pytest

import gnome
from gnome import basic_types


def mock_append_data_arrays(array_types, num_elements, data_arrays={}):
    """
    takes array_types desired by test function and number of elements
    to be initialized. For testing element_type functionality with a
    SpillContainer. Mocks the functionality of
    SpillContainer()._append_data_arrays(..)

    :param array_types: dict of array_types used to initialize data_arrays.
        If data_arrays is empty, then use the initialize_null() method of
        each array_type to first initialize it, then append to it.
    :param num_elements: number of elements to be released. Append
        'num_elements' to data_arrays
    :param data_arrays: empty by default. But this could contain a dictionary
        of data_arrays. In this case, just initialize each array_type for
        'num_elements' and append it to numpy array in dict.
        Function makes a deepcopy of data_arrays, appends to the copied dict,
        and returns this copy after appending num_elements to numpy arrays.
        SpillContainer would be managing this dict in the real use case
    """
    array_types = dict(array_types)
    data_arrays = copy.deepcopy(data_arrays)

    for name, array_type in array_types.iteritems():
        # initialize null arrays so they exist before appending
        if name not in data_arrays:
            data_arrays[name] = array_type.initialize_null()

        arr = array_type.initialize(num_elements)
        data_arrays[name] = np.r_[data_arrays[name], arr]

    return data_arrays


@pytest.fixture(scope='module')
def invalid_rq():
    """
    Provides invalid (r,theta) values for the transforms for wind
    and current from (r,theta) to (u,v)

    Transforms require r > 0, and 0 <= theta <=360. This returns bad values
    for (r,q)

    :returns: dictionary containing 'rq' which is numpy array of '(r,q)' values
    that violate above requirement
    """

    bad_rq = np.array([(-1, 0), (1, -1), (1, 361)], dtype=np.float64)
    return {'rq': bad_rq}

# use this for wind and current deterministic (r,theta)

rq = np.array([
    (1, 0),
    (1, 45),
    (1, 90),
    (1, 120),
    (1, 180),
    (1, 270),
    ], dtype=np.float64)


@pytest.fixture(scope='module')
def rq_wind():
    """
    (r,theta) setup for wind on a unit circle for 0,90,180,270 deg

    :returns: dictionary containing 'rq' and 'uv' which is numpy array of (r,q)
        values and the corresponding (u,v)
    """

    uv = np.array([
        (0, -1),
        (-1. / np.sqrt(2), -1. / np.sqrt(2)),
        (-1, 0),
        (-np.sqrt(3) / 2, .5),
        (0, 1),
        (1, 0),
        ], dtype=np.float64)
    return {'rq': rq, 'uv': uv}


@pytest.fixture(scope='module')
def rq_curr():
    """
    (r,theta) setup for current on a unit circle

    :returns: dictionary containing 'rq' and 'uv' which is numpy array of (r,q)
        values and the corresponding (u,v)
    """

    uv = np.array([
        (0, 1),
        (1. / np.sqrt(2), 1. / np.sqrt(2)),
        (1, 0),
        (np.sqrt(3) / 2, -.5),
        (0, -1),
        (-1, 0),
        ], dtype=np.float64)
    return {'rq': rq, 'uv': uv}


@pytest.fixture(scope='module')
def rq_rand():
    """
    (r,theta) setup randomly generated array of length = 3. The uv = None,
    only (r,theta) are randomly generated: 'r' is between (.5,len(rq)) and
    'theta' is between (0,360)

    :returns: dictionary containing randomly generated 'rq', which is numpy
        array of (r,q) values
    """

    rq = np.zeros((5, 2), dtype=np.float64)

    # cannot be 0 magnitude vector - let's just make it from 0.5

    rq[:, 0] = np.random.uniform(.5, len(rq), len(rq))

    rq[:, 1] = np.random.uniform(0, 360, len(rq))
    return {'rq': rq}


@pytest.fixture(scope='module')
def wind_circ(rq_wind):
    """
    Create Wind object using the time series given by test fixture 'rq_wind'
    'wind' object where timeseries is defined as:
         - 'time' defined by: [datetime(2012,11,06,20,10+i,30)
            for i in range(len(dtv_rq))]
         - 'value' defined by: (r,theta) values ferom rq_wind fixtures, units
            are 'm/s'

    :returns: a dict containing following three keys: 'wind', 'rq', 'uv'
              'wind' object, timeseries in (r,theta) format 'rq', timeseries in
              (u,v) format 'uv'.
    """

    from gnome import environment
    dtv_rq = np.zeros((len(rq_wind['rq']), ),
                      dtype=basic_types.datetime_value_2d).view(dtype=np.recarray)
    dtv_rq.time = [datetime(
        2012,
        11,
        06,
        20,
        10 + i,
        30,
        ) for i in range(len(dtv_rq))]
    dtv_rq.value = rq_wind['rq']
    dtv_uv = np.zeros((len(dtv_rq), ),
                   dtype=basic_types.datetime_value_2d).view(dtype=np.recarray)
    dtv_uv.time = dtv_rq.time
    dtv_uv.value = rq_wind['uv']
    wm = environment.Wind(timeseries=dtv_rq, format='r-theta',
                          units='meter per second')
    return {'wind': wm, 'rq': dtv_rq, 'uv': dtv_uv}


@pytest.fixture(scope='module')
def sample_model():
    """
    sample model with no outputter and no spills. Use this as a template for
    fixtures to add spills
    Uses:
        sample_data/MapBounds_Island.bna
        Contains: gnome.movers.SimpleMover(velocity=(1.0, -1.0, 0.0))
        duration is 1 hour with 15min intervals so 5 timesteps total,
        including initial condition,
        model is uncertain and cache is not enabled
        No spills or outputters defined

    To use:
        add a spill and run

    :returns: It returns a dict -
        {'model':model,
         'release_start_pos':start_points,
         'release_end_pos':end_points}
        The release_start_pos and release_end_pos can be used by test to define
        the spill's 'start_position' and 'end_position'
    """

    start_time = datetime(2012, 9, 15, 12, 0)

    # the image output map

    mapfile = os.path.join(os.path.dirname(__file__), '../sample_data',
                           'MapBounds_Island.bna')

    # the land-water map

    map_ = gnome.map.MapFromBNA(mapfile, refloat_halflife=06)  # seconds

    model = gnome.model.Model(
        time_step=timedelta(minutes=15),
        start_time=start_time,
        duration=timedelta(hours=1),
        map=map_,
        uncertain=True,
        cache_enabled=False,
        )

    model.movers += gnome.movers.SimpleMover(velocity=(1., -1., 0.0))

    model.uncertain = True

    start_points = np.zeros((3, ), dtype=np.float64)
    end_points = np.zeros((3, ), dtype=np.float64)

    start_points[:] = (-127.1, 47.93, 0)
    end_points[:] = (-126.5, 48.1, 0)

    return {'model': model, 'release_start_pos': start_points,
            'release_end_pos': end_points}
