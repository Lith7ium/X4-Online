#!/usr/bin/env python3
"""Opt-in, isolated single-fixture MD velocity diagnostic; never import-launches X4."""
import argparse
import json
import math
from pathlib import Path
import shutil
import sys

import authority_fixture_warp_live as base


def install_probe(case, profile):
    base.install_probe(case, profile)
    lab=case/'extensions/x4_lan_lab';ui=lab/'ui';md=lab/'md'
    (ui/'authority_fixture_warp_probe.lua').unlink()
    (md/'authority_fixture_warp.xml').unlink()
    shutil.copyfile(base.REPO/'tools/dev/authority_fixture_velocity_probe.lua', ui/'authority_fixture_velocity_probe.lua')
    shutil.copyfile(base.REPO/'tools/dev/authority_fixture_velocity.xml', md/'authority_fixture_velocity.xml')
    (lab/'ui.xml').write_text(base.extension.ui_xml([*base.extension.BASE_UI,'ui/authority_fixture_velocity_probe.lua']),encoding='utf-8')
    (ui/'config.lua').write_text('X4LAN_CONFIG = {enabled=false, test_profile="45841", authority_fixture_velocity=true, '
        'authority_fixture_save_path='+base.load.lua_literal(str(profile/'save'))+'}\n',encoding='ascii')


class VelocityWatch(base.WarpWatch):
    TAG=b'[X4LAN] AUTH_VELOCITY '
    LABELS=(b'LOAD_ARMED',b'LOAD_REQUEST',b'LOADED',b'BEFORE',b'BASE',b'REQUEST_START',b'ACK_START',
            b'MOVING1',b'MOVING2',b'REQUEST_STOP',b'ACK_STOP',b'STOP1',b'STOP2')
    SAMPLES=(b'BEFORE',b'BASE',b'MOVING1',b'MOVING2',b'STOP1',b'STOP2')
    TIMED=(b'BASE',b'MOVING1',b'MOVING2',b'STOP1',b'STOP2')


def check_measurements(watch):
    if watch.stage!=len(watch.LABELS):raise ValueError('incomplete velocity receipts')
    samples=watch.samples
    for first,last in (('MOVING1','MOVING2'),('STOP1','STOP2')):
        if samples[last][3] < 2 or not .5 <= samples[last][3]-samples[first][3] <= 3:
            raise ValueError('invalid sample interval')
    baseline=math.dist(samples['BEFORE'][:3],samples['BASE'][:3])
    moved1=math.dist(samples['BASE'][:3],samples['MOVING1'][:3])
    moved2=math.dist(samples['MOVING1'][:3],samples['MOVING2'][:3])
    stopped=math.dist(samples['STOP1'][:3],samples['STOP2'][:3])
    if baseline>.5 or not 2<=moved1<=50 or not 2<=moved2<=50 or stopped>1:
        raise ValueError('baseline, motion or reset displacement outside bounds')
    return {'baseline_displacement_m':baseline,'first_motion_displacement_m':moved1,
            'second_motion_displacement_m':moved2,'post_reset_displacement_m':stopped,
            'motion_interval_s':samples['MOVING2'][3]-samples['MOVING1'][3],
            'post_reset_interval_s':samples['STOP2'][3]-samples['STOP1'][3],
            'native_velocity_vector_readback':False}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game',type=Path,required=True);parser.add_argument('--bundle',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True);parser.add_argument('--display',required=True)
    parser.add_argument('--timeout',type=float,default=600);parser.add_argument('--seed',type=int,default=276944566)
    args=parser.parse_args(argv)
    try:
        result=base.run(args,install=install_probe,watch_class=VelocityWatch,check=check_measurements,
            scope='one disposable X4 instance; one fixture MD velocity start and zero reset; no multiplayer')
    except (OSError,ValueError,RuntimeError) as error:parser.exit(1,'REFUSED: '+str(error)+'\n')
    print(json.dumps(result,indent=2));return 0 if result['success'] else 1

if __name__=='__main__':sys.exit(main())
