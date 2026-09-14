#!/usr/bin/python3 -I
"""Root-only allowlisted service controller. Never accepts commands or paths from HTTP.
Inventory verified on thebeachlab 2026-09-14. systemd dependencies are authoritative;
Docker daemon and hardware are observation-only, so the panel cannot stop shared infrastructure.
"""
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

SERVICES = [
    dict(id='comfyui', name='ComfyUI', description='Generación de imágenes', group='ai', unit='comfyui.service', url='https://comfyui.beachlab.org/', dependencies=['egpu'], icon='image'),
    dict(id='qwen', name='Qwen3-TTS', description='Síntesis de voz', group='ai', unit='qwen3-tts.service', url='https://beachlab.org/tts/', dependencies=['egpu'], icon='audio'),
    dict(id='whisper', name='Whisper', description='Transcripción de audio', group='ai', unit='whisper-web.service', url='https://beachlab.org/whisper/', dependencies=['egpu'], icon='mic'),
    dict(id='rag', name='Biblioteca RAG', description='Ingesta de documentos', group='ai', unit='rag-library-ingest.service', dependencies=['egpu'], icon='file'),
    dict(id='transmission', name='Transmission', description='Descargas a través de VPN', group='apps', container='transmission-vpn', compose='/home/pink/docker/transmission-vpn/docker-compose.yml', compose_service='transmission-vpn', image='haugene/transmission-openvpn:latest', url='https://beachlab.org/transmission/web/', dependencies=['docker','vpn'], icon='download'),
    dict(id='browser', name='Navegador remoto', description='Chromium aislado', group='apps', unit='remote-browser.service', url='https://beachlab.org/browser/', dependencies=['docker','firewall'], icon='monitor'),
    dict(id='drop', name='Drop', description='Descargas por URL', group='apps', unit='url-drop.service', url='https://beachlab.org/drop/', dependencies=[], icon='link'),
    dict(id='minecraft', name='Minecraft Java', description='Servidor Fabric', group='games', unit='minecraft-java.service', connection='beachlab.org:25565', dependencies=[], icon='box'),
    dict(id='grafana', name='Grafana', description='Métricas y paneles', group='monitoring', container='grafana', url='https://grafana.beachlab.org/', dependencies=['docker'], icon='chart'),
    dict(id='gotify', name='Gotify', description='Servidor de notificaciones', group='monitoring', container='gotify', url='https://ntfy.beachlab.org/', dependencies=['docker'], icon='bell'),
    dict(id='igotify', name='iGotify', description='Notificaciones en iOS', group='monitoring', container='igotify', dependencies=['docker','gotify'], icon='phone'),
    dict(id='titiler', name='TiTiler', description='Procesamiento de mapas', group='monitoring', container='titiler', dependencies=['docker'], icon='map'),
]
BY_ID = {s['id']: s for s in SERVICES}
AI_IDS = {s['id'] for s in SERVICES if s['group'] == 'ai'}
BUSY = {'active','activating','reloading','deactivating'}

class ControlError(Exception):
    pass

def run(args, timeout=8, check=False):
    try:
        p = subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout,
                           env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','LANG':'C.UTF-8'})
    except subprocess.TimeoutExpired:
        raise ControlError('El servicio no respondió a tiempo. Comprueba su estado antes de reintentar.') from None
    if check and p.returncode:
        raise ControlError('La operación ha fallado. Consulta el diario del servicio en el servidor.')
    return p

def unit_states():
    units=[s['unit'] for s in SERVICES if 'unit' in s]+['docker.service','remote-browser-firewall.service']
    p=run(['/usr/bin/systemctl','show',*units,'--property=Id,LoadState,ActiveState,SubState,Result'])
    if p.returncode: raise ControlError('No se pudo consultar systemd.')
    return {d['Id']:d for block in p.stdout.strip().split('\n\n') if (d:=dict(l.split('=',1) for l in block.splitlines() if '=' in l)) and 'Id' in d}

def containers():
    names=[s['container'] for s in SERVICES if 'container' in s]
    p=run(['/usr/bin/docker','inspect',*names],timeout=10)
    # docker inspect returns nonzero for an absent container but valid JSON for the rest.
    try: return {x['Name'].lstrip('/'):x for x in json.loads(p.stdout or '[]')}
    except (ValueError,KeyError): raise ControlError('No se pudo consultar Docker.') from None

def gpu():
    if not Path('/dev/nvidiactl').exists(): return {'id':'egpu','name':'eGPU · RTX 2070 SUPER','state':'inactive','message':'Enciende y conecta la eGPU físicamente.'}
    try:
        p=run(['/usr/bin/nvidia-smi','--query-gpu=name,memory.used,memory.total','--format=csv,noheader,nounits'],timeout=5)
        if p.returncode: raise ControlError('GPU no disponible')
        name,used,total=p.stdout.strip().splitlines()[0].rsplit(',',2)
        return {'id':'egpu','name':'eGPU · '+name.replace('NVIDIA GeForce ','').strip(),'state':'active','message':f'{used.strip()} / {total.strip()} MiB · La GPU se enciende físicamente.'}
    except (ControlError,ValueError,IndexError):
        return {'id':'egpu','name':'eGPU','state':'failed','message':'La GPU no responde. Revisa la conexión física.'}

def snapshot():
    us=unit_states(); cs=containers()
    deps={'egpu':gpu()}
    for id,unit,name,message in [('docker','docker.service','Docker','Servicios en contenedores.'),('firewall','remote-browser-firewall.service','Cortafuegos','Aislamiento del navegador remoto.')]:
        deps[id]={'id':id,'name':name,'state':us.get(unit,{}).get('ActiveState','unknown'),'message':message}
    t=cs.get('transmission-vpn',{}).get('State',{})
    deps['vpn']={'id':'vpn','name':'VPN integrada','state':'active' if t.get('Health',{}).get('Status')=='healthy' else 'unknown' if t.get('Running') else 'inactive','message':'Arranca junto con Transmission. El túnel lo gestiona el contenedor.'}
    rows=[]
    for s in SERVICES:
        item={k:v for k,v in s.items() if k not in ('unit','compose','compose_service','image','container')}
        if 'unit' in s:
            u=us.get(s['unit'],{}); state=u.get('ActiveState','unknown')
            installed=u.get('LoadState')=='loaded'
            detail=u.get('SubState',''); ready=state=='active'; running=state in BUSY
        else:
            c=cs.get(s['container']); st=(c or {}).get('State',{})
            installed=bool(c) or bool(s.get('compose') and Path(s['compose']).is_file())
            running=bool(st.get('Running')) or bool(st.get('Restarting'))
            health=st.get('Health',{}).get('Status')
            state='failed' if st.get('Dead') else 'degraded' if health=='unhealthy' else 'activating' if st.get('Restarting') or health=='starting' else 'active' if running else 'inactive'
            detail=health or st.get('Status','not-created'); ready=running and state=='active'
        item.update(state=state,detail=detail,running=running,ready=ready,installed=installed,blocked=None)
        rows.append(item)
    active_gpu=[x['name'] for x in rows if x['id'] in AI_IDS and x['running']]
    for item in rows:
        if not item['installed']:item['blocked']='El servicio no está instalado.'
        elif not item['running'] and item['id'] in AI_IDS:
            if deps['egpu']['state']!='active': item['blocked']=deps['egpu']['message']
            elif active_gpu:item['blocked']='Apaga primero '+', '.join(active_gpu)+': comparten la memoria de la GPU.'
        if not item['running'] and 'docker' in item['dependencies'] and deps['docker']['state']!='active':item['blocked']='Docker no está disponible. Requiere intervención en el servidor.'
    mem=dict((k,int(v.split()[0])) for l in Path('/proc/meminfo').read_text().splitlines() if ':' in l for k,v in [l.split(':',1)])
    disk=shutil.disk_usage('/')
    return {'services':rows,'dependencies':deps,'host':os.uname().nodename,'metrics':{'load':round(os.getloadavg()[0],2),'cpus':os.cpu_count(),'memoryUsed':(mem['MemTotal']-mem['MemAvailable'])*1024,'memoryTotal':mem['MemTotal']*1024,'diskUsed':disk.used,'diskTotal':disk.total},'updatedAt':time.time()}

def plan(action,id,state):
    if id not in BY_ID or action not in ('start','stop'): raise ControlError('Servicio u operación no permitidos.')
    rows={x['id']:x for x in state['services']}; row=rows[id]; s=BY_ID[id]
    if action=='start' and row['blocked']:raise ControlError(row['blocked'])
    if action=='stop':
        dependents=[x['name'] for x in state['services'] if id in x['dependencies'] and x['running']]
        if dependents:raise ControlError('Apaga primero '+', '.join(dependents)+'.')
    if action=='start' and row['running'] or action=='stop' and not row['running']:return []
    cmds=[]
    if action=='start' and id=='igotify' and not rows['gotify']['running']:cmds.append(['/usr/bin/docker','start','gotify'])
    if 'unit' in s:cmds.append(['/usr/bin/systemctl',action,s['unit']])
    elif action=='start' and 'compose' in s:
        cmds.append(['/usr/bin/docker','image','inspect',s['image']])
        cmds.append(['/usr/bin/docker','compose','-f',s['compose'],'up','-d','--no-build','--pull','never',s['compose_service']])
    else:cmds.append(['/usr/bin/docker',action,*( ['--time','60'] if action=='stop' else [] ),s['container']])
    return cmds

def main():
    if os.geteuid()!=0:raise ControlError('El controlador requiere su autorización de sistema.')
    args=sys.argv[1:]
    if args==['status']:return snapshot()
    if len(args)!=2 or args[0] not in ('start','stop') or args[1] not in BY_ID:raise ControlError('Servicio u operación no permitidos.')
    with open('/run/beachlab-admin-control.lock','w') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ControlError('Hay otra operación en curso.') from None
        state=snapshot(); commands=plan(*args,state)
        for command in commands:run(command,timeout=150,check=True)
        # Return success only when the service actually reached its requested state.
        current={x['id']:x for x in snapshot()['services']}[args[1]]
        if args[0]=='start' and not current['running']:raise ControlError('El servicio no ha arrancado. Consulta su diario.')
        if args[0]=='stop' and current['running']:raise ControlError('El servicio sigue en marcha. Comprueba su estado.')
        return {'ok':True,'service':args[1],'state':current['state']}

if __name__=='__main__':
    try: print(json.dumps(main(),ensure_ascii=False))
    except (ControlError,OSError) as e:
        print(json.dumps({'error':str(e) if isinstance(e,ControlError) else 'No se pudo completar la operación de sistema.'},ensure_ascii=False));sys.exit(1)
