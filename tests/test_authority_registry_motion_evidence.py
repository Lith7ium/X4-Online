"""Synthetic validation of motion evidence; no X4 processes are started."""
import importlib.util
from pathlib import Path
import unittest

PATH=Path(__file__).resolve().parents[1]/'tools/dev/authority_registry_motion_evidence.py'
spec=importlib.util.spec_from_file_location('authority_registry_motion_evidence',PATH)
evidence=importlib.util.module_from_spec(spec);spec.loader.exec_module(evidence)
EPOCH='a'*32
FRAME='cluster_01'


def logs():
    server=[];client=[]
    for seq in range(1,7):
        x=seq*10
        server.append(f'REGISTRY_MOTION_SOURCE epoch={EPOCH} index=1 frame={FRAME} seq={seq} x={x} y=0 z=0 rate=known vx=10 vy=0 vz=0')
        client.append(f'AUTHORITY_CONTINUOUS_WRITE seq={seq} x={x} y=0 z=0 vx=10 vy=0 vz=0 target_x={x+1} target_y=0 target_z=0')
        client.append(f'AUTHORITY_CONTINUOUS_OBSERVE seq={seq} x={x+1} y=0 z=0')
    server.extend(f'REGISTRY_MOTION_NUDGE number={n} before_x={n*5} target_x={n*5+5}' for n in range(1,4))
    return '\n'.join(server),'\n'.join(client)


class MotionEvidenceTests(unittest.TestCase):
    def test_matching_source_writes_and_readbacks(self):
        server,client=logs();result=evidence.validate(server,client,epoch=EPOCH,frame=FRAME)
        self.assertEqual(result['matching_guest_readbacks'],6)
        self.assertFalse(result['gameplay_proven'])

    def test_unknown_rate_is_rejected(self):
        server,client=logs();server=server.replace('rate=known vx=10','rate=unknown vx=10',1)
        with self.assertRaisesRegex(ValueError,'unknown velocity'):
            evidence.validate(server,client,epoch=EPOCH,frame=FRAME)

    def test_missing_readbacks_are_rejected(self):
        server,client=logs()
        client='\n'.join(line for line in client.splitlines() if 'AUTHORITY_CONTINUOUS_OBSERVE' not in line)
        with self.assertRaisesRegex(ValueError,'movement readbacks'):
            evidence.validate(server,client,epoch=EPOCH,frame=FRAME)

    def test_source_sequence_mismatch_is_rejected(self):
        server,client=logs()
        client=client.replace('AUTHORITY_CONTINUOUS_WRITE seq=3 ','AUTHORITY_CONTINUOUS_WRITE seq=99 ',1)
        with self.assertRaisesRegex(ValueError,'unmatched or stale'):
            evidence.validate(server,client,epoch=EPOCH,frame=FRAME)

if __name__=='__main__': unittest.main()
