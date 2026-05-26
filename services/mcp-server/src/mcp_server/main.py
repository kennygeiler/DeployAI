"""FastAPI entrypoint — Model Context Protocol inbound server (v2 Phase 4).

The MCP wire protocol is JSON-RPC 2.0 over HTTP. We expose:

- ``POST /mcp``       — single JSON-RPC endpoint for ``initialize``,
                        ``tools/list``, ``tools/call``, ``resources/list``,
                        ``resources/read``.
- ``GET  /health``    — uvicorn / compose healthcheck (no auth).

Every JSON-RPC request needs ``Authorization: Bearer mcp_live_<hex>``. The
bearer maps to one ``tenant_api_keys`` row; the row's engagement scope is
enforced for every resource + tool call.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from mcp_server.auth import MCPPrincipal, require_principal
from mcp_server.db import get_session
from mcp_server.resources import (
    UnknownResourceError,
    list_resource_templates,
    read_resource,
)
from mcp_server.tools import call_tool, list_mcp_tools

_log = logging.getLogger(__name__)

PROTOCOL_VERSION = "2025-06-18"
SERVER_NAME = "deployai-mcp"
SERVER_VERSION = "0.1.0"


@asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield


app = FastAPI(
    title="DeployAI MCP server",
    version=SERVER_VERSION,
    lifespan=_lifespan,
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "mcp-server", "version": SERVER_VERSION}


class JsonRpcRequest(BaseModel):
    jsonrpc: str
    id: int | str | None = None
    method: str
    params: dict[str, Any] | None = None


def _rpc_error(req_id: int | str | None, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def _rpc_result(req_id: int | str | None, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


async def _dispatch(
    session: AsyncSession,
    principal: MCPPrincipal,
    req: JsonRpcRequest,
) -> dict[str, Any]:
    method = req.method
    params = req.params or {}
    if method == "initialize":
        return _rpc_result(
            req.id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                "capabilities": {
                    "tools": {"listChanged": False},
                    "resources": {"listChanged": False, "subscribe": False},
                },
            },
        )
    if method == "tools/list":
        return _rpc_result(req.id, {"tools": list_mcp_tools()})
    if method == "tools/call":
        name = params.get("name")
        if not isinstance(name, str):
            return _rpc_error(req.id, -32602, "tools/call requires 'name'")
        arguments = params.get("arguments")
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            return _rpc_error(req.id, -32602, "tools/call 'arguments' must be an object")
        result = await call_tool(session, principal, name=name, arguments=arguments)
        # MCP CallToolResult wraps content blocks; we return a single text block
        # carrying the serialized tool result so clients can parse the rows.
        import json

        return _rpc_result(
            req.id,
            {
                "content": [
                    {"type": "text", "text": json.dumps(result, default=str)},
                ],
                "isError": False,
            },
        )
    if method == "resources/list":
        return _rpc_result(req.id, {"resourceTemplates": list_resource_templates(), "resources": []})
    if method == "resources/read":
        uri = params.get("uri")
        if not isinstance(uri, str) or not uri:
            return _rpc_error(req.id, -32602, "resources/read requires 'uri'")
        try:
            content = await read_resource(session, principal, uri)
        except UnknownResourceError as exc:
            return _rpc_error(req.id, -32601, str(exc))
        return _rpc_result(
            req.id,
            {
                "contents": [{"uri": content.uri, "mimeType": content.mime_type, "text": content.text}],
            },
        )
    if method == "ping":
        return _rpc_result(req.id, {})
    return _rpc_error(req.id, -32601, f"method not found: {method!r}")


@app.post("/mcp")
async def mcp_endpoint(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[MCPPrincipal, Depends(require_principal)],
    authorization: str | None = Header(default=None),
) -> JSONResponse:
    _ = authorization  # consumed by require_principal — declared so OpenAPI carries the auth header
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid JSON body") from exc
    try:
        req = JsonRpcRequest.model_validate(body)
    except Exception:
        return JSONResponse(_rpc_error(None, -32600, "invalid JSON-RPC envelope"))
    if req.jsonrpc != "2.0":
        return JSONResponse(_rpc_error(req.id, -32600, "only jsonrpc 2.0 is supported"))
    try:
        payload = await _dispatch(session, principal, req)
    except HTTPException:
        raise
    except Exception as exc:
        _log.exception("mcp dispatch error")
        return JSONResponse(_rpc_error(req.id, -32603, f"internal error: {exc!s}"[:240]))
    return JSONResponse(payload)


__all__ = ["app"]
