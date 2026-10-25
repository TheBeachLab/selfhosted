"""Real HTTP boundary with a mocked privileged controller."""
import http.client
from http.server import HTTPServer
import json
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server

class BackupHttpTests(unittest.TestCase):
 def setUp(self):
  self.http=HTTPServer(('127.0.0.1',0),server.Handler)
  self.http.secret=b'fixture-secret'
  self.thread=threading.Thread(target=self.http.serve_forever,daemon=True)
  self.thread.start()
  self.token=server.issue_token('fran',self.http.secret)
 def tearDown(self):
  self.http.shutdown();self.http.server_close();self.thread.join()
 def request(self,path='/api/services/minecraft/backup',headers=None,body='{}',method='POST'):
  h={'X-Authentik-Username':'fran','Origin':server.ORIGIN,'Content-Type':'application/json','X-CSRF-Token':self.token,'Cookie':server.COOKIE+'='+self.token}
  if headers:h.update(headers)
  conn=http.client.HTTPConnection(*self.http.server_address)
  conn.request(method,path,body,h);response=conn.getresponse();result=(response.status,response.read());conn.close();return result
 def test_valid_post_schedules_only_fixed_command(self):
  with patch.object(server,'controller',return_value=({'ok':True},200)) as control:
   self.assertEqual(self.request()[0],200);control.assert_called_once_with('backup','minecraft')
 def test_untrusted_requests_never_reach_controller(self):
  with patch.object(server,'controller') as control:
   for headers,status in [({'X-Authentik-Username':''},401),({'Origin':'https://wrong.example'},403),({'X-CSRF-Token':'bad'},403)]:
    self.assertEqual(self.request(headers=headers)[0],status)
   self.assertEqual(self.request(body=json.dumps({'path':'/tmp/other'}))[0],400)
   self.assertEqual(self.request(path='/api/services/grafana/backup')[0],404)
   self.assertEqual(self.request(method='GET')[0],404)
   control.assert_not_called()

if __name__=='__main__':unittest.main()
