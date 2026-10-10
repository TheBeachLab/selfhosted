#!/usr/bin/env python3
"""Bridge stdio to the private, read-only HTTP MCP endpoint on the NUC.

Run as msgvault. Credentials stay on the NUC, outside argv and client config.
https://github.com/sparfenyuk/mcp-proxy#1-stdio-to-ssestreamablehttp
"""
import os
from pathlib import Path
import re

config = Path("/var/lib/msgvault/mcp.toml").read_text()
server = config.partition("[remote]")[0]
keys = re.findall(r'^api_key = "([0-9a-f]{64})"$', server, re.M)
if len(keys) != 1:
    raise SystemExit("Expected one MCP key in the server section.")
environment = dict(os.environ)
environment["API_ACCESS_TOKEN"] = keys[0]
python = "/opt/msgvault/mcp-venv/bin/python"
bridge = "/opt/msgvault/deployment/mcp-proxy-compat.py"
os.execve(python, [python, bridge], environment)
