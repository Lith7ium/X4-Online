#!/usr/bin/env python3
"""Check two completed isolated supervisor runs and their simulated clients.

This reads only local artifacts and never launches X4. It verifies saved bytes,
markers, recorded engine transitions, and recovery log receipts. Client X4
observations and participant controls in the paired probes were simulated.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools/dev')]
import authority_load_live as load
import authority_recovery_join_source as source
import authority_recovery_live as recovery
from authority.checkpoints import Checkpoint, CheckpointStore
from authority.marker_evidence import verify_saved_marker
from authority.load_messages import _pairs, _reject_constant
from authority_recovered_loopback_server import read_evidence, verify_final_recovery


def result(path):
    try:
        value=json.loads(read_evidence(Path(path)/'result.json').decode('utf-8'),object_pairs_hook=_pairs,
                         parse_constant=_reject_constant)
    except (UnicodeError,json.JSONDecodeError,RecursionError) as error: raise ValueError('invalid result') from error
    if type(value) is not dict or value.get('success') is not True: raise ValueError('run did not succeed')
    return value


def server(path, expected_source, operations):
    path=load.local_directory(path); data=result(path); store=CheckpointStore(path/'checkpoints')
    if (data.get('supervisor_version')!=1 or data.get('owned_processes_remaining')!=[] or
            'cleanup_error' in data or 'cleanup_errors' in data or data.get('final_world_state')!='paused' or
            data.get('load_marker_observed') is not True or data.get('pause_observed') is not True or
            data.get('source_checkpoint_id')!=expected_source.checkpoint_id or
            data.get('source_sha256')!=expected_source.sha256):
        raise ValueError('server recovery or cleanup evidence differs')
    actual_ops=[x for x in data.get('engine_operations',[]) if x in ('pause','resume','save')]
    if actual_ops != operations: raise ValueError('server engine operation sequence differs')
    watch=recovery.RecoveryWatch(path/'case/home/.config/EgoSoft/X4/45841/engine-output.log',expected_source.marker)
    verify_final_recovery(watch)
    checkpoint=store.latest_marked_confirmed()
    if (checkpoint.checkpoint_id!=data.get('final_checkpoint_id') or checkpoint.sha256!=data.get('final_checkpoint_sha256')):
        raise ValueError('server final checkpoint differs')
    verify_saved_marker(checkpoint,checkpoint.marker,script_name='X4AuthorityCheckpointMarker',cue_name='MarkerState')
    return store, checkpoint


def probe(path, store, count):
    path=load.local_directory(path); data=result(path); rows=data.get('attempts')
    if (data.get('client_x4_load_simulated') is not True or data.get('gameplay_tested') is not False or
            data.get('windows_tested') is not False or data.get('internet_tested') is not False or
            type(rows) is not list or len(rows)!=count):
        raise ValueError('probe scope differs')
    checkpoints=[]
    for index,row in enumerate(rows,1):
        if (type(row) is not dict or row.get('transfer_verified') is not True or
                row.get('client_x4_load_simulated') is not True or row.get('participant_controls_simulated') is not True):
            raise ValueError('probe attempt is incomplete or not labeled simulated')
        cp=store.get(row.get('checkpoint_id'))
        if (cp.sha256!=row.get('sha256') or cp.size!=row.get('size') or cp.marker!=row.get('marker')):
            raise ValueError('offered checkpoint differs from server store')
        directory=path/('download-'+str(index))
        if directory.is_symlink() or not directory.is_dir(): raise ValueError('download directory missing')
        files=list(directory.iterdir())
        if len(files)!=1 or files[0].is_symlink() or not files[0].is_file():
            raise ValueError('download file is missing or ambiguous')
        received=Checkpoint(cp.checkpoint_id,files[0],cp.sha256,cp.size,cp.marker)
        verify_saved_marker(received,cp.marker,script_name='X4AuthorityCheckpointMarker',cue_name='MarkerState')
        checkpoints.append(cp)
    if len(checkpoints)==2 and (checkpoints[0].checkpoint_id==checkpoints[1].checkpoint_id or
                                checkpoints[0].marker==checkpoints[1].marker):
        raise ValueError('second join did not use a fresh checkpoint')
    return checkpoints


def verify(first_path, first_probe, second_path, second_probe):
    source_cp=CheckpointStore(source.DEFAULT_STORE).latest_marked_confirmed()
    store_a,final_a=server(first_path,source_cp,['pause','save','resume','pause','save','resume','pause','save'])
    offers_a=probe(first_probe,store_a,2)
    if final_a.checkpoint_id==offers_a[-1].checkpoint_id or final_a.marker==offers_a[-1].marker:
        raise ValueError('first server has no fresh final checkpoint')
    store_b,final_b=server(second_path,final_a,['pause','save','resume','pause','save'])
    offers_b=probe(second_probe,store_b,1)
    if final_b.checkpoint_id==offers_b[-1].checkpoint_id or final_b.marker==offers_b[-1].marker:
        raise ValueError('restarted server has no fresh final checkpoint')
    return {'success':True,'scope':'isolated Linux server recovery and local save transfers; client X4 events simulated',
            'first_offers':[cp.checkpoint_id for cp in offers_a], 'first_final':final_a.checkpoint_id,
            'restart_source':final_a.checkpoint_id,'second_final':final_b.checkpoint_id,
            'client_x4_load_simulated':True,'gameplay_tested':False,'windows_tested':False,'internet_tested':False,
            'exact_loaded_file_proven':False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--first',type=Path,required=True);p.add_argument('--first-probe',type=Path,required=True)
    p.add_argument('--second',type=Path,required=True);p.add_argument('--second-probe',type=Path,required=True)
    a=p.parse_args()
    try: value=verify(a.first,a.first_probe,a.second,a.second_probe)
    except (OSError,ValueError,RuntimeError) as error: p.exit(1,'FAILED: '+str(error)+'\n')
    print(json.dumps(value,indent=2));return 0

if __name__=='__main__': sys.exit(main())
