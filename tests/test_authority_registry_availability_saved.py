import gzip
from contextlib import contextmanager
import hashlib
from pathlib import Path
import tempfile
import unittest

from authority.checkpoints import Checkpoint
from authority_registry_availability_saved import AvailabilitySavedError, verify

EPOCH = 'a' * 32
RUN = 'b' * 32
INDICES = (9, 2)
FIELDS = [
    ('$format', 'integer', '1'), ('$epoch', 'string', '101'), ('$run_id', 'string', '102'),
    ('$issued_count', 'integer', '20'), ('$count', 'integer', '2'), ('$sealed', 'integer', '1'),
    ('$faulted', 'integer', None),
]
TABLE_NAMES = ('$forward_present', '$object_exists', '$is_ship', '$is_operational', '$reverse_matches')
DATA = {
    '$forward_present': {2: 1, 9: 0}, '$object_exists': {2: 1, 9: 1},
    '$is_ship': {2: 1, 9: 0}, '$is_operational': {2: 0, 9: 1},
    '$reverse_matches': {2: 1, 9: 1},
}


def build_xml(fields=None, data=None, extras='', epoch=EPOCH, run=RUN, first_table_id=200, key_type='integer'):
    fields = list(FIELDS if fields is None else fields)
    data = {key: dict(value) for key, value in (DATA if data is None else data).items()}
    vals = ''.join(f'<value name="{n}" type="{t}"' + (f' value="{v}"' if v is not None else '') + '/>' for n, t, v in fields)
    vals += ''.join(
        f'<value name="{name}" type="table" value="{first_table_id if i == 0 else 200+i}"/>'
        for i, name in enumerate(TABLE_NAMES))
    refs = f'<refs type="string"><ref id="101" string="{epoch}"/><ref id="102" string="{run}"/></refs>'
    for i, name in enumerate(TABLE_NAMES):
        entries = ''.join(
            f'<key type="{key_type}" value="{index}"/><value type="integer"'
            + (f' value="{value}"' if value else '') + '/>'
            for index, value in data[name].items())
        reference_id = first_table_id if i == 0 else 200 + i
        refs += f'<refs type="table"><ref id="{reference_id}">{entries}</ref></refs>'
    return ('<savegame><md><script name="X4AuthorityRegistryAvailabilityProbe"><cue name="State"><vars>'
            + vals + extras + '</vars></cue></script></md><script>' + refs + '</script></savegame>').encode()


class SavedAvailabilityTests(unittest.TestCase):
    @contextmanager
    def make_checkpoint(self, xml=None):
        if xml is None:
            xml = build_xml()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'save.gz'
            compressed = gzip.compress(xml)
            path.write_bytes(compressed)
            checkpoint = Checkpoint('checkpoint-' + 'c' * 32, path, hashlib.sha256(compressed).hexdigest(), len(compressed))
            yield checkpoint

    def check(self, xml=None, **kwargs):
        with self.make_checkpoint(xml) as checkpoint:
            return verify(checkpoint, kwargs.get('epoch', EPOCH), kwargs.get('run', RUN),
                          kwargs.get('issued', 20), kwargs.get('indices', INDICES))

    def test_round_trip_sparse_indices_and_mixed_booleans(self):
        result = self.check()
        self.assertEqual([row['index'] for row in result['rows']], [2, 9])
        self.assertIs(result['rows'][0]['forward_present'], True)
        self.assertIs(result['rows'][1]['is_operational'], True)
        self.assertIn('no runtime', result['evidence_scope'])

    def test_duplicate_field_and_duplicate_ref_id_rejected(self):
        duplicate_field = build_xml(extras='<value name="$count" type="integer" value="2"/>')
        with self.assertRaises(AvailabilitySavedError):
            self.check(duplicate_field)
        duplicate_ref = build_xml().replace(b'<ref id="102"', b'<ref id="101"')
        with self.assertRaises(AvailabilitySavedError):
            self.check(duplicate_ref)

    def test_same_numeric_reference_id_in_different_types_is_valid(self):
        self.assertEqual(self.check(build_xml(first_table_id=101))['count'], 2)

    def test_native_largefloat_index_encoding(self):
        result = self.check(build_xml(key_type='largefloat'))
        self.assertEqual([row['index'] for row in result['rows']], [2, 9])

    def test_aliased_tables_and_mismatched_tables_rejected(self):
        aliased = build_xml().replace(b'value="201"', b'value="200"', 1)
        with self.assertRaises(AvailabilitySavedError):
            self.check(aliased)
        data = dict(DATA)
        data['$object_exists'] = {2: 1}
        with self.assertRaises(AvailabilitySavedError):
            self.check(build_xml(data=data))

    def test_correlation_count_seal_and_fault_rejected(self):
        for kwargs in ({'epoch': 'd' * 32}, {'run': 'd' * 32}, {'issued': 21}, {'indices': (2,) }):
            with self.assertRaises(AvailabilitySavedError):
                self.check(**kwargs)
        for field_name, value in (('$sealed', '0'), ('$faulted', '1')):
            changed = [(n, t, value if n == field_name else v) for n, t, v in FIELDS]
            with self.assertRaises(AvailabilitySavedError):
                self.check(build_xml(fields=changed))

    def test_dangling_selected_key_at_group_boundary_rejected(self):
        xml = build_xml().replace(
            b'<key type="integer" value="2"/><value type="integer" value="1"/>',
            b'<key type="integer" value="2"/>', 1)
        with self.assertRaises(AvailabilitySavedError):
            self.check(xml)

    def test_nested_entry_and_missing_selected_reference_rejected(self):
        nested = build_xml().replace(b'<ref id="200">', b'<ref id="200"><nested/>', 1)
        missing_selected = build_xml().replace(
            b'<refs type="table"><ref id="200">',
            b'<refs type="table"><ref id="999">', 1)
        for xml in (nested, missing_selected):
            with self.subTest(xml=xml):
                with self.assertRaises(AvailabilitySavedError):
                    self.check(xml)

    def test_duplicate_table_key_rejected(self):
        duplicate_key = build_xml().replace(b'<key type="integer" value="9"/>', b'<key type="integer" value="2"/>', 1)
        with self.assertRaises(AvailabilitySavedError):
            self.check(duplicate_key)

    def test_invalid_boolean_and_integrity_mismatch_rejected(self):
        bad_data = dict(DATA)
        bad_data['$forward_present'] = {2: 2, 9: 0}
        with self.assertRaises(AvailabilitySavedError):
            self.check(build_xml(data=bad_data))
        with self.make_checkpoint() as checkpoint:
            checkpoint.path.write_bytes(checkpoint.path.read_bytes() + b'!')
            with self.assertRaises(AvailabilitySavedError):
                verify(checkpoint, EPOCH, RUN, 20, INDICES)


if __name__ == '__main__':
    unittest.main()
