"""
Transparent GitHub API proxy.

All requests to /github/{path} are forwarded to https://api.github.com/{path}
with the server-side GITHUB_TOKEN added. This removes the need for the
front-end to hold a GitHub token.
"""

import httpx
from fastapi import APIRouter, Request, Response

from config import GITHUB_TOKEN

router = APIRouter()

_GITHUB_API = "https://api.github.com"
_TIMEOUT = 30.0

# Headers that must not be forwarded from the client to GitHub
_HOP_BY_HOP = frozenset(
    [
        "host",
        "connection",
        "transfer-encoding",
        "te",
        "trailer",
        "upgrade",
        "proxy-authorization",
        "proxy-authenticate",
    ]
)


@router.api_route(
    "/github/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
)
async def github_proxy(path: str, request: Request) -> Response:
    """Forward requests to the GitHub API, injecting the server-side token."""
    url = f"{_GITHUB_API}/{path}"

    # Build forwarded headers — strip hop-by-hop and override auth
    forward_headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower() not in _HOP_BY_HOP
    }
    forward_headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    forward_headers.setdefault("Accept", "application/vnd.github+json")
    forward_headers.setdefault("X-GitHub-Api-Version", "2022-11-28")

    body = await request.body()

    async with httpx.AsyncClient() as client:
        resp = await client.request(
            method=request.method,
            url=url,
            headers=forward_headers,
            params=dict(request.query_params),
            content=body or None,
            timeout=_TIMEOUT,
        )

    return Response(
        content=resp.content,
        status_code=resp.status_code,
        media_type=resp.headers.get("content-type", "application/json"),
    )
