"""Put a kit's server on a Linux machine: python tools/deploy_playtest_server.py --kit KIT --ssh root@ADDRESS

For a kit made with tools/make_playtest_kit.py --server ADDRESS. The server needs the kit's checkout, overlay and
server.json (not the snapshot, not X4) and Python 3.10 or newer. This tool copies those three over ssh and sets up:

  <dir>/kits/<name>/{repo,overlay,server.json}   the kit's server files (<dir>/current points at them)
  <dir>/runs/                                    each game's relay files and the players' logs
  /etc/systemd/system/<service>.service          python3 repo/tools/x4ls.py serve ..., as --user, restarted if it ends
  ufw: UDP <port> (the session), TCP <port + 1> (the lobby and the logs) and TCP <port> (the join files of a drop-in
       game), when ufw is there

A kit has its own key and its own overlay, so every new kit is deployed again; players of an older kit are then
refused with the reason. The restart ends a game that is running.

ssh must reach the machine without a question (a key, an agent). Nothing of this is stored in the repository: the
address and the key are the kit's."""
import argparse
import io
import ipaddress
import json
import re
import shlex
import subprocess
import sys
import tarfile
import time
from pathlib import Path

UNIT = """[Unit]
Description=X4 lockstep playtest server (x4ls serve: lobby and relay)
After=network-online.target
Wants=network-online.target

[Service]
User={user}
WorkingDirectory={dir}/current
ExecStart=/usr/bin/python3 -u repo/tools/x4ls.py serve --overlay overlay --server-file server.json --bind 0.0.0.0 --runs {dir}/runs
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
"""

REMOTE = """set -e
chmod 600 -- {server_file}
ln -sfn -- {kit_link} {current}
mkdir -p -- {runs}
chown -R -- {owner} {dir}
cat > {unit_file} <<'UNIT'
{unit}UNIT
systemctl daemon-reload
systemctl enable {service} >/dev/null 2>&1
systemctl restart {service}
if command -v ufw >/dev/null 2>&1; then
  ufw allow {udp} comment 'x4 lockstep relay' >/dev/null
  ufw allow {lobby} comment 'x4 lockstep lobby' >/dev/null
  ufw allow {join} comment 'x4 lockstep join files' >/dev/null
fi
sleep 2
systemctl is-active {service}
journalctl -u {service} -n 5 --no-pager -o cat
"""

_ACCOUNT = re.compile(r'[a-z_][a-z0-9_-]{0,31}\Z')
_SERVICE = re.compile(r'[a-z][a-z0-9_-]{0,62}\Z')
_COMMIT = re.compile(r'[0-9a-f]{40}\Z')
_SSH_USER = re.compile(r'[A-Za-z0-9_][A-Za-z0-9_.-]*')
_SSH_HOST = re.compile(r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,252}')
_IPV6_SCOPE = re.compile(r'[A-Za-z0-9_.-]+')
_FOLDER_PART = re.compile(r'[A-Za-z0-9_][A-Za-z0-9_.-]*\Z')


def ssh_destination(target):
    error_message = 'SSH destination must be [user@]hostname, SSH alias, IPv4 or IPv6'
    if not isinstance(target, str):
        raise ValueError(error_message)
    username, separator, host = target.rpartition('@')
    if separator and not _SSH_USER.fullmatch(username):
        raise ValueError(error_message)
    if _SSH_HOST.fullmatch(host):
        return target
    if host.startswith('[') and host.endswith(']'):
        host = host[1:-1]
    address, scope_separator, scope = host.partition('%')
    if scope_separator and not _IPV6_SCOPE.fullmatch(scope):
        raise ValueError(error_message)
    try:
        ipaddress.IPv6Address(address)
    except ipaddress.AddressValueError as error:
        raise ValueError(error_message) from error
    return f'{username}{separator}{host}'


def deployment_plan(*, ssh_target, user, folder, service, server, manifest, name_time):
    """Validate every remote input before constructing shell or unit text."""
    if not isinstance(user, str) or not _ACCOUNT.fullmatch(user):
        raise ValueError('invalid server account')
    if not isinstance(service, str) or not _SERVICE.fullmatch(service):
        raise ValueError('invalid systemd service name')
    destination = ssh_destination(ssh_target)
    if (not isinstance(folder, str) or not folder.startswith('/') or folder == '/' or
            not all(_FOLDER_PART.fullmatch(part) and part not in ('.', '..')
                    for part in folder[1:].split('/'))):
        raise ValueError('invalid absolute deployment directory')
    if (not isinstance(manifest, dict) or not isinstance(manifest.get('commit'), str)
            or not _COMMIT.fullmatch(manifest['commit'])):
        raise ValueError('invalid kit commit')
    if (not isinstance(server, dict) or type(server.get('port')) is not int or
            not 1 <= server['port'] <= 65534 or not isinstance(server.get('host'), str)):
        raise ValueError('invalid kit server port or host')
    try:
        ipaddress.IPv4Address(server['host'])
    except ipaddress.AddressValueError as error:
        raise ValueError('kit server host must be IPv4') from error
    if not re.fullmatch(r'[0-9]{8}-[0-9]{6}', name_time):
        raise ValueError('invalid deployment timestamp')
    name = f'{name_time}-{manifest["commit"][:12]}'
    target = f'{folder}/kits/{name}'
    q = shlex.quote
    unit = UNIT.format(user=user, dir=folder)
    if '\r' in unit or '\nUNIT\n' in unit:
        raise ValueError('invalid systemd unit content')
    remote = REMOTE.format(server_file=q(f'{target}/server.json'),
        kit_link=q(f'kits/{name}'), current=q(f'{folder}/current'),
        runs=q(f'{folder}/runs'), owner=q(f'{user}:'), dir=q(folder),
        unit_file=q(f'/etc/systemd/system/{service}.service'), unit=unit,
        service=q(service), udp=q(f'{server["port"]}/udp'),
        lobby=q(f'{server["port"] + 1}/tcp'), join=q(f'{server["port"]}/tcp'))
    extract = (f'umask 077; mkdir -p -- {q(target)} && '
               f'tar xzf - --no-same-owner --no-same-permissions -C {q(target)}')
    return {'name': name, 'target': target,
            'ssh': ['ssh', '-o', 'BatchMode=yes', '--', destination],
            'extract': extract, 'remote': remote}


def pack(kit):
    """repo/, overlay/ and server.json of a kit as a tar.gz in memory (run folders and caches left out)."""
    def archive_item(item):
        if '/.local' in item.name or '__pycache__' in item.name:
            return None
        if not (item.isfile() or item.isdir()):
            raise ValueError('kit archive contains a link or special file')
        if item.name == 'server.json':
            item.mode = 0o600
        return item

    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode='w:gz') as tar:
        for name in ('repo', 'overlay', 'server.json'):
            tar.add(kit / name, arcname=name, filter=archive_item)
    return data.getvalue()


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--kit', type=Path, required=True, help='a kit folder made with make_playtest_kit.py --server')
    p.add_argument('--ssh', required=True, metavar='[USER@]HOST',
        help='SSH alias or address for an account with permission to write the systemd unit')
    p.add_argument('--user', default='x4server', help='the account the server runs as (default x4server)')
    p.add_argument('--dir', default='', help='where it lives (default /home/<user>/lockstep-lobby)')
    p.add_argument('--service', default='x4mp-lobby')
    args = p.parse_args(argv)
    if not (args.kit / 'server.json').is_file():
        p.error(f'{args.kit} has no server.json: build the kit with make_playtest_kit.py --server ADDRESS')
    server = json.loads((args.kit / 'server.json').read_text())
    manifest = json.loads((args.kit / 'kit-manifest.json').read_text())
    folder = args.dir or f'/home/{args.user}/lockstep-lobby'
    try:
        plan = deployment_plan(ssh_target=args.ssh, user=args.user, folder=folder,
            service=args.service, server=server, manifest=manifest,
            name_time=time.strftime('%Y%m%d-%H%M%S'))
    except ValueError as error:
        p.error(str(error))
    data = pack(args.kit)
    print(f'copying {len(data) // 1024} KiB to {args.ssh}:{plan["target"]}')
    subprocess.run([*plan['ssh'], plan['extract']], input=data, check=True)
    done = subprocess.run([*plan['ssh'], 'bash -s'], input=plan['remote'].encode(), capture_output=True)
    print(done.stdout.decode(errors='replace').strip())
    if done.returncode:
        print(done.stderr.decode(errors='replace').strip(), file=sys.stderr)
        return 1
    print(f'server {server["host"]}: UDP {server["port"]}, TCP {server["port"] + 1}; service {args.service}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
