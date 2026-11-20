import gzip
import hashlib
from contextlib import contextmanager
from pathlib import Path
import tempfile
import unittest

from authority.checkpoints import Checkpoint
from authority.registry_availability_evidence import RegistryAvailabilityEvidenceError, verify

EPOCH = 'a' * 32
RUN = 'b' * 32
WRECK_INDICES = (22, 23, 24, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 78, 79, 80, 81, 82, 83, 253, 1448, 3314, 3563, 3564, 3656, 3657, 3683, 4004, 4013, 4018, 4098, 4099, 4100, 4112, 4113, 4115, 4449, 4888, 4889, 4890, 4892, 4903, 4904, 4905, 4906, 4907, 5058, 5127, 5314, 5315, 5316, 5597, 5598, 5610, 5611, 5612)
MISSING_INDICES = (576, 577, 578, 579, 664, 671, 672)


def build_xml(bits=(1, 0, 1), *, operational=None, key_type='integer', available=None,
              op_table=None, ships=None, reverse=None, counters=None, operational_count=None,
              format_version=3, fields_extra='', refs_extra='', definitions=None):
    count = len(bits)
    available = {i: bit for i, bit in enumerate(bits, 1)} if available is None else dict(available)
    operational = tuple(bits) if operational is None else tuple(operational)
    op_table = {i: bit for i, bit in enumerate(operational, 1)} if op_table is None else dict(op_table)
    indices = [i for i, bit in enumerate(bits, 1) if bit]
    ships = {i: f'{0x100+i:x}' for i in indices} if ships is None else dict(ships)
    reverse = {v: k for k, v in ships.items()} if reverse is None else dict(reverse)
    available_count = sum(bits) if counters is None else counters[0]
    unavailable_count = count - available_count if counters is None else counters[1]
    op_count = sum(operational) if operational_count is None else operational_count
    fields = [('$format', 'integer', str(format_version)), ('$epoch', 'string', '10'), ('$run_id', 'string', '11'),
              ('$issued_count', 'integer', str(count)), ('$cursor', 'integer', str(count)),
              ('$available_count', 'integer', str(available_count)), ('$unavailable_count', 'integer', str(unavailable_count)),
              ('$operational_count', 'integer', str(op_count)), ('$sealed', 'integer', '1'), ('$faulted', 'integer', None),
              ('$available', 'table', '20'), ('$operational', 'table', '21'),
              ('$ships', 'table', '22'), ('$byship', 'table', '23')]
    values = ''.join(f'<value name="{n}" type="{t}"' + (f' value="{v}"' if v is not None else '') + '/>' for n,t,v in fields)
    values += fields_extra
    def entry(k, v, typ='integer', kt=key_type):
        return f'<key type="{kt}" value="{k}"/><value type="{typ}"' + (f' value="{v}"' if v else '') + '/>'
    avail_xml = ''.join(entry(k, v) for k,v in available.items())
    op_xml = ''.join(entry(k, v) for k,v in op_table.items())
    ship_xml = ''.join(entry(k, f'[0x{v}]', 'component') for k,v in ships.items())
    reverse_xml = ''.join(entry(f'[0x{k}]', v, 'integer', 'component') for k,v in reverse.items())
    refs = (f'<refs type="string"><ref id="10" string="{EPOCH}"/><ref id="11" string="{RUN}"/></refs>'
            f'<refs type="table"><ref id="20">{avail_xml}</ref></refs>'
            f'<refs type="table"><ref id="21">{op_xml}</ref></refs>'
            f'<refs type="table"><ref id="22">{ship_xml}</ref></refs>'
            f'<refs type="table"><ref id="23">{reverse_xml}</ref></refs>') + refs_extra
    if definitions is None:
        definitions = ''.join(f'<component id="[0x{v}]" class="ship_s"/>' for v in ships.values())
    return (f'<savegame><md><script name="X4AuthorityRegistryAvailabilitySnapshot"><cue name="State"><vars>{values}</vars></cue></script></md>'
            f'<script>{refs}</script><universe>{definitions}</universe></savegame>').encode()


class RegistryAvailabilityEvidenceTests(unittest.TestCase):
    @contextmanager
    def checkpoint(self, xml):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'save.gz'
            data = gzip.compress(xml)
            path.write_bytes(data)
            yield Checkpoint('checkpoint-' + 'c'*32, path, hashlib.sha256(data).hexdigest(), len(data))

    def check(self, xml, count=None, epoch=EPOCH, run=RUN):
        count = count or 3
        with self.checkpoint(xml) as cp:
            return verify(cp, epoch, run, count)

    def test_mixed_bits_and_v3_digests(self):
        result = self.check(build_xml((1, 0, 1), operational=(1, 0, 0)))
        self.assertEqual(result['format'], 3)
        self.assertEqual(result['availability_bits'], '101')
        self.assertEqual(result['operational_bits'], '100')
        self.assertEqual((result['available_count'], result['unavailable_count'], result['operational_count']), (2, 1, 1))
        for name in ('mapping_sha256', 'availability_sha256', 'operational_sha256'):
            self.assertEqual(len(result[name]), 64)
        self.assertEqual(result['evidence_scope'], 'saved checkpoint bytes only')
        self.assertIn('recheck live', result['operational_scope'])

    def test_all_missing_and_all_available_but_nonoperational(self):
        missing = build_xml((0, 0, 0), operational=(0, 0, 0), ships={}, reverse={}, definitions='')
        missing = missing.replace(b'name="$available_count" type="integer" value="0"', b'name="$available_count" type="integer"')
        result = self.check(missing)
        self.assertEqual((result['availability_bits'], result['operational_bits']), ('000', '000'))
        all_nonop = self.check(build_xml((1, 1, 1), operational=(0, 0, 0)))
        self.assertEqual((all_nonop['availability_bits'], all_nonop['operational_bits']), ('111', '000'))
        self.assertEqual(all_nonop['operational_count'], 0)

    def test_native_largefloat_keys_and_typed_reference_id_reuse(self):
        xml = build_xml((1, 0, 1), operational=(1, 0, 1), key_type='largefloat')
        xml = xml.replace(b'<key type="largefloat" value="1"/>', b'<key type="largefloat" value="1.000000"/>', 1)
        xml = xml.replace(b'name="$available" type="table" value="20"', b'name="$available" type="table" value="10"').replace(b'id="20"', b'id="10"')
        self.assertEqual(self.check(xml)['availability_bits'], '101')

    def test_full_10082_with_seven_missing_and_56_bound_nonoperational(self):
        missing = set(MISSING_INDICES)
        nonop = missing | set(WRECK_INDICES)
        availability = tuple(0 if i in missing else 1 for i in range(1, 10083))
        operational = tuple(0 if i in nonop else 1 for i in range(1, 10083))
        ships = {i: f'{0x100+i:x}' for i, bit in enumerate(availability, 1) if bit}
        reverse = {component: index for index, component in ships.items()}
        definitions = ''.join(
            f'<component id="[0x{component}]" class="ship_s"' + (' state="wreck"' if index in WRECK_INDICES else '') + '/>'
            for index, component in ships.items())
        result = self.check(build_xml(availability, operational=operational, ships=ships, reverse=reverse, definitions=definitions), count=10082)
        self.assertEqual((result['available_count'], result['unavailable_count']), (10075, 7))
        self.assertEqual(result['operational_count'], 10019)
        self.assertEqual([i for i, bit in enumerate(result['availability_bits'], 1) if bit == '0'], sorted(missing))
        self.assertEqual([i for i, bit in enumerate(result['operational_bits'], 1) if bit == '0'], sorted(nonop))
        self.assertEqual((result['availability_bits'][58], result['operational_bits'][58]), ('1', '0'))

    def test_missing_component_definition_is_rejected_for_binding(self):
        bits = (1,) * 64
        xml = build_xml(bits, operational=(1,) * 64, definitions=''.join(
            f'<component id="[0x{0x100+i:x}]" class="ship_s"/>' for i in range(1, 65) if i != 7))
        with self.assertRaises(RegistryAvailabilityEvidenceError):
            self.check(xml, count=64)

    def test_operational_map_gaps_unbound_true_and_bad_count_rejected(self):
        bits = (1, 0, 1)
        cases = [build_xml(bits, operational=(1, 0, 1), op_table={1: 1, 3: 1}),
                 build_xml(bits, operational=(1, 1, 1), operational_count=3),
                 build_xml(bits, operational=(1, 0, 1), operational_count=1),
                 build_xml(bits, operational=(1, 2, 0), op_table={1: 1, 2: 2, 3: 0})]
        for xml in cases:
            with self.subTest(), self.assertRaises(RegistryAvailabilityEvidenceError):
                self.check(xml)

    def test_format2_alias_duplicate_refs_and_binding_mismatch_rejected(self):
        cases = [build_xml(format_version=2),
                 build_xml().replace(b'value="21"', b'value="20"'),
                 build_xml(refs_extra='<refs type="table"><ref id="21"/></refs>'),
                 build_xml(available={1:1, 3:1, 4:0}),
                 build_xml(ships={1:'101', 3:'101'})]
        for xml in cases:
            with self.subTest(), self.assertRaises(RegistryAvailabilityEvidenceError):
                self.check(xml)

    def test_counters_correlation_seal_fault_and_gzip_integrity(self):
        omitted_zero = build_xml((1, 1, 1), operational=(0, 0, 0), operational_count=0).replace(
            b'name="$operational_count" type="integer" value="0"', b'name="$operational_count" type="integer"')
        self.assertEqual(self.check(omitted_zero)['operational_count'], 0)
        bad = [build_xml(counters=(1, 2)), build_xml(operational=(1, 0, 0), operational_count=2),
               build_xml(), build_xml()]
        kwargs = ({}, {}, {'epoch': 'd'*32}, {'run': 'd'*32})
        for xml, options in zip(bad, kwargs):
            with self.assertRaises(RegistryAvailabilityEvidenceError):
                self.check(xml, **options)
        for xml in (build_xml(fields_extra='<value name="$sealed" type="integer" value="0"/>'),
                    build_xml(fields_extra='<value name="$faulted" type="integer" value="0"/>')):
            with self.assertRaises(RegistryAvailabilityEvidenceError):
                self.check(xml)
        with self.checkpoint(build_xml()) as cp:
            cp.path.write_bytes(cp.path.read_bytes() + b'!')
            with self.assertRaises(RegistryAvailabilityEvidenceError):
                verify(cp, EPOCH, RUN, 3)


if __name__ == '__main__':
    unittest.main()
