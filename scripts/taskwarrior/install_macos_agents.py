#!/usr/bin/env python3
"""Install the user's SSH tunnel and two-minute Taskwarrior sync LaunchAgents.

Requires the local binary, ~/.taskrc and client certificates to be provisioned
first. Refuses to overwrite existing agents. See doc/taskserver.md.
"""
from pathlib import Path
import os
import sys
import plistlib
import subprocess

home=Path.home()
logs=home/'Library/Logs/Taskwarrior'
logs.mkdir(parents=True,exist_ok=True)
agents=home/'Library/LaunchAgents'
agents.mkdir(parents=True,exist_ok=True)
for suffix,arguments,options in (
    ('tunnel',['/usr/bin/ssh','-N','-o','BatchMode=yes','-o','ExitOnForwardFailure=yes',
               '-o','ServerAliveInterval=30','-o','ServerAliveCountMax=3',
               '-L','127.0.0.1:53590:127.0.0.1:53590','pink-sudo'],
     {'KeepAlive':True,'RunAtLoad':True,'ThrottleInterval':30}),
    ('sync',['/opt/homebrew/bin/task','rc.verbose=nothing','sync'],
     {'StartInterval':120,'RunAtLoad':True}),
):
    label='com.beachlab.taskwarrior-'+suffix
    path=agents/(label+'.plist')
    config={'Label':label,'ProgramArguments':arguments,**options,
            'EnvironmentVariables':{'HOME':str(home)},
            'StandardOutPath':str(logs/(suffix+'.log')),
            'StandardErrorPath':str(logs/(suffix+'.log'))}
    if path.exists():
        # Permit a matching existing agent without disturbing its running process.
        existing=plistlib.loads(path.read_bytes())
        if existing['ProgramArguments']==arguments:
            print(f'Already installed: {label}')
            continue
        if '--replace-existing' not in sys.argv:
            raise RuntimeError(f'Existing agent differs: {path}; use --replace-existing for an authorized migration')
        backup=path.with_suffix('.plist.pre-taskchampion')
        if not backup.exists():
            backup.write_bytes(path.read_bytes())
        subprocess.run(['launchctl','bootout',f'gui/{os.getuid()}/'+label],check=False,capture_output=True)
    path.write_bytes(plistlib.dumps(config))
    subprocess.run(['launchctl','bootstrap',f'gui/{os.getuid()}',str(path)],check=True)
    print(f'Installed: {label}')
