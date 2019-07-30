"""Test module for data wranlging methods."""

from   anprx.preprocessing import wrangle_cameras
from   anprx.preprocessing import network_from_cameras
from   anprx.preprocessing import merge_cameras_network
from   anprx.preprocessing import camera_pairs_from_graph
from   anprx.preprocessing import map_nodes_cameras
from   anprx.preprocessing import wrangle_raw_anpr
from   anprx.compute       import trip_identification

import os
import numpy               as     np
import pandas              as     pd

"""
Test set 1 - assert:
    - Cameras 1 and 10 are merged (same location, same direction)
    - Cameras 1 and 9 are not merged (same location, different direction)
    - Camera 6 is dropped (is_carpark = 1)
    - Camera 7 is dropped (is_commissioned = 0)
    - Camera 8 is dropped (is_test = 1)
    - Cameras 2 and 3 see in both directions
    - Direction is inferred correctly
    - Address is extracted correctly
    - Road Category is extracted correctly
    - Resulting df has 6 rows
"""
raw_cameras_testset_1 = pd.DataFrame({
    'id'   : ['1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11'],
    'lat'  : [54.972017, 54.975509, 54.974499, 54.974612, 54.974181,
              54.90, 54.89, 54.88, 54.972017, 54.972017, 54.974612],
    'lon'  : [-1.631206, -1.628498, -1.627997, -1.637108, -1.659476,
              -1.60, -1.61, -1.67, -1.631206, -1.631206, -1.637108],
    'name' : ["CA" , "CB" , "CC", "CD", "CE", "CF", "CG",
              "Test", "CA2", "CA3", "No Direction"],
    'desc' : ["Westbound A186", "East/West Stanhope St A13",
              "North/South Diana St B1", "Beaconsfield St Southbound A27",
              "Northbound B1305 Condercum Rd", "Car park in",
              "Disabled", "Camera Test",
              "Eastbound A186", "Westbound A186", "Directionless"],
    'is_commissioned' : [1,1,1,1,1,1,0,1,1,1,1]
})

raw_nodes_testset = pd.DataFrame({
    'id'   : ['1', '2', '3', '4', '5', '6'],
    'lat'  : [54.971859, 54.975552, 54.974684, 54.974896, 54.970954, 54.973475],
    'lon'  : [-1.630304, -1.628980, -1.627947, -1.637061, -1.660613,-1.621355],
    'name' : ["NA" , "NB" , "NC", "ND", "NE", "NF"],
    'desc' : ["Westbound A186", "Eastbound Stanhope St A13",
              "Southbound Diana St B1", "Beaconsfield St Southbound A27",
              "Northbound B1305 Condercum Rd", "St James Av A98 Northbound"]
})

#   Test raw ANPR dataset
#
#   vehicle | camera | timestamp | confidence
#   ------------------------------------------
#   AA00AAA |   1    |     0     |    90        (Camera 1 shd change to 1-10)
#   AA00AAA |   1    |     5     |    92        (duplicate)
#   AA00AAA |   1    |     6     |    91        (duplicate x2)
#   AA00AAA |   2    |     90    |    84        (valid step)
#   AA00AAA |   1    |    1e6    |    83        (new trip)
#   AA00AAA |   2    |  1e6 +90  |    98        (valid step)
#   ------------------------------------------
#   AA11AAA |   3    |     0     |    82        (ok)
#   AA11AAA |   10   |     100   |    96        (valid step, camera 10 -> 1-10)
#   AA11AAA |   5    |     101   |    84        (too fast, should be filtered)
#   AA11AAA |   2    |     105   |    88        (too fast x2)
#   AA11AAA |   4    |     200   |    84        (valid step)
#   AA11AAA |   3    |     1e5   |    92        (new trip)
#   ------------------------------------------
#   AA22AAA |   4    |     0     |    90        (ok)
#   AA22AAA |   4    |    1500   |    92        (new trip, same camera)
#   AA22AAA |   3    |    1600   |    84        (valid step)
#   AA22AAA |   3    |    1601   |    83        (duplicate)
#   AA22AAA |   2    |    1700   |    35        (low confidence)
#   ------------------------------------------
#   np.nan  |   2    |     0     |    75        (nan license plate)

baseline_date = pd.to_datetime('21000101', format='%Y%m%d', errors='coerce')

raw_anpr_testset_v1 = pd.DataFrame({
    'vehicle'    : ['AA00AAA'] * 6,
    'camera'     : ['1', '1', '1', '2', '1', '2'],
    'timestamp'  : [0.0, 5.0, 6.0, 90.0, 1e6, 1e6 + 90],
    'confidence' : [90 , 92, 91, 84 , 83, 98]
})

raw_anpr_testset_v2 = pd.DataFrame({
    'vehicle'    : ['AA11AAA'] * 6,
    'camera'     : ['3', '10', '5', '2', '4', '3'],
    'timestamp'  : [0.0, 100.0, 101.0, 105.0, 200.0, 1e5],
    'confidence' : [82 , 96, 84, 84, 88, 92]
})

raw_anpr_testset_v3 = pd.DataFrame({
    'vehicle'    : ['AA22AAA'] * 5,
    'camera'     : ['4', '4', '3', '3', '2'],
    'timestamp'  : [0.0, 1500.0, 1600.0, 1601.0, 1700.0],
    'confidence' : [90 , 92, 84 , 83, 35]
})

raw_anpr_testset_v4 = pd.DataFrame({
    'vehicle'    : [np.nan],
    'camera'     : ['2'],
    'timestamp'  : [0.0],
    'confidence' : [75.0]
})

raw_anpr_testset = pd.concat([raw_anpr_testset_v1, raw_anpr_testset_v2,
                              raw_anpr_testset_v3, raw_anpr_testset_v4],
                             axis = 0)\
                     .reset_index(drop = True)
#
raw_anpr_testset['timestamp'] = raw_anpr_testset['timestamp']\
    .apply(lambda x: baseline_date + pd.to_timedelta(x, unit = 's'))

#   Expected Trips - Vehicle 1: 'AA00AAA'
#
#   vehicle | ori | dst | to | td | tt | d_ori | d_dst | trip | step | trip_len
#   ----------------------------------------------------------------------------
#   AA00AAA | NA  | 1-10| NA | 0  | NA | NA    | W     |  1   |  1   |    3
#   AA00AAA | 1-10|  2  | 0  | 90 | 90 | W     | N-S   |  1   |  2   |    3
#   AA00AAA | 2   |  NA | 90 | NA | NA | N-S   | NA    |  1   |  3   |    3
#   ----------------------------------------------------------------------------
#   AA00AAA | NA  | 1-10| NA | 1e6| NA | NA    | W     |  2   |  1   |    3
#   AA00AAA | 1-10|  2  | 0  |1e6+90|90| W     | N-S   |  2   |  2   |    3
#   AA00AAA | 2   |  NA |1e6+90|NA |NA | N-S   | NA    |  2   |  3   |    3
#

expected_trips_v1 = pd.DataFrame({
    'vehicle'               : ['AA00AAA'] * 6,
    'origin'                : [np.nan, '1-10', '2'] * 2,
    'destination'           : ['1-10', '2', np.nan] * 2,
    'od'                    : ['NA_1-10', '1-10_2', '2_NA'] * 2,
    't_origin'              : [pd.NaT, 0, 90, pd.NaT, 1e6, 1e6 + 90.0],
    't_destination'         : [0, 90.0, pd.NaT, 1e6, 1e6 + 90.0, pd.NaT],
    'travel_time'           : [pd.NaT, 90.0, pd.NaT] * 2,
    'direction_origin'      : [np.nan, 'W', 'E-W'] * 2,
    'direction_destination' : ['W', 'E-W', np.nan] * 2,
    'trip'                  : np.array([1] * 3 + [2] * 3, dtype=np.uint64),
    'trip_step'             : np.array([1,2,3] * 2, dtype=np.uint16),
    'trip_length'           : np.array([3] * 6, dtype = np.uint16),
    'valid'                 : np.array([np.nan,1.0,np.nan]*2, dtype=np.float64),
    'rest_time'             : [pd.NaT] * 3 + [1e6-90.0, pd.NaT, pd.NaT]
})

#   Expected Trips - Vehicle 2: 'AA11AAA'
#
#   vehicle | ori | dst | to | td | tt | d_ori | d_dst | trip | step | trip_len
#   ----------------------------------------------------------------------------
#   AA11AAA | NA  |  3 | NA | 0  | NA  | NA    | N-S   |  1   |  1   |    4
#   AA11AAA | 3   |1-10| 0  | 100| 100 | N-S   | W     |  1   |  2   |    4
#   AA11AAA | 1-10|  4 | 90 | NA | NA  | W     | S     |  1   |  3   |    4
#   AA11AAA | 4   | NA | 90 | NA | NA  | S     | NA    |  1   |  4   |    4
#   ----------------------------------------------------------------------------
#   AA00AAA | NA  | 3  | NA | 1e5| NA | NA    | N-S    |  2   |  1   |    2
#   AA00AAA | 3   | NA |1e5+100|NA |NA | N-S   | NA    |  2   |  2   |    2
#

expected_trips_v2 = pd.DataFrame({
    'vehicle'               : ['AA11AAA'] * 6,
    'origin'                : [np.nan, '3', '1-10', '4', np.nan, '3'],
    'destination'           : ['3', '1-10', '4', np.nan, '3', np.nan],
    'od'                    : ['NA_3','3_1-10','1-10_4','4_NA','NA_3','3_NA'],
    't_origin'              : [pd.NaT, 0, 100.0, 200.0, pd.NaT, 1e5],
    't_destination'         : [0, 100.0, 200.0, pd.NaT, 1e5, pd.NaT],
    'travel_time'           : [pd.NaT, 100.0, 100.0, pd.NaT, pd.NaT, pd.NaT],
    'direction_origin'      : [np.nan, 'N-S', 'W', 'S', np.nan, 'N-S'],
    'direction_destination' : ['N-S', 'W', 'S', np.nan, 'N-S', np.nan],
    'trip'                  : np.array([1] * 4 + [2] * 2, dtype=np.uint64),
    'trip_step'             : np.array([1,2,3,4] + [1,2], dtype=np.uint16),
    'trip_length'           : np.array([4] * 4 + [2] * 2, dtype=np.uint16),
    'valid'                 : np.array([np.nan,True,True,np.nan,np.nan,np.nan],
                                       dtype=np.float64),
    'rest_time'             : [pd.NaT] * 4 + [1e5-200.0, pd.NaT]
})

expected_trips = pd.concat([expected_trips_v1, expected_trips_v2], axis = 0)\
                   .reset_index(drop = True)

# Correcting datetime, timedelta dtypes
expected_trips['t_origin'] = expected_trips['t_origin']\
    .apply(lambda x: baseline_date + pd.to_timedelta(x, unit = 's'))
expected_trips['t_destination'] = expected_trips['t_destination']\
    .apply(lambda x: baseline_date + pd.to_timedelta(x, unit = 's'))
expected_trips['travel_time'] = expected_trips['travel_time']\
    .apply(lambda x: pd.to_timedelta(x, unit = 's'))
expected_trips['rest_time'] = expected_trips['rest_time']\
    .apply(lambda x: pd.to_timedelta(x, unit = 's'))

# Using global variables to avoid having to compute the same stuff twice

wrangled_cameras = None
raw_G            = None
merged_G         = None
camera_pairs     = None
wrangled_anpr    = None
trips            = None

### ----------------------------------------------------------------------------
### ----------------------------------------------------------------------------
### ----------------------------------------------------------------------------

def get_wrangled_cameras():
    global wrangled_cameras

    if wrangled_cameras is None:
        wrangled_cameras = wrangle_cameras(
            cameras             = raw_cameras_testset_1,
            is_test_col         = "name",
            is_commissioned_col = "is_commissioned",
            road_attr_col       = "desc",
            drop_car_park       = True,
            drop_na_direction   = True,
            distance_threshold  = 50.0,
            sort_by             = "id")

    return wrangled_cameras


def get_wrangled_network(plot = False):
    global raw_G

    if raw_G is None:
        raw_G = network_from_cameras(
            cameras = get_wrangled_cameras(),
            filter_residential = False,
            clean_intersections = True,
            tolerance = 5,
            plot = plot,
            file_format = 'png',
            fig_height = 12,
            fig_width = 12
        )

    return raw_G

def get_merged_network(plot = False):
    global merged_G

    if merged_G is None:
        merged_G = merge_cameras_network(
            G = get_wrangled_network(plot),
            cameras = get_wrangled_cameras(),
            plot = plot,
            file_format = 'png',
            fig_height = 12,
            fig_width = 12
        )

    return merged_G

def get_camera_pairs():
    global camera_pairs

    if camera_pairs is None:
        G = get_merged_network()
        camera_pairs = camera_pairs_from_graph(G)

    return camera_pairs


def get_wrangled_anpr():
    global wrangled_anpr

    if wrangled_anpr is None:
        wrangled_anpr = wrangle_raw_anpr(
            raw_anpr_testset,
            cameras = get_wrangled_cameras(),
            filter_low_confidence = True,
            confidence_threshold = 70,
            anonymise = False,
            digest_size = 10,
            digest_salt = b"ABC"
        )

    return wrangled_anpr

def get_trips():
    global trips

    if trips is None:
        trips = trip_identification(
            anpr = get_wrangled_anpr(),
            camera_pairs = get_camera_pairs(),
            speed_threshold = 3.0, # km/h : 3 km/h = 1 km/20h
            duplicate_threshold = 60.0,
            maximum_av_speed = 140.0
        )

    return trips

### ----------------------------------------------------------------------------
### ----------------------------------------------------------------------------
### ----------------------------------------------------------------------------

def test_wrangle_cameras():
    cameras = get_wrangled_cameras()

    assert len(cameras) == 6

    assert {'1-10', '2', '3', '4', '5', '9'}.issubset(cameras['id'].unique())

    assert cameras.loc[cameras.id == '1-10'].iloc[0]['direction'] == "W"
    assert cameras.loc[cameras.id == '2'].iloc[0]['direction'] == "E-W"
    assert cameras.loc[cameras.id == '3'].iloc[0]['direction'] == "N-S"
    assert cameras.loc[cameras.id == '9'].iloc[0]['direction'] == "E"

    assert cameras.loc[cameras.id == '1-10'].iloc[0]['ref'] == "A186"
    assert cameras.loc[cameras.id == '9'].iloc[0]['ref'] == "A186"
    assert cameras.loc[cameras.id == '2'].iloc[0]['ref'] == "A13"
    assert cameras.loc[cameras.id == '3'].iloc[0]['ref'] == "B1"
    assert cameras.loc[cameras.id == '4'].iloc[0]['ref'] == "A27"
    assert cameras.loc[cameras.id == '5'].iloc[0]['ref'] == "B1305"

    assert "Condercum Rd" in cameras[cameras['id'] == '5']['address'].iloc[0]


def test_wrangle_nodes():
    cameras = get_wrangled_cameras()

    nodes = map_nodes_cameras(
        raw_nodes_testset,
        cameras,
        is_test_col           = "name",
        is_commissioned_col   = False,
        road_attr_col         = "desc",
        drop_car_park         = True,
        drop_na_direction     = True,
        distance_threshold    = 100
    )

    # Same address, direction and within distance
    assert nodes.loc[nodes.id == '1'].iloc[0]['camera'] == '1-10'
    assert nodes.loc[nodes.id == '2'].iloc[0]['camera'] == '2'
    assert nodes.loc[nodes.id == '3'].iloc[0]['camera'] == '3'
    assert nodes.loc[nodes.id == '4'].iloc[0]['camera'] == '4'
    # Camera with same address but over distance_threshold
    assert pd.isna(nodes.loc[nodes.id == '5'].iloc[0]['camera'])
    # No camera with the same address
    assert pd.isna(nodes.loc[nodes.id == '6'].iloc[0]['camera'])

def test_wrangle_network_pairs(plot):
    """Test default behavior."""

    cameras = get_wrangled_cameras()
    pairs = get_camera_pairs()

    for origin in pairs['origin']:
        assert origin[0:1] != 'c_'

    assert len(pairs) == len(cameras) ** 2

    assert pairs.loc[(pairs.origin == '1-10') & (pairs.destination == '2')]\
                .iloc[0]['valid'] == 1

    assert pairs.loc[(pairs.origin == '1-10') & (pairs.destination == '3')]\
                .iloc[0]['valid'] == 1

    assert pairs.loc[(pairs.origin == '4') & (pairs.destination == '5')]\
                .iloc[0]['valid'] == 0

    assert pairs.loc[(pairs.origin == '5') & (pairs.destination == '4')]\
                .iloc[0]['valid'] == 0

    assert pairs.loc[(pairs.origin == '5') & (pairs.destination == '5')]\
                .iloc[0]['valid'] == 0


def test_wrangle_raw_anpr():

    cameras = get_wrangled_cameras()

    wrangled_anpr = get_wrangled_anpr()

    assert len(wrangled_anpr) == 16 # including 3 duplicates, 2 fast obs
    assert '1' not in wrangled_anpr['camera'].values
    assert '10' not in wrangled_anpr['camera'].values
    assert '1-10' in wrangled_anpr['camera'].values


def test_trips():
    cols = expected_trips_v1.columns.values

    trips = get_trips()

    print(trips['rest_time'])
    print(expected_trips['rest_time'])

    pd.testing.assert_frame_equal(
        trips.loc[trips.vehicle == "AA00AAA", cols],
        expected_trips.loc[expected_trips.vehicle == "AA00AAA", cols],
        check_dtype = True)

    pd.testing.assert_frame_equal(
        trips.loc[trips.vehicle == "AA11AAA", cols],
        expected_trips.loc[expected_trips.vehicle == "AA11AAA", cols],
        check_dtype = True)
