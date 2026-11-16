"""In-process fake X11 worker; actual signals/socket, never connects to X."""
from pathlib import Path
import json,os,signal,socket,sys,threading
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools/dev'))
import authority_x11_pulse_worker as w
mode=sys.argv[1];parent,child=socket.socketpair();events=[];pressed=[False];checks=[0]
w.scope.verify=lambda *_a,**_k:True
class Fake:
 def __init__(self,*_a,**_k):pass
 def check_window(self):
  if mode=='signal_before_down':os.kill(os.getpid(),signal.SIGTERM)
  if mode=='deadline_before_down':time.sleep(.2)
 def code(self):return 38
 def pressed(self,_):
  checks[0]+=1
  if mode=='signal_during_keycheck' and checks[0]==2:os.kill(os.getpid(),signal.SIGTERM)
  return pressed[0]
 def event(self,_,down):
  pressed[0]=down;events.append('down' if down else 'up')
  if down and mode=='exception_after_down':raise RuntimeError('after possible dispatch')
  if down and mode=='signal_after_down':os.kill(os.getpid(),signal.SIGTERM)
 def close(self):pass
w.X11=Fake
import time
config={'scope':{},'mode':'pulse','code':None,'duration':.05,'deadline':time.monotonic()+(.1 if mode=='deadline_before_down' else 3)}
def supervisor():
 parent.sendall((json.dumps(config)+'\n').encode())
 data=b''
 while not data.endswith(b'\n'):data+=parent.recv(100)
 assert json.loads(data)['event']=='READY'
 parent.sendall(b'G')
 while parent.recv(512):pass
thread=threading.Thread(target=supervisor);thread.start();sys.argv=['worker',str(child.detach())]
rc=w.main();thread.join(3);parent.close()
expected=[] if mode in ('signal_before_down','signal_during_keycheck','deadline_before_down') else ['down','up']
assert events==expected and not pressed[0],(mode,events,pressed)
assert rc==(0 if mode=='ok' else 1)
