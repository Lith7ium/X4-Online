"""Generated saves only; the diagnostic does not launch X4."""
import gzip
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('witness_save_evidence', ROOT/'tools/dev/authority_registry_witness_save_evidence.py')
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)
EPOCH = 'a' * 32


def save():
    return f'''<savegame><universe><component class="ship_s" id="[0x1]" macro="a"/><component class="ship_l" id="[0x2]" macro="b"/></universe>
<script><refs type="string"><ref id="1" string="{EPOCH}"/><ref id="2" string="sealed"/></refs>
<refs type="table"><ref id="3"><key type="integer" value="1"/><value type="component" value="[0x1]"/><key type="integer" value="2"/><value type="component" value="[0x2]"/></ref>
<ref id="4"><key type="component" value="[0x1]"/><value type="integer" value="1"/><key type="component" value="[0x2]"/><value type="integer" value="2"/></ref>
<ref id="5"><key type="integer" value="1"/><value type="component" value="[0x2]"/><key type="integer" value="2"/><value type="component" value="[0x1]"/></ref>
<ref id="6"><key type="component" value="[0x1]"/><value type="integer" value="2"/><key type="component" value="[0x2]"/><value type="integer" value="1"/></ref></refs></script>
<md><script name="X4AuthorityShipRegistry"><cue name="State"><vars><value name="$epoch" type="string" value="1"/><value name="$last" type="integer" value="2"/><value name="$faulted" type="integer"/><value name="$ships" type="table" value="3"/><value name="$byship" type="table" value="4"/></vars></cue></script>
<script name="X4AuthorityRegistryWitness"><cue name="State"><vars><value name="$epoch" type="string" value="1"/><value name="$count" type="integer" value="2"/><value name="$cursor" type="integer" value="2"/><value name="$phase" type="string" value="2"/><value name="$faulted" type="integer"/><value name="$objects" type="table" value="5"/><value name="$reverse" type="table" value="6"/></vars></cue></script></md></savegame>'''


class WitnessSaveTests(unittest.TestCase):
    def check(self, text, *, digest=None, epoch=EPOCH, count=2):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'save.xml.gz'
            data = gzip.compress(text.encode()); path.write_bytes(data)
            checkpoint = M.Checkpoint('checkpoint-'+'a'*32, path, digest or hashlib.sha256(data).hexdigest(), len(data))
            return M.verify(checkpoint, epoch, count)

    def test_valid_and_scope(self):
        result = self.check(save())
        self.assertEqual(result['count'], 2)
        self.assertTrue(result['registry_witness_match'])
        self.assertFalse(result['historical_identity_proven'])
        self.assertFalse(result['runtime_binding_proven'])

    def test_native_largefloat_counters_are_exact_canonical_integers(self):
        text = save()
        for field in ('$count', '$cursor'):
            text = text.replace(f'name="{field}" type="integer" value="2"',
                                f'name="{field}" type="largefloat" value="2"')
        self.assertTrue(self.check(text)['registry_witness_match'])
        for field in ('$count', '$cursor'):
            for value in ('NaN', 'inf', '-inf', '2.0', '2.5', '2e0', '0', '-2', '+2', '02', '200001', '99999999999999999999999999999999', ''):
                with self.subTest(field=field, value=value), self.assertRaises(M.WitnessEvidenceError):
                    self.check(text.replace(f'name="{field}" type="largefloat" value="2"',
                                            f'name="{field}" type="largefloat" value="{value}"'))
        with self.assertRaises(M.WitnessEvidenceError):
            self.check(text.replace('name="$last" type="integer"', 'name="$last" type="largefloat"'))

    def test_native_largefloat_witness_slots(self):
        text = save()
        for ref in ('5', '6'):
            start = text.index('<ref id="'+ref+'">')
            end = text.index('</ref>', start) + len('</ref>')
            text = text[:start] + text[start:end].replace('type="integer"', 'type="largefloat"') + text[end:]
        self.assertTrue(self.check(text)['registry_witness_match'])
        for field in ('<key type="largefloat" value="1"/>', '<value type="largefloat" value="1"/>'):
            for value in ('NaN', 'inf', '1.0', '1.5', '1e0', '0', '-1', '+1', '01', '200001', '999999999999999999999', ''):
                with self.subTest(field=field, value=value), self.assertRaises(M.WitnessEvidenceError):
                    self.check(text.replace(field, field.replace('value="1"', 'value="'+value+'"'), 1))
        with self.assertRaises(M.WitnessEvidenceError):
            self.check(text.replace('<ref id="3"><key type="integer"', '<ref id="3"><key type="largefloat"', 1))
        with self.assertRaises(M.WitnessEvidenceError):
            self.check(text.replace('<ref id="4"><key type="component" value="[0x1]"/><value type="integer"', '<ref id="4"><key type="component" value="[0x1]"/><value type="largefloat"', 1))

    def test_renumbered_component_ids_preserve_structure(self):
        text = save().replace('[0x1]', '[0xa]').replace('[0x2]', '[0xb]')
        self.assertTrue(self.check(text)['registry_witness_match'])

    def test_invalid_component_numbers_are_rejected(self):
        for value in ('[0x0]', '[0x0000000000000000]', '[0x10000000000000000]'):
            with self.subTest(value=value), self.assertRaises(M.WitnessEvidenceError):
                self.check(save().replace('[0x1]', value))

    def test_consistent_but_permuted_witness_is_rejected(self):
        text = save()
        objects = '<ref id="5"><key type="integer" value="1"/><value type="component" value="[0x2]"/><key type="integer" value="2"/><value type="component" value="[0x1]"/></ref>'
        swapped = '<ref id="5"><key type="integer" value="1"/><value type="component" value="[0x1]"/><key type="integer" value="2"/><value type="component" value="[0x2]"/></ref>'
        reverse = '<ref id="6"><key type="component" value="[0x1]"/><value type="integer" value="2"/><key type="component" value="[0x2]"/><value type="integer" value="1"/></ref>'
        swapped_reverse = '<ref id="6"><key type="component" value="[0x1]"/><value type="integer" value="1"/><key type="component" value="[0x2]"/><value type="integer" value="2"/></ref>'
        with self.assertRaises(M.WitnessEvidenceError):
            self.check(text.replace(objects, swapped).replace(reverse, swapped_reverse))

    def test_rejects_duplicate_reference_containers(self):
        for addition in ('<refs type="string"/>', '<refs type="table"/>'):
            with self.subTest(addition=addition), self.assertRaises(M.WitnessEvidenceError):
                self.check(save().replace('</refs></script>\n<md>', '</refs>' + addition + '</script>\n<md>', 1))
        with self.assertRaises(M.WitnessEvidenceError):
            self.check(save().replace('</script>\n<md>', '</script><script/>\n<md>', 1))

    def test_three_entries_and_missing_or_extra_rows(self):
        text = save().replace('<component class="ship_l" id="[0x2]" macro="b"/>', '<component class="ship_l" id="[0x2]" macro="b"/><component class="ship_s" id="[0x3]" macro="c"/>')
        old = '<refs type="table">' + text.split('<refs type="table">', 1)[1].split('</refs>', 1)[0] + '</refs>'
        tables = '<refs type="table">'
        for ref, pairs in ((3, [(1, 1), (2, 2), (3, 3)]), (4, [(1, 1), (2, 2), (3, 3)]), (5, [(1, 3), (2, 2), (3, 1)]), (6, [(1, 3), (2, 2), (3, 1)])):
            tables += f'<ref id="{ref}">'
            for index, component in pairs:
                key = f'<key type="integer" value="{index}"/>'
                value = f'<value type="component" value="[0x{component}]"/>'
                if ref in (4, 6):
                    key = f'<key type="component" value="[0x{component}]"/>'
                    value = f'<value type="integer" value="{index}"/>'
                tables += key + value
            tables += '</ref>'
        tables += '</refs>'
        text = text.replace(old, tables)
        for field in ('$last', '$count', '$cursor'):
            text = text.replace(f'name="{field}" type="integer" value="2"', f'name="{field}" type="integer" value="3"')
        self.assertTrue(self.check(text, count=3)['registry_witness_match'])
        with self.assertRaises(M.WitnessEvidenceError):
            self.check(text.replace('<key type="integer" value="3"/><value type="component" value="[0x3]"/>', '', 1), count=3)
        with self.assertRaises(M.WitnessEvidenceError):
            self.check(text.replace('<ref id="3">', '<ref id="3"><key type="integer" value="4"/><value type="component" value="[0x4]"/>', 1), count=3)

    def test_rejects_wrong_digest_epoch_and_unsealed(self):
        with self.assertRaises(M.WitnessEvidenceError): self.check(save(), digest='0'*64)
        with self.assertRaises(M.WitnessEvidenceError): self.check(save(), epoch='b'*32)
        with self.assertRaises(M.WitnessEvidenceError): self.check(save().replace('string="sealed"', 'string="verify"'))
        with self.assertRaises(M.WitnessEvidenceError): self.check(save().replace('name="$cursor" type="integer" value="2"', 'name="$cursor" type="integer" value="1"'))

    def test_rejects_alias_or_witness_disagreement(self):
        with self.assertRaises(M.WitnessEvidenceError): self.check(save().replace('name="$objects" type="table" value="5"', 'name="$objects" type="table" value="3"'))
        with self.assertRaises(M.WitnessEvidenceError): self.check(save().replace('<ref id="5"><key type="integer" value="1"/><value type="component" value="[0x2]"/>', '<ref id="5"><key type="integer" value="1"/><value type="component" value="[0x1]"/>'))
        with self.assertRaises(M.WitnessEvidenceError): self.check(save().replace('<ref id="6"><key type="component" value="[0x1]"/><value type="integer" value="2"/>', '<ref id="6"><key type="component" value="[0x1]"/><value type="integer" value="1"/>'))

    def test_rejects_duplicate_unknown_or_missing_components(self):
        with self.assertRaises(M.WitnessEvidenceError): self.check(save().replace('<ref id="5">', '<ref id="5"/><ref id="5">'))
        with self.assertRaises(M.WitnessEvidenceError): self.check(save().replace('class="ship_l"', 'class="station"'))
        with self.assertRaises(M.WitnessEvidenceError): self.check(save().replace('id="[0x2]" macro="b"', 'id="[0x3]" macro="b"'))
        with self.assertRaises(M.WitnessEvidenceError): self.check(save().replace('<value name="$cursor"', '<value name="$count" type="integer" value="2"/><value name="$cursor"'))

    def test_rejects_fault_and_malformed_xml(self):
        with self.assertRaises(M.WitnessEvidenceError): self.check(save().replace('name="$faulted" type="integer"', 'name="$faulted" type="integer" value="1"', 1))
        with self.assertRaises(M.WitnessEvidenceError): self.check(save()[:-5])
        with self.assertRaises(M.WitnessEvidenceError): self.check('<!DOCTYPE savegame [<!ENTITY a "x">]><savegame>&a;</savegame>')


if __name__ == '__main__': unittest.main()
