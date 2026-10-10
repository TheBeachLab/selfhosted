#!/usr/bin/env python3
"""Proxy msgvault's HTTP tools to stdio with its redundant object type explicit.

Observed with msgvault 0.21.0 and OpenClaw 2026.9.9: query_sql's outputSchema
is oneOf two object schemas without a root type. OpenClaw rejects the complete
tools/list response because its validator requires outputSchema.type=object.
The extra type is already implied by both branches; keep the branches intact.
Bridge factory: https://github.com/sparfenyuk/mcp-proxy/blob/v0.13.0/src/mcp_proxy/proxy_server.py
"""
import asyncio
import os

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.server.stdio import stdio_server
from mcp_proxy.proxy_server import create_proxy_server


class CompatibleSession(ClientSession):
    async def list_tools(self, *args, **kwargs):
        result = await super().list_tools(*args, **kwargs)
        for tool in result.tools:
            schema = tool.outputSchema
            if tool.name != "query_sql" or not schema or "type" in schema:
                continue
            branches = schema.get("oneOf", [])
            if branches and all(isinstance(branch, dict) and branch.get("type") == "object" for branch in branches):
                tool.outputSchema = {**schema, "type": "object"}
        return result


async def main():
    headers = {"Authorization": "Bearer " + os.environ["API_ACCESS_TOKEN"]}
    async with httpx.AsyncClient(headers=headers, timeout=httpx.Timeout(30, read=300), trust_env=False) as http:
        async with streamable_http_client("http://127.0.0.1:8097/mcp", http_client=http) as (read, write, _):
            async with CompatibleSession(read, write) as session:
                app = await create_proxy_server(session)
                async with stdio_server() as (incoming, outgoing):
                    await app.run(incoming, outgoing, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
