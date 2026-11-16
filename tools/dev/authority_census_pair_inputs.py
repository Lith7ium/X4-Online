"""Read-only pinned census evidence and isolated dual staging; no X4 starts.

Provenance is verified once; a single source read writes two fresh save slots.
Neither saved component references nor local handles are network identities.
"""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import stat
import types

import authority_census_archive_provenance as archive
import authority_sector_read_live as base

WITNESS_SHA256='006b07a39be4cff6a3fac7555b26d40ffe834594304c231dd659b23bfdc85349'
WITNESS_PATH=base.ROOT/'.local/authority-census-sector-witness-all-01.json'
_MAX_WITNESS_BYTES=4*1024*1024
_MACRO=re.compile(r'[A-Za-z0-9_.-]{1,128}\Z',re.ASCII)
_REF=re.compile(r'\[0x[1-9a-f][0-9a-f]{0,15}\]\Z',re.ASCII)


@dataclass(frozen=True)
class VerifiedInputs:
    source_path: Path
    source_fingerprint: tuple
    archive_fingerprints: dict
    witness_sha256: str
    witness_candidates: object


def _unique_pairs(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('duplicate witness JSON key')
        result[key]=value
    return result


def _file_fingerprint(path):
    s=path.lstat()
    if not stat.S_ISREG(s.st_mode):raise ValueError('expected regular evidence file')
    return s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns


def load_witness(path=WITNESS_PATH):
    """Read pinned immutable bytes once and validate all 152/10054 mappings."""
    path=Path(path)
    # The caller's local artifact directory may not be a symlink; the final
    # file itself is opened O_NOFOLLOW by the stable evidence reader.
    parent=path.parent.lstat()
    if not stat.S_ISDIR(parent.st_mode) or stat.S_ISLNK(parent.st_mode):raise ValueError('invalid witness directory')
    identity,digest,raw=base.stable_read(path,_MAX_WITNESS_BYTES,collect=True)
    parent_after=path.parent.lstat()
    if (digest!=WITNESS_SHA256 or _file_fingerprint(path)!=identity or
        (parent.st_dev,parent.st_ino,parent.st_mode)!=(parent_after.st_dev,parent_after.st_ino,parent_after.st_mode)):
        raise ValueError('witness file differs or was replaced')
    try:
        def bad_constant(_):raise ValueError('invalid JSON constant')
        data=json.loads(raw.decode('utf-8'),object_pairs_hook=_unique_pairs,parse_constant=bad_constant)
    except (UnicodeError,ValueError,RecursionError) as error:
        raise ValueError('invalid witness JSON') from error
    fields={'saved_sector_count','saved_registry_count','runtime_binding_proven','cross_instance_frame_identity_proven',
            'exact_loaded_file_proven','registry_entries_without_sector_witness','scope','checkpoint_id','sha256',
            'registry_epoch','sectors'}
    if type(data) is not dict or set(data)!=fields:raise ValueError('invalid witness fields')
    if (type(data['saved_sector_count']) is not int or data['saved_sector_count']!=152
        or type(data['saved_registry_count']) is not int or data['saved_registry_count']!=archive.COUNT
        or type(data['registry_entries_without_sector_witness']) is not int
        or data['registry_entries_without_sector_witness']!=0
        or data['scope']!='one pinned census checkpoint; saved structural evidence only'
        or (data['checkpoint_id'],data['sha256'],data['registry_epoch'])!=(archive.CHECKPOINT_ID,archive.SHA256,archive.REGISTRY_EPOCH)
        or any(data[k] is not False for k in ('runtime_binding_proven','cross_instance_frame_identity_proven','exact_loaded_file_proven'))):
        raise ValueError('witness provenance mismatch')
    sectors=data['sectors'];names=[];refs=set();seen=set();eligible={}
    if type(sectors) is not list or len(sectors)!=152:raise ValueError('invalid witness sector count')
    for row in sectors:
        if type(row) is not dict or set(row)!={'sector_macro','sector_saved_component_ref','witnesses'}:
            raise ValueError('invalid sector witness fields')
        name,ref,items=row['sector_macro'],row['sector_saved_component_ref'],row['witnesses']
        if (type(name) is not str or not _MACRO.fullmatch(name) or name.casefold() in names
                or type(ref) is not str or not _REF.fullmatch(ref) or ref in refs or type(items) is not list):
            raise ValueError('invalid or duplicate saved sector')
        names.append(name.casefold());refs.add(ref);previous=0;candidates=[]
        for item in items:
            if type(item) is not dict or set(item)!={'index','saved_under_dockingbay','saved_immediate_parent_zone'}:
                raise ValueError('invalid saved witness')
            index=item['index'];docked=item['saved_under_dockingbay'];zone=item['saved_immediate_parent_zone']
            if (type(index) is not int or not previous<index<=archive.COUNT or index in seen
                    or type(docked) is not bool or type(zone) is not bool):raise ValueError('invalid witness index or flags')
            previous=index;seen.add(index)
            if not docked and zone:candidates.append(index)
        eligible[name]=tuple(candidates)
    if names!=sorted(names) or seen!=set(range(1,archive.COUNT+1)):
        raise ValueError('incomplete or unsorted saved witnesses')
    return types.MappingProxyType(eligible)


def verify_once(store_path,witness_path=WITNESS_PATH):
    """Verify one pinned source and a previously generated witness artifact."""
    store=Path(os.path.abspath(store_path))
    if store!=archive.DEFAULT_STORE.resolve(strict=True):raise ValueError('only pinned census store supported')
    before=archive.fingerprints(store)
    evidence=archive.verify(store)  # one full provenance operation only
    if (evidence['checkpoint_id'],evidence['sha256'],evidence['registry_epoch'],evidence['registry_entries'])!=(
        archive.CHECKPOINT_ID,archive.SHA256,archive.REGISTRY_EPOCH,archive.COUNT):
        raise ValueError('unexpected archive evidence')
    if (evidence.get('current_equals_confirmed') is not True or evidence.get('saved_marker_matches') is not True
            or evidence.get('forward_reverse_match') is not True or evidence.get('runtime_binding_proven') is not False
            or evidence.get('exact_loaded_file_proven') is not False):
        raise ValueError('archive provenance incomplete')
    witness=load_witness(witness_path)
    if archive.fingerprints(store)!=before:raise ValueError('archive changed during input verification')
    source=store/archive.CHECKPOINT_ID/'save.xml.gz'
    fp=before[str(source)]
    return VerifiedInputs(source,fp,before,WITNESS_SHA256,witness)


def _stat_tuple(s):return s.st_dev,s.st_ino,s.st_mode,s.st_size,s.st_mtime_ns,s.st_ctime_ns


def stage_pair(verified,profiles):
    """Read source bytes once and write two exclusively created private slots."""
    if not isinstance(verified,VerifiedInputs) or type(profiles) is not dict or set(profiles)!={'server','client'}:
        raise ValueError('invalid staging request')
    save_dirs={role:Path(profile)/'save' for role,profile in profiles.items()}
    if save_dirs['server'].resolve()==save_dirs['client'].resolve():raise ValueError('profiles must be distinct')
    if any(p.is_relative_to(verified.source_path.parent.parent.parent) or
           verified.source_path.parent.parent.parent.is_relative_to(p) for p in (d.resolve() for d in save_dirs.values())):
        raise ValueError('staging and source must be disjoint')
    source_fd=os.open(verified.source_path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    directory_fds=[];directory_identities={};targets={};writers=[]
    try:
        before=os.fstat(source_fd)
        if not stat.S_ISREG(before.st_mode) or _stat_tuple(before)!=verified.source_fingerprint:
            raise ValueError('verified source identity changed')
        for role,directory in save_dirs.items():
            dfd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC);directory_fds.append(dfd)
            dstat=os.fstat(dfd)
            if not stat.S_ISDIR(dstat.st_mode) or os.listdir(dfd):raise ValueError('private save directory not empty')
            directory_identities[role]=(dstat.st_dev,dstat.st_ino,dstat.st_mode)
            fd=os.open(base.snapshot.SLOT,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=dfd)
            writer=os.fdopen(fd,'wb');writers.append(writer);targets[role]=directory/base.snapshot.SLOT
        import hashlib
        digest=hashlib.sha256();size=0
        while True:
            part=os.read(source_fd,1024*1024)
            if not part:break
            size+=len(part)
            if size>archive.SIZE:raise ValueError('source grew during staging')
            digest.update(part)
            for writer in writers:writer.write(part)
        after=os.fstat(source_fd)
        if (_stat_tuple(after)!=_stat_tuple(before) or _stat_tuple(verified.source_path.lstat())!=_stat_tuple(before)
            or (size,digest.hexdigest())!=(archive.SIZE,archive.SHA256)):
            raise ValueError('source changed during staging')
        for writer in writers:writer.flush();os.fsync(writer.fileno())
        for writer in writers:writer.close()
        writers=[]
        results={}
        for role,target in targets.items():
            current=save_dirs[role].lstat()
            if (current.st_dev,current.st_ino,current.st_mode)!=directory_identities[role]:
                raise ValueError('private save directory changed')
            fingerprint,sha,_=base.stable_read(target,archive.SIZE,collect=False)
            if sha!=archive.SHA256 or fingerprint[2]!=archive.SIZE or _file_fingerprint(target)!=fingerprint:
                raise ValueError('staged save differs')
            results[role]=(target,fingerprint,sha)
        identities=[result[1][:2] for result in results.values()]
        if len(set(identities))!=2 or (before.st_dev,before.st_ino) in identities:
            raise ValueError('staged saves do not have independent identities')
        for role,directory in save_dirs.items():
            current=directory.lstat()
            if (current.st_dev,current.st_ino,current.st_mode)!=directory_identities[role]:
                raise ValueError('private save directory changed after staging')
        if archive.fingerprints(verified.source_path.parent.parent)!=verified.archive_fingerprints:
            raise ValueError('archive changed during staging')
        return results
    finally:
        failures=[]
        for writer in writers:
            try:writer.close()
            except BaseException as error:failures.append(error)
        for fd in (*directory_fds,source_fd):
            try:os.close(fd)
            except BaseException as error:failures.append(error)
        if failures:raise RuntimeError('staging descriptor cleanup unconfirmed') from failures[0]
