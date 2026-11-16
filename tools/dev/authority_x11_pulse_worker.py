#!/usr/bin/env python3
"""Private XTEST worker. No X11 connection until private scope verifies."""
import ctypes as C
import json
import os
import select
import signal
import socket
import sys
import time
import authority_x11_private_scope as scope

KEY='a'  # One bounded lateral-strafe key in the historical test layout.
class X11:
 def __init__(self,s,*,verify_window):
    scope.verify(s,require_x4=verify_window)
    os.environ['DISPLAY']=s['display'];os.environ['XAUTHORITY']=s['auth']
    self.x=C.CDLL('libX11.so.6');self.xt=C.CDLL('libXtst.so.6')
    self.x.XOpenDisplay.argtypes=[C.c_char_p];self.x.XOpenDisplay.restype=C.c_void_p
    self.x.XCloseDisplay.argtypes=[C.c_void_p];self.x.XSync.argtypes=[C.c_void_p,C.c_int]
    self.x.XGetInputFocus.argtypes=[C.c_void_p,C.POINTER(C.c_ulong),C.POINTER(C.c_int)]
    self.x.XInternAtom.argtypes=[C.c_void_p,C.c_char_p,C.c_int];self.x.XInternAtom.restype=C.c_ulong
    self.x.XGetWindowProperty.argtypes=[C.c_void_p,C.c_ulong,C.c_ulong,C.c_long,C.c_long,C.c_int,C.c_ulong,
     C.POINTER(C.c_ulong),C.POINTER(C.c_int),C.POINTER(C.c_ulong),C.POINTER(C.c_ulong),C.POINTER(C.POINTER(C.c_ubyte))]
    self.x.XFree.argtypes=[C.c_void_p];self.x.XStringToKeysym.argtypes=[C.c_char_p];self.x.XStringToKeysym.restype=C.c_ulong
    self.x.XKeysymToKeycode.argtypes=[C.c_void_p,C.c_ulong];self.x.XKeysymToKeycode.restype=C.c_ubyte
    self.x.XQueryKeymap.argtypes=[C.c_void_p,C.c_void_p];self.xt.XTestFakeKeyEvent.argtypes=[C.c_void_p,C.c_uint,C.c_int,C.c_ulong]
    self.d=self.x.XOpenDisplay(s['display'].encode('ascii'))
    if not self.d:raise RuntimeError('private X display unavailable')
    self.scope=s;self.closed=False
    try:
     scope.verify(s,require_x4=verify_window)
     if verify_window:self.check_window()
    except BaseException:self.close();raise
 def close(self):
    if not self.closed:self.x.XCloseDisplay(self.d);self.closed=True
 def check_window(self):
    s=self.scope;scope.verify(s)
    atom=self.x.XInternAtom(self.d,b'_NET_WM_PID',1)
    if not atom:raise RuntimeError('window PID property absent')
    actual=C.c_ulong();fmt=C.c_int();n=C.c_ulong();left=C.c_ulong();data=C.POINTER(C.c_ubyte)()
    status=self.x.XGetWindowProperty(self.d,s['window'],atom,0,1,0,6,C.byref(actual),C.byref(fmt),C.byref(n),C.byref(left),C.byref(data))
    try:
     if status!=0 or actual.value!=6 or fmt.value!=32 or n.value!=1 or left.value!=0 or not data:
      raise RuntimeError('invalid window PID property')
     if C.cast(data,C.POINTER(C.c_ulong))[0]!=s['x4_pid']:raise RuntimeError('window not owned by X4')
    finally:
     if data:self.x.XFree(data)
    focus=C.c_ulong();revert=C.c_int();self.x.XGetInputFocus(self.d,C.byref(focus),C.byref(revert))
    if focus.value!=s['window']:raise RuntimeError('X4 window not focused')
    scope.verify(s)
 def code(self):
    k=self.x.XKeysymToKeycode(self.d,self.x.XStringToKeysym(KEY.encode('ascii')))
    if not k:raise RuntimeError('key mapping unavailable')
    return int(k)
 def pressed(self,code):
    keys=C.create_string_buffer(32)
    if not self.x.XQueryKeymap(self.d,keys):raise RuntimeError('keyboard state unavailable')
    return bool(keys.raw[code//8] & (1<<(code%8)))
 def event(self,code,down):
    if not self.xt.XTestFakeKeyEvent(self.d,code,int(down),0):raise RuntimeError('XTEST refused key event')
    self.x.XSync(self.d,0)

def _read_config(ipc):
 ipc.settimeout(5);raw=b''
 while not raw.endswith(b'\n'):
  part=ipc.recv(8193-len(raw))
  if not part or len(raw)+len(part)>8192:raise ValueError('invalid configuration')
  raw+=part
 obj=json.loads(raw.decode('ascii'))
 if type(obj) is not dict or set(obj)!={'scope','mode','code','duration','deadline'}:raise ValueError('bad configuration')
 return obj

def _send(ipc,obj):ipc.sendall((json.dumps(obj,separators=(',',':'))+'\n').encode('ascii'))

def main():
 if len(sys.argv)!=2:return 2
 ipc=socket.socket(fileno=int(sys.argv[1]));x=None;down=False;key=None;cancel=[False]
 def cancel_signal(*_):cancel[0]=True
 for n in (signal.SIGINT,signal.SIGTERM,signal.SIGHUP):signal.signal(n,cancel_signal)
 try:
  cfg=_read_config(ipc);s=cfg['scope'];deadline=cfg['deadline'];mode=cfg['mode']
  if type(deadline) not in (int,float) or deadline!=deadline or not time.monotonic()<deadline<=time.monotonic()+15:raise ValueError('invalid deadline')
  if mode=='release':
   key=cfg['code']
   if type(key) is not int or not 8<=key<=255:raise ValueError('invalid release keycode')
   x=X11(s,verify_window=False)
   if x.pressed(key):x.event(key,False)
   if x.pressed(key):raise RuntimeError('key release unconfirmed')
   scope.verify(s,require_x4=False);_send(ipc,{'event':'RELEASED'});return 0
  if mode!='pulse' or cfg['code'] is not None or type(cfg['duration']) not in (int,float) or not .05<=cfg['duration']<=.5:
   raise ValueError('invalid pulse configuration')
  x=X11(s,verify_window=True);key=x.code()
  if x.pressed(key):raise RuntimeError('key already held')
  _send(ipc,{'event':'READY','keycode':key})
  ipc.setblocking(False);go=b''
  while not go:
   if cancel[0] or time.monotonic()>=deadline:raise TimeoutError('pulse authorization expired')
   if select.select([ipc],[],[],min(.05,max(0,deadline-time.monotonic())))[0]:
    go=ipc.recv(1)
    if go==b'':raise EOFError('control closed')
  if go!=b'G':raise ValueError('invalid authorization')
  x.check_window()
  if x.pressed(key):raise RuntimeError('key no longer neutral')
  # The X11 and scope calls above may be slow; authorization is no longer
  # valid if a signal or deadline arrived while they were in progress.
  if cancel[0] or time.monotonic()>=deadline:raise TimeoutError('pulse authorization expired before key down')
  down=True;x.event(key,True)
  if not x.pressed(key):raise RuntimeError('key down not observed')
  _send(ipc,{'event':'DOWN'});until=min(deadline,time.monotonic()+cfg['duration'])
  while not cancel[0] and time.monotonic()<until:
   if select.select([ipc],[],[],min(.02,until-time.monotonic()))[0]:
    msg=ipc.recv(1)
    if msg in (b'',b'S'):cancel[0]=True
    else:raise ValueError('unexpected command')
  x.event(key,False);down=False
  if x.pressed(key):raise RuntimeError('key up unconfirmed')
  scope.verify(s,require_x4=False);_send(ipc,{'event':'UP'})
  if cancel[0]:return 1
  x.check_window();_send(ipc,{'event':'DONE'});return 0
 except BaseException:
  return 1
 finally:
  if x is not None:
   if down and key is not None:
    try:x.event(key,False)
    except BaseException:pass
   try:x.close()
   except BaseException:pass
  ipc.close()
if __name__=='__main__':sys.exit(main())
