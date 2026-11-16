"""Real-process fake for supervisor tests; never connects to a display."""
import json,os,socket,sys,time
s=socket.socket(fileno=int(sys.argv[1]));data=b''
while not data.endswith(b'\n'):data+=s.recv(4096)
c=json.loads(data);mode=os.environ.get('FAKE_PULSE_MODE','ok')
def send(d):s.sendall((json.dumps(d)+'\n').encode())
if c['mode']=='release':
 if mode!='release_fail':send({'event':'RELEASED'})
 sys.exit(0 if mode!='release_fail' else 1)
send({'event':'READY','keycode':38})
if s.recv(1)!=b'G':sys.exit(2)
if mode in ('crash_after_go','release_fail'):sys.exit(1)
send({'event':'DOWN'})
if mode=='crash_after_down':sys.exit(1)
send({'event':'UP'});send({'event':'DONE'})
sys.exit(0)
