"""Evidence checker tests with synthetic files and logs; no X4 is started."""
import gzip
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('authority_loopback_restart_evidence',ROOT/'tools/dev/authority_loopback_restart_evidence.py')
EVIDENCE=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(EVIDENCE)
from authority.checkpoints import CheckpointStore
from test_authority_trusted_marker_load_session import XML, MARKER


class EvidenceTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup); self.root=Path(self.temp.name)
        self.source_path=self.root/'source'; self.source_path.mkdir(); self.source=CheckpointStore(self.source_path)
        self.source_cp=self.checkpoint(self.source,1)
        self.first=self.root/'first';self.second=self.root/'second'
        for path in (self.first,self.second): path.mkdir();(path/'checkpoints').mkdir()
        self.store_a=CheckpointStore(self.first/'checkpoints');self.store_b=CheckpointStore(self.second/'checkpoints')
        self.a=[self.checkpoint(self.store_a,i) for i in (2,3,4)]
        self.b=[self.checkpoint(self.store_b,i) for i in (5,6)]
        self.write_server(self.first,self.source_cp,self.a[-1],['pause','save','resume','pause','save','resume','pause','save'])
        self.write_server(self.second,self.a[-1],self.b[-1],['pause','save','resume','pause','save'])
        self.probe_a=self.root/'probe_a';self.probe_b=self.root/'probe_b'
        self.write_probe(self.probe_a,self.a[:2]);self.write_probe(self.probe_b,self.b[:1])
    def checkpoint(self,store,index):
        marker='%032x'%index; path=self.root/('save-%d.gz'%index)
        path.write_bytes(gzip.compress(XML.replace(MARKER,marker).encode()))
        cp=store.publish(path,marker=marker);store.confirm(cp);return cp
    def write_server(self,path,source,final,operations):
        data={'success':True,'supervisor_version':1,'owned_processes_remaining':[],
              'final_world_state':'paused','source_checkpoint_id':source.checkpoint_id,'source_sha256':source.sha256,
              'load_marker_observed':True,'pause_observed':True,'engine_operations':operations,
              'final_checkpoint_id':final.checkpoint_id,'final_checkpoint_sha256':final.sha256}
        (path/'result.json').write_text(json.dumps(data))
        log=path/'case/home/.config/EgoSoft/X4/45841/engine-output.log';log.parent.mkdir(parents=True)
        log.write_text('[X4LAN] AUTH_RECOVERY REQUEST\n[X4LAN] AUTH_MARKER load INSPECTED '+source.marker+
                       '\n[X4LAN] AUTH_RECOVERY PAUSED\n')
    def write_probe(self,path,checkpoints):
        path.mkdir();rows=[]
        for index,cp in enumerate(checkpoints,1):
            folder=path/('download-%d'%index);folder.mkdir();shutil.copyfile(cp.path,folder/'save.xml.gz')
            rows.append({'checkpoint_id':cp.checkpoint_id,'sha256':cp.sha256,'size':cp.size,'marker':cp.marker,
                         'transfer_verified':True,'client_x4_load_simulated':True,'participant_controls_simulated':True})
        (path/'result.json').write_text(json.dumps({'success':True,'client_x4_load_simulated':True,
             'gameplay_tested':False,'windows_tested':False,'internet_tested':False,'attempts':rows}))
    def verify(self):
        with patch.object(EVIDENCE.source,'DEFAULT_STORE',self.source_path), \
             patch.object(EVIDENCE.load,'local_directory',side_effect=lambda path: Path(path)):
            return EVIDENCE.verify(self.first,self.probe_a,self.second,self.probe_b)
    def test_chain_and_download_bytes(self):
        value=self.verify(); self.assertTrue(value['success']);self.assertTrue(value['client_x4_load_simulated'])
        (self.probe_b/'download-1/save.xml.gz').write_bytes(b'corrupted')
        with self.assertRaises(ValueError): self.verify()
    def test_incorrect_restart_source_and_duplicate_log_fail(self):
        path=self.second/'result.json';result=json.loads(path.read_text());result['source_sha256']='0'*64
        path.write_text(json.dumps(result))
        with self.assertRaises(ValueError): self.verify()
        result['source_sha256']=self.a[-1].sha256;path.write_text(json.dumps(result))
        log=self.second/'case/home/.config/EgoSoft/X4/45841/engine-output.log'
        with log.open('a') as file: file.write('[X4LAN] AUTH_RECOVERY PAUSED\n')
        with self.assertRaises(ValueError): self.verify()


if __name__=='__main__': unittest.main()
