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


def build_xml(bits=(1, 0, 1), *, key_type='integer', available=None, ships=None,
              reverse=None, counters=None, fields_extra='', refs_extra='', definitions=None):
    count = len(bits)
    available = {i: bit for i, bit in enumerate(bits, 1)} if available is None else dict(available)
    indices = [i for i, bit in enumerate(bits, 1) if bit]
    ships = {i: f'{0x100+i:x}' for i in indices} if ships is None else dict(ships)
    reverse = {v: k for k, v in ships.items()} if reverse is None else dict(reverse)
    ac = sum(bits) if counters is None else counters[0]
    uc = count - ac if counters is None else counters[1]
    fields = [('$format', 'integer', '2'), ('$epoch', 'string', '10'), ('$run_id', 'string', '11'),
              ('$issued_count', 'integer', str(count)), ('$cursor', 'integer', str(count)),
              ('$available_count', 'integer', str(ac)), ('$unavailable_count', 'integer', str(uc)),
              ('$sealed', 'integer', '1'), ('$faulted', 'integer', None),
              ('$available', 'table', '20'), ('$ships', 'table', '21'), ('$byship', 'table', '22')]
    values = ''.join(f'<value name="{n}" type="{t}"' + (f' value="{v}"' if v is not None else '') + '/>' for n,t,v in fields)
    values += fields_extra
    def entry(k, v, typ='integer', kt=key_type):
        return f'<key type="{kt}" value="{k}"/><value type="{typ}" value="{v}"/>'
    avail_xml = ''.join(entry(k, v) for k,v in available.items())
    ship_xml = ''.join(entry(k, f'[0x{v}]', 'component') for k,v in ships.items())
    reverse_xml = ''.join(entry(f'[0x{k}]', v, 'integer', 'component') for k,v in reverse.items())
    refs = (f'<refs type="string"><ref id="10" string="{EPOCH}"/><ref id="11" string="{RUN}"/></refs>'
            f'<refs type="table"><ref id="20">{avail_xml}</ref></refs>'
            f'<refs type="table"><ref id="21">{ship_xml}</ref></refs>'
            f'<refs type="table"><ref id="22">{reverse_xml}</ref></refs>') + refs_extra
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

    def test_mixed_full_snapshot_bits_and_digests(self):
        result = self.check(build_xml())
        self.assertEqual(result['availability_bits'], '101')
        self.assertEqual((result['available_count'], result['unavailable_count']), (2, 1))
        self.assertEqual(len(result['mapping_sha256']), 64)
        self.assertEqual(len(result['availability_sha256']), 64)
        self.assertEqual(result['evidence_scope'], 'saved checkpoint bytes only')

    def test_all_unavailable_empty_ship_tables(self):
        xml = build_xml((0, 0, 0), ships={}, reverse={}, definitions='')
        xml = xml.replace(b'name="$available_count" type="integer" value="0"', b'name="$available_count" type="integer"')
        result = self.check(xml)
        self.assertEqual(result['availability_bits'], '000')

    def test_largefloat_keys_and_typed_reference_id_reuse(self):
        xml = build_xml((1, 0, 1), key_type='largefloat').replace(b'<key type="largefloat" value="1"/>', b'<key type="largefloat" value="1.000000"/>', 1).replace(b'name="$available" type="table" value="20"', b'name="$available" type="table" value="10"').replace(b'id="20"', b'id="10"')
        self.assertEqual(self.check(xml)['availability_bits'], '101')

    def test_full_10082_mixed_snapshot_with_seven_unavailable(self):
        unavailable = {576, 577, 578, 579, 664, 671, 672}
        bits = tuple(0 if i in unavailable else 1 for i in range(1, 10083))
        result = self.check(build_xml(bits), count=10082)
        self.assertEqual((result['available_count'], result['unavailable_count']), (10075, 7))
        self.assertEqual(len(result['availability_bits']), 10082)
        self.assertEqual([i for i, bit in enumerate(result['availability_bits'], 1) if bit == '0'], sorted(unavailable))

    def test_sparse_10082_snapshot_detects_missing_seventh(self):
        bits = (1,) * 10082
        xml = build_xml(bits, definitions=''.join(
            f'<component id="[0x{0x100+i:x}]" class="ship_s"/>' for i in range(1, 10083) if i != 7))
        with self.assertRaises(RegistryAvailabilityEvidenceError):
            self.check(xml, count=10082)

    def test_missing_duplicate_and_wrongclass_components_rejected(self):
        for definitions in ('', '<component id="[0x101]" class="ship_s"/><component id="[0x101]" class="ship_s"/>',
                            '<component id="[0x101]" class="station"/><component id="[0x103]" class="ship_s"/>'):
            with self.subTest(definitions=definitions), self.assertRaises(RegistryAvailabilityEvidenceError):
                self.check(build_xml(definitions=definitions))

    def test_aliases_duplicate_refs_duplicate_keys_gaps_and_nulls_rejected(self):
        cases = [build_xml().replace(b'value="21"', b'value="20"'),
                 build_xml(refs_extra='<refs type="table"><ref id="20"/></refs>'),
                 build_xml().replace(b'<key type="integer" value="2"/>', b'<key type="integer" value="1"/>', 1),
                 build_xml(available={1:1, 3:1, 4:0}),
                 build_xml(ships={1:'0', 3:'103'})]
        for xml in cases:
            with self.subTest(), self.assertRaises(RegistryAvailabilityEvidenceError):
                self.check(xml)

    def test_counters_epoch_run_seal_fault_and_gzip_integrity(self):
        all_available = build_xml((1, 1, 1), counters=(3, 0)).replace(
            b'name="$unavailable_count" type="integer" value="0"',
            b'name="$unavailable_count" type="integer"')
        self.assertEqual(self.check(all_available)['availability_bits'], '111')
        for xml, kwargs in ((build_xml(counters=(1, 2)), {}), (build_xml(), {'epoch':'d'*32}),
                            (build_xml(), {'run':'d'*32}),
                            (build_xml(fields_extra='<value name="$sealed" type="integer" value="0"/>'), {}),
                            (build_xml(fields_extra='<value name="$faulted" type="integer" value="0"/>'), {})):
            with self.assertRaises(RegistryAvailabilityEvidenceError):
                self.check(xml, **kwargs)
        with self.checkpoint(build_xml()) as cp:
            cp.path.write_bytes(cp.path.read_bytes() + b'!')
            with self.assertRaises(RegistryAvailabilityEvidenceError):
                verify(cp, EPOCH, RUN, 3)


if __name__ == '__main__':
    unittest.main()
