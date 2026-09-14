#!/usr/bin/python3
"""Unprivileged admin HTTP API; exposed only through a permissioned Unix socket.
Nginx must validate Authentik and overwrite X-Authentik-Username on every request.
"""
import base64
from http import cookies
from http.server import BaseHTTPRequestHandler, HTTPServer
import hashlib
import hmac
import json
import logging
import mimetypes
import os
from pathlib import Path
import re
import secrets
import socket
from socketserver import ThreadingMixIn
import subprocess
import threading
import time
from urllib.parse import unquote,urlsplit
from control import BY_ID

ORIGIN='https://admin.beachlab.org'
COOKIE='__Host-admin-csrf'
WEBROOT=Path(os.environ.get('ADMIN_WEBROOT','/opt/beachlab-admin/frontend/dist')).resolve()
KEYFILE=Path(os.environ.get('ADMIN_KEYFILE','/var/lib/beachlab-admin/csrf.key'))
CACHE={'time':0,'data':None}; CACHE_LOCK=threading.Lock()
ACTION_LOCK=threading.Lock()
LOG=logging.getLogger('beachlab-admin')

def key():
    if not KEYFILE.exists():
        fd=os.open(KEYFILE,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'wb') as f:f.write(secrets.token_bytes(32))
    return KEYFILE.read_bytes()

def issue_token(user,secret):
    body=base64.urlsafe_b64encode(json.dumps([user,int(time.time()),secrets.token_hex(16)]).encode()).decode().rstrip('=')
    return body+'.'+hmac.new(secret,body.encode(),hashlib.sha256).hexdigest()

def valid_token(token,user,secret):
    try:
        body,signature=token.split('.')
        if not hmac.compare_digest(hmac.new(secret,body.encode(),hashlib.sha256).hexdigest(),signature):return False
        owner,created,_=json.loads(base64.urlsafe_b64decode(body+'='*(-len(body)%4)))
        return owner==user and 0<=time.time()-created<43200
    except (ValueError,TypeError):return False

def controller(*args):
    try:
        p=subprocess.run(['/usr/bin/sudo','-n','/usr/local/sbin/beachlab-admin-control',*args],stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=175)
        data=json.loads(p.stdout)
        return data,409 if p.returncode else 200
    except (subprocess.TimeoutExpired,ValueError,OSError):return {'error':'No se pudo consultar el controlador. Actualiza el estado antes de reintentar.'},503

def state():
    with CACHE_LOCK:
        if time.monotonic()-CACHE['time']<2 and CACHE['data'] is not None:return CACHE['data'],200
        data,status=controller('status')
        if status==200:CACHE.update(time=time.monotonic(),data=data)
        return data,status

class Handler(BaseHTTPRequestHandler):
    server_version='Beachlab'
    def log_message(self,fmt,*args):
        # Do not record cookies, query strings, OAuth codes, or user-supplied request lines.
        pass
    def user(self):
        u=self.headers.get('X-Authentik-Username','')
        return u if re.fullmatch(r'[\w.@+-]{1,150}',u) else None
    def response(self,status,data,content_type='application/json',headers=None):
        body=json.dumps(data,ensure_ascii=False).encode() if content_type=='application/json' else data
        self.send_response(status)
        self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store')
        for k,v in (headers or {}).items():self.send_header(k,v)
        self.end_headers()
        if self.command!='HEAD':self.wfile.write(body)
    def do_GET(self):
        user=self.user()
        if not user:return self.response(401,{'error':'Acceso no autenticado.'})
        path=urlsplit(self.path).path
        if path=='/api/state':
            data,status=state()
            if status!=200:return self.response(status,data)
            jar=cookies.SimpleCookie()
            try: jar.load(self.headers.get('Cookie',''))
            except cookies.CookieError: pass
            existing=jar.get(COOKIE)
            token=existing.value if existing and valid_token(existing.value,user,self.server.secret) else issue_token(user,self.server.secret)
            return self.response(200,{**data,'user':user,'csrfToken':token,'busy':ACTION_LOCK.locked()},headers={'Set-Cookie':f'{COOKIE}={token}; Secure; HttpOnly; SameSite=Strict; Path=/'})
        if path.startswith('/api/'):return self.response(404,{'error':'Ruta no encontrada.'})
        candidate=(WEBROOT/unquote(path).lstrip('/')).resolve()
        if not candidate.is_relative_to(WEBROOT):return self.response(404,{'error':'Ruta no encontrada.'})
        if path=='/':candidate=WEBROOT/'index.html'
        if not candidate.is_file():return self.response(404,{'error':'Ruta no encontrada.'})
        return self.response(200,candidate.read_bytes(),mimetypes.guess_type(candidate.name)[0] or 'application/octet-stream')
    def do_HEAD(self):self.do_GET()
    def do_POST(self):
        user=self.user()
        if not user:return self.response(401,{'error':'Acceso no autenticado.'})
        if self.headers.get('Origin')!=ORIGIN or self.headers.get('Content-Type','').split(';')[0]!='application/json':
            return self.response(403,{'error':'Origen de la petición no permitido.'})
        jar=cookies.SimpleCookie()
        try:jar.load(self.headers.get('Cookie',''))
        except cookies.CookieError:return self.response(403,{'error':'Vuelve a cargar el panel.'})
        token=self.headers.get('X-CSRF-Token',''); cookie=jar.get(COOKIE)
        if not cookie or not hmac.compare_digest(cookie.value,token) or not valid_token(token,user,self.server.secret):return self.response(403,{'error':'Vuelve a cargar el panel antes de continuar.'})
        m=re.fullmatch(r'/api/services/([a-z]+)/(?P<action>start|stop)',urlsplit(self.path).path)
        if not m or m[1] not in BY_ID:return self.response(404,{'error':'Operación no encontrada.'})
        try:
            size=int(self.headers.get('Content-Length','0'))
            if size<0 or size>1024:raise ValueError
            payload=json.loads(self.rfile.read(size))
            if payload!={}:raise ValueError
        except (ValueError,TypeError):return self.response(400,{'error':'Petición no válida.'})
        if not ACTION_LOCK.acquire(blocking=False):return self.response(409,{'error':'Espera a que termine la operación actual.'})
        try:
            LOG.info('action actor=%s service=%s operation=%s',user,m[1],m['action'])
            data,status=controller(m['action'],m[1])
            with CACHE_LOCK:CACHE['time']=0
            LOG.info('result actor=%s service=%s operation=%s status=%s',user,m[1],m['action'],status)
            return self.response(status,data)
        finally:ACTION_LOCK.release()

class Server(ThreadingMixIn,HTTPServer):
    address_family=socket.AF_UNIX
    daemon_threads=True
    def server_bind(self):
        self.socket.bind(self.server_address)
        self.server_name='localhost';self.server_port=0

if __name__=='__main__':
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(message)s')
    sock=Path('/run/beachlab-admin/http.sock')
    if sock.exists():sock.unlink()
    server=Server(str(sock),Handler);server.secret=key();sock.chmod(0o660)
    server.serve_forever()
