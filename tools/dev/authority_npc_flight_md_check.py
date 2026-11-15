#!/usr/bin/env python3
"""Read-only XML/schema precheck for the NPC flight fixture; never starts X4.

Supply an independently obtained local md.xsd with --xsd to request stock
schema validation. Schema compilation can be expensive. Neither XML parsing
nor schema validation executes MD or proves its in-game expression semantics.
"""
import argparse
from pathlib import Path
import xml.etree.ElementTree as ET

FIXTURE = Path(__file__).with_name('authority_npc_flight_fixture.xml')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--xsd', type=Path, help='local X4 md.xsd and its referenced schemas')
    args = parser.parse_args()
    root = ET.parse(FIXTURE).getroot()
    if root.tag != 'mdscript' or root.get('name') != 'X4AuthorityNPCFlightFixture':
        raise ValueError('unexpected MD fixture')
    print('XML parsed; this does not establish X4 runtime semantics.')
    if args.xsd:
        from lxml import etree
        schema = etree.XMLSchema(etree.parse(str(args.xsd)))
        schema.assertValid(etree.parse(str(FIXTURE)))
        print('Supplied MD schema accepted the fixture; X4 runtime semantics remain unverified.')
    else:
        print('MD schema validation not requested.')


if __name__ == '__main__':
    main()
