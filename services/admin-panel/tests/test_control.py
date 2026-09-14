import importlib.util
from pathlib import Path
import unittest
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from unittest.mock import patch

def load(name):
 spec=importlib.util.spec_from_file_location(name,Path(__file__).resolve().parents[1]/(name+'.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
c=load('control');web=load('server')

def state():
 return {'services':[dict(id=s['id'],name=s['name'],running=False,blocked=None,dependencies=s['dependencies']) for s in c.SERVICES]}

class ControllerTests(unittest.TestCase):
 def test_unknown_service_and_shell_input_rejected(self):
  for id in ['ssh','docker','minecraft; reboot','../etc/passwd']:
   with self.assertRaises(c.ControlError):c.plan('start',id,state())
 def test_hardware_or_gpu_conflict_blocks_start(self):
  s=state();s['services'][0]['blocked']='GPU ocupada'
  with self.assertRaisesRegex(c.ControlError,'GPU ocupada'):c.plan('start','comfyui',s)
 def test_shared_dependency_cannot_stop_while_in_use(self):
  s=state()
  for r in s['services']:
   if r['id'] in ['gotify','igotify']:r['running']=True
  with self.assertRaisesRegex(c.ControlError,'iGotify'):c.plan('stop','gotify',s)
 def test_dependency_starts_before_consumer(self):
  self.assertEqual(c.plan('start','igotify',state()),[['/usr/bin/docker','start','gotify'],['/usr/bin/docker','start','igotify']])
 def test_transmission_preserves_compose_vpn_and_never_pulls(self):
  commands=c.plan('start','transmission',state());cmd=commands[-1]
  self.assertIn('/home/pink/docker/transmission-vpn/docker-compose.yml',cmd)
  self.assertIn('--no-build',cmd);self.assertEqual(cmd[cmd.index('--pull')+1],'never')
 def test_browser_uses_existing_systemd_dependencies(self):
  self.assertEqual(c.plan('start','browser',state()),[['/usr/bin/systemctl','start','remote-browser.service']])
 def test_already_started_is_noop(self):
  s=state();s['services'][0]['running']=True
  self.assertEqual(c.plan('start','comfyui',s),[])
 def test_minecraft_uses_graceful_service_not_legacy_unit(self):
  s=state();next(r for r in s['services'] if r['id']=='minecraft')['running']=True
  self.assertEqual(c.plan('stop','minecraft',s),[['/usr/bin/systemctl','stop','minecraft-java.service']])

class CsrfTests(unittest.TestCase):
 def test_token_bound_to_user_and_secret(self):
  t=web.issue_token('fran',b'key')
  self.assertTrue(web.valid_token(t,'fran',b'key'))
  self.assertFalse(web.valid_token(t,'fran-jr',b'key'))
  self.assertFalse(web.valid_token(t,'fran',b'other'))
  self.assertFalse(web.valid_token(t+'x','fran',b'key'))
 def test_expired_and_malformed_tokens_rejected(self):
  with patch.object(web.time,'time',return_value=100):t=web.issue_token('fran',b'key')
  self.assertFalse(web.valid_token(t,'fran',b'key'))
  for t in ['', 'x','x.y','%.foo']:self.assertFalse(web.valid_token(t,'fran',b'key'))

if __name__=='__main__':unittest.main()
