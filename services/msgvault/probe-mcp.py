#!/usr/bin/env python3
"""Check the private HTTP MCP endpoint and the same stdio command as Watson."""
import asyncio
import json
from pathlib import Path
import re

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client

WRITE_TOOLS = {
    "stage_deletion", "create_saved_view", "update_saved_view", "delete_saved_view",
    "export_attachment", "promote_person", "update_person_notes",
}


async def inspect_session(session, label):
    initialized = await session.initialize()
    listed = await session.list_tools()
    names = {tool.name for tool in listed.tools}
    assert "get_stats" in names and not names.intersection(WRITE_TOOLS)
    if label == "stdio bridge":
        sql = next(tool for tool in listed.tools if tool.name == "query_sql")
        assert sql.outputSchema["type"] == "object"
        assert len(sql.outputSchema["oneOf"]) == 2
    result = await session.call_tool("get_stats", {})
    assert not result.isError, "Statistics tool failed."
    if label == "stdio bridge":
        query = await session.call_tool("query_sql", {"sql": "SELECT 1 AS check_value"})
        assert not query.isError, "Read-only SQL tool failed after schema normalization."
    response_keys = []
    for item in result.content:
        if item.type == "text":
            try:
                data = json.loads(item.text)
                if isinstance(data, dict):
                    response_keys = list(data)
            except json.JSONDecodeError:
                pass
    print(json.dumps({"transport": label, "server": initialized.serverInfo.name,
                      "tools": len(names), "writes_exposed": False,
                      "stats_call": "ok", "stats_response_keys": response_keys}))


async def main():
    config = Path("/var/lib/msgvault/mcp.toml").read_text()
    key = re.search(r'^api_key = "([0-9a-f]{64})"$', config, re.M).group(1)
    async with httpx.AsyncClient(headers={"Authorization": "Bearer " + key}) as http:
        denied = await http.get("http://127.0.0.1:8096/api/v1/stats")
        assert denied.status_code == 401, "MCP key must not authenticate to the owner REST API."
        async with streamable_http_client("http://127.0.0.1:8097/mcp", http_client=http) as (read, write, _):
            async with ClientSession(read, write) as session:
                await inspect_session(session, "HTTP")
    process = StdioServerParameters(command="/usr/bin/sudo", args=[
        "-n", "-u", "msgvault", "/usr/local/bin/msgvault-mcp-client",
    ])
    async with stdio_client(process) as (read, write):
        async with ClientSession(read, write) as session:
            await inspect_session(session, "stdio bridge")


if __name__ == "__main__":
    asyncio.run(main())
