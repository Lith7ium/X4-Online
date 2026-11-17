"""Compare candidate station anchors in two fixture-sector observations.

The caller owns checkpoint provenance, native readers, pause and process
fences. Saved candidates and matching records alone prove no X4 runtime fact.
"""
import math

from authority_saved_frame_compare import noncollinear

# Inventory from confirmed checkpoint-cac780ceccbd405ea367dfe028a5ae9d.
# These are saved candidates; native operation and discoverability are unproven.
FIXTURE_SECTORS = {
    1: {
        'sector': 'cluster_33_sector001_macro',
        'stations': {
            'SLS-778': ('xenon_small_station_01_macro', 'xenon'),
            'MRY-123': ('xenon_small_station_01_macro', 'xenon'),
            'MYO-569': ('station_xen_shipyard_base_01_macro', 'xenon'),
            'UNY-112': ('xenon_small_station_01_macro', 'xenon'),
            'WRC-572': ('xenon_small_station_01_macro', 'xenon'),
            'TFX-549': ('station_xen_shipyard_base_01_macro', 'xenon'),
            'EMK-709': ('xenon_small_station_01_macro', 'xenon'),
            'ZJC-487': ('station_xen_defence_base_01_macro', 'xenon'),
            'QMO-302': ('station_xen_factory_base_01_macro', 'xenon'),
            'IIX-945': ('xenon_small_station_01_macro', 'xenon'),
            'QHN-865': ('station_xen_factory_base_01_macro', 'xenon'),
            'GYR-493': ('station_xen_factory_base_01_macro', 'xenon'),
        },
    },
    2: {
        'sector': 'cluster_45_sector001_macro',
        'stations': {
            'FPJ-079': ('landmarks_kha_weaponplatform_01_macro', 'khaak'),
            'OSK-110': ('landmarks_kha_weaponplatform_01_macro', 'khaak'),
            'JFP-464': ('landmarks_kha_hive_03_macro', 'khaak'),
            'XMV-006': ('landmarks_kha_weaponplatform_01_macro', 'khaak'),
            'FUE-354': ('landmarks_kha_weaponplatform_01_macro', 'khaak'),
            'HWE-184': ('landmarks_kha_weaponplatform_01_macro', 'khaak'),
            'FJW-934': ('landmarks_kha_weaponplatform_01_macro', 'khaak'),
            'PFP-044': ('station_gen_piratebase_base_01_macro', 'scaleplate'),
        },
    },
}


def _read_stations(observations, slot):
    """Validate plain, detached station rows supplied by one local reader."""
    fixture = FIXTURE_SECTORS[slot]
    rows = observations[slot]
    if type(rows) is not list or len(rows) > len(fixture['stations']):
        raise ValueError('invalid fixture station rows')
    stations = {}
    for row in rows:
        if type(row) is not dict or set(row) != {'code', 'macro', 'owner', 'sector', 'position'}:
            raise ValueError('invalid fixture station row')
        code = row['code']
        if (type(code) is not str or code in stations or code not in fixture['stations'] or
                row['sector'] != fixture['sector'] or
                (row['macro'], row['owner']) != fixture['stations'][code]):
            raise ValueError('fixture station identity differs')
        position = row['position']
        if (type(position) not in (tuple, list) or len(position) != 3 or
                any(type(value) not in (int, float) or abs(value) > 1e9 or not math.isfinite(value)
                    for value in position)):
            raise ValueError('invalid fixture station position')
        stations[code] = tuple(position)
    return stations


def compare(first, second, *, tolerance=1.0):
    """Compare two supplied sector-frame observations; return no X4 handles.

    Each input is ``{1: [station rows], 2: [station rows]}``. Positions must
    already be expressed in the relevant local X4 sector frame. This function
    neither obtains nor independently verifies the observations.
    """
    if (type(first) is not dict or type(second) is not dict or set(first) != {1, 2} or
            set(second) != {1, 2} or any(type(slot) is not int for slot in (*first, *second)) or
            type(tolerance) not in (int, float) or not 0 < tolerance <= 1 or not math.isfinite(tolerance)):
        raise ValueError('invalid fixture frame comparison context')
    sectors = []
    for slot in (1, 2):
        left, right = _read_stations(first, slot), _read_stations(second, slot)
        common = sorted(left.keys() & right.keys())
        if len(common) < 3:
            raise ValueError('fewer than three shared fixture stations')
        if not noncollinear([left[code] for code in common]) or not noncollinear([right[code] for code in common]):
            raise ValueError('fixture station geometry is degenerate')
        deltas = [math.dist(left[code], right[code]) for code in common]
        if any(delta > tolerance for delta in deltas):
            raise ValueError('fixture station positions differ')
        sectors.append({'slot': slot, 'expected_registry_index': slot + 2, 'sector': FIXTURE_SECTORS[slot]['sector'],
                        'station_codes': common, 'station_count': len(common), 'max_station_delta': max(deltas)})
    return {'sectors': sectors, 'position_tolerance': tolerance, 'geometry_min_arm': 1000,
            'geometry_min_sine': 0.05, 'runtime_observation_proven': False,
            'cross_process_identity_proven': False, 'universal_frame_identity_proven': False,
            'continuous_pause_proven': False, 'gameplay_proven': False}
