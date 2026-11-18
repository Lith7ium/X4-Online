"""Add one opt-in source-motion owner to an existing private recovery probe.

No process or socket is started. Caller must establish checkpoint provenance,
process/socket ownership and a confirmed remote STOP before any world pause.
"""
import math
import re
from pathlib import Path
import authority_load_live as load

ROOT=Path(__file__).resolve().parents[2]
HEX=re.compile(r'[0-9a-f]{32}\Z')
MODULES=(
 ('tools/dev/authority_registry_resolve_string.lua','authority_registry_resolve_string.lua'),
 ('tools/dev/authority_job_descriptor_probe.lua','authority_job_descriptor_probe.lua'),
 ('src/authority/lua/saved_baseline_source_bootstrap.lua','saved_baseline_source_bootstrap.lua'),
 ('src/authority/lua/source_motion_sampler.lua','source_motion_sampler.lua'),
 ('src/authority/lua/source_motion_ipc.lua','source_motion_ipc.lua'),
 ('src/authority/lua/source_motion_shutdown.lua','source_motion_shutdown.lua'),
 ('tools/dev/authority_recovered_source_motion.lua','authority_recovered_source_motion.lua'),
)


def install(case,profile,status,settings):
    """Extend disposable recovery files; return every changed/new protected path."""
    if (type(status) is not tuple or len(status)!=4 or status[0]!='ready' or
        type(status[1]) is not str or not HEX.fullmatch(status[1]) or
        type(status[2]) is not int or not 1<=status[2]<=200000 or
        type(status[3]) is not str or not re.fullmatch(r'[0-9a-f]{64}',status[3])):
        raise ValueError('confirmed registry status required')
    fields={'port','lease','attempt','generation','nonce','saved_nonce','timeout'}
    allowed_fields = (fields, fields | {'selection'}, fields | {'local_pair'})
    if type(settings) is not dict or (set(settings) - {'real_time_motion'}) not in allowed_fields:
        raise ValueError('invalid motion settings')
    real_time_motion = settings.get('real_time_motion', False)
    if type(real_time_motion) is not bool or (real_time_motion and ('selection' in settings or 'local_pair' in settings)):
        raise ValueError('real-time motion requires baseline-only mode')
    if type(settings['port']) is not int or not 1<=settings['port']<=65535:
        raise ValueError('invalid motion port')
    if (type(settings['timeout']) not in (int,float) or not math.isfinite(settings['timeout']) or
        not 0<settings['timeout']<=120):raise ValueError('invalid motion timeout')
    tokens=[settings[k] for k in ('lease','attempt','generation','nonce','saved_nonce')]
    selection=settings.get('selection')
    if 'selection' in settings and selection is None:raise ValueError('invalid bounded candidate selection')
    if selection is not None:
        if (type(selection) is not dict or set(selection)!={'nonce','candidates'} or
            type(selection['nonce']) is not str or not HEX.fullmatch(selection['nonce']) or
            type(selection['candidates']) is not tuple or not 1<=len(selection['candidates'])<=32 or
            any(type(n) is not int or not 1<=n<=status[2] for n in selection['candidates']) or
            len(set(selection['candidates']))!=len(selection['candidates']) or
            selection['nonce'][:16] in (settings['nonce'][:16],settings['saved_nonce'][:16])):
            raise ValueError('invalid bounded candidate selection')
        tokens.append(selection['nonce'])
    local_pair=settings.get('local_pair')
    if 'local_pair' in settings and (type(local_pair) is not dict or
        set(local_pair) not in ({'nonce','index'}, {'nonce','index','delivery'}) or
        ('delivery' in local_pair and local_pair['delivery'] is not True) or
        type(local_pair['nonce']) is not str or not HEX.fullmatch(local_pair['nonce']) or
        type(local_pair['index']) is not int or not 1<=local_pair['index']<=status[2] or
        local_pair['nonce'][:16] in (settings['nonce'][:16],settings['saved_nonce'][:16])):
        raise ValueError('invalid local pair context')
    if local_pair is not None:tokens.append(local_pair['nonce'])
    if (any(type(t) is not str or not HEX.fullmatch(t) for t in tokens) or
        len(set(tokens+[status[1]]))!=len(tokens)+1 or settings['nonce'][:16]==settings['saved_nonce'][:16]):
        raise ValueError('invalid or colliding motion context')
    case=Path(case);profile=Path(profile)
    if (case.is_symlink() or profile.is_symlink() or not profile.resolve().is_relative_to(case.resolve()) or
        profile.name!='45841' or (profile/'save').is_symlink() or not (profile/'save').is_dir()):
        raise ValueError('private 45841 profile required')
    lab=case/'extensions/x4_lan_lab';ui=lab/'ui';md=lab/'md'
    if any(p.is_symlink() or not p.is_dir() for p in (lab,ui,md)):
        raise ValueError('invalid recovery extension')
    config=ui/'config.lua';manifest=lab/'ui.xml';probe=ui/'authority_world_bridge_probe.lua'
    if any(p.is_symlink() or not p.is_file() for p in (config,manifest,probe,md/'authority_ship_registry.xml')):
        raise ValueError('recovery owner or registry unavailable')
    cfg=config.read_text(encoding='ascii');mf=manifest.read_text(encoding='utf-8');owner=probe.read_text(encoding='utf-8')
    if not cfg.endswith('}\n') or 'authority_recovered_source_motion=' in cfg or re.search(r'\bauthority_motion_[A-Za-z0-9_]+\s*=',cfg):
        raise ValueError('invalid or already extended recovery config')
    expected_path='authority_load_save_path='+load.lua_literal(str(profile/'save'))
    if (cfg.count('authority_load_save_path=')!=1 or
        not re.search(re.escape(expected_path)+r'(?=,|})',cfg)):
        raise ValueError('recovery save path differs from private profile')
    saved_expected=re.findall(r'authority_registry_expected="([0-9a-f]{32}\|[1-9][0-9]*)"',cfg)
    if saved_expected!=[status[1]+'|'+str(status[2])]:
        raise ValueError('motion registry differs from recovery owner')
    control=re.search(r'authority_control_port=([0-9]+)',cfg)
    old_tokens=re.findall(r'authority_(?:control_lease|world_epoch)="([0-9a-f]{32})"',cfg)
    if (not control or int(control.group(1))==settings['port'] or len(old_tokens)!=2 or
        len(set(tokens+[status[1]]+old_tokens))!=len(tokens)+3):raise ValueError('motion and recovery contexts overlap')
    manifest_hook='    <file name="ui/authority_world_bridge_probe.lua" />\n'
    owner_hook=" local ok,reason=bridge:update();assert(ok,reason)\n"
    state_hook='local activated=false\n'
    if (mf.count(manifest_hook)!=1 or owner.count(owner_hook)!=1 or owner.count(state_hook)!=1 or
            owner.count("SetScript('onUpdate'")!=1):
        raise ValueError('recovery owner hook missing or ambiguous')
    modules=list(MODULES)
    if selection is not None:modules.insert(-1,('tools/dev/authority_registry_motion_candidate.lua','authority_registry_motion_candidate.lua'))
    if local_pair is not None:modules.insert(-1,('src/authority/lua/source_motion_local_pair.lua','source_motion_local_pair.lua'))
    files=[ui/name for _,name in modules]+[md/'authority_job_descriptor_probe.xml']
    if selection is not None:files.append(md/'authority_registry_motion_candidate.xml')
    if any(path.exists() or path.is_symlink() for path in files):raise ValueError('motion overlay would overwrite existing files')
    # All resources and hooks were validated before writing; this case is a
    # caller-owned disposable profile, never the normal X4 profile.
    for (source,_),target in zip(modules,files):
        with target.open('xb') as f:f.write((ROOT/source).read_bytes())
    with (md/'authority_job_descriptor_probe.xml').open('xb') as f:f.write((ROOT/'tools/dev/authority_job_descriptor_probe.xml').read_bytes())
    if selection is not None:
        with (md/'authority_registry_motion_candidate.xml').open('xb') as f:f.write((ROOT/'tools/dev/authority_registry_motion_candidate.xml').read_bytes())
    module_xml=''.join('    <file name="ui/'+name+'" />\n' for _,name in modules)
    manifest.write_text(mf.replace(manifest_hook,module_xml+manifest_hook),encoding='utf-8')
    add=',authority_recovered_source_motion=true,authority_motion_epoch="'+status[1]+'",authority_motion_baseline='+str(status[2])
    add+=',authority_motion_port='+str(settings['port'])+',authority_motion_timeout='+format(settings['timeout'],'.17g')
    if real_time_motion:
        add+=',authority_motion_real_time=true'
    for name in ('lease','attempt','generation','nonce','saved_nonce'):
        add+=',authority_motion_'+name+'="'+settings[name]+'"'
    if selection is not None:
        add+=',authority_motion_candidate_nonce="'+selection['nonce']+'",authority_motion_candidate_indices={'
        add+=','.join(str(n) for n in selection['candidates'])+'}'
    if local_pair is not None:
        add+=',authority_motion_pair_nonce="'+local_pair['nonce']+'",authority_motion_pair_index='+str(local_pair['index'])
    config.write_text(cfg[:-2]+add+'}\n',encoding='ascii');config.chmod(0o600)
    owner_add=''' if cfg.authority_recovered_source_motion then
  if not recovered_motion and not C.IsGamePaused() then
   recovered_motion=assert(X4LAN_RECOVERED_SOURCE_MOTION.new_x4({port=cfg.authority_motion_port,
    epoch=cfg.authority_motion_epoch,baseline=cfg.authority_motion_baseline,timeout=cfg.authority_motion_timeout,
    lease=cfg.authority_motion_lease,attempt=cfg.authority_motion_attempt,generation=cfg.authority_motion_generation,
    nonce=cfg.authority_motion_nonce,saved_nonce=cfg.authority_motion_saved_nonce,expected_save_path=cfg.authority_load_save_path}))
  end
  if recovered_motion then assert(recovered_motion:tick())end
 end
'''
    if real_time_motion:
        owner_add=owner_add.replace('expected_save_path=cfg.authority_load_save_path}))',
            'expected_save_path=cfg.authority_load_save_path,real_time_motion=cfg.authority_motion_real_time}))')
    if selection is not None:
        owner_add=owner_add.replace('expected_save_path=cfg.authority_load_save_path}))',
            'expected_save_path=cfg.authority_load_save_path,selection={nonce=cfg.authority_motion_candidate_nonce,candidates=cfg.authority_motion_candidate_indices}}))')
    if local_pair is not None:
        delivery=',delivery=true' if local_pair.get('delivery') is True else ''
        owner_add=owner_add.replace('expected_save_path=cfg.authority_load_save_path}))',
            'expected_save_path=cfg.authority_load_save_path,local_pair={nonce=cfg.authority_motion_pair_nonce,index=cfg.authority_motion_pair_index'+delivery+'}}))')
    owner=owner.replace(state_hook,state_hook+'local recovered_motion=nil\n')
    probe.write_text(owner.replace(owner_hook,owner_hook+owner_add),encoding='utf-8')
    return [config,manifest,probe,*files]
