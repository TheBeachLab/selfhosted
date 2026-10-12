"""Isolated browser QA only; hard bound to loopback and a temporary empty DB.

Not used by the production systemd service. No source credentials/data are read.
Browser auth is injected by this test fixture, not by the production app.
"""
import os
from pathlib import Path
import tempfile

import uvicorn

from buchhaltung.api import create_app
from buchhaltung.config import Config


def main():
    port = 8765
    os.umask(0o077)
    with tempfile.TemporaryDirectory(prefix="buchhaltung-browser-qa-") as temp:
        config = Config(Path(temp), "http://127.0.0.1:8765", "isolated-qa-only-"+"x"*32, b"q"*32,
                        dist=Path(__file__).resolve().parents[1]/"frontend/dist",
                        validator=Path(__file__).resolve().parents[1]/"vendor/xrechnung")
        application = create_app(config)
        class Fixture:
            async def __call__(self, scope, receive, send):
                if scope['type']=='http':
                    scope['headers']=[(k,v) for k,v in scope['headers'] if k.lower() not in (b'x-authentik-username',b'x-buchhaltung-proxy')]
                    scope['headers'] += [(b'x-authentik-username',b'fran'),(b'x-buchhaltung-proxy',config.proxy_secret.encode())]
                await application(scope, receive, send)
        uvicorn.run(Fixture(),host="127.0.0.1",port=port,access_log=False)


if __name__=='__main__':main()
