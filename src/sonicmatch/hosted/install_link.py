"""Cursor one-click install link for the hosted MCP."""

from __future__ import annotations

import base64
import json
from urllib.parse import quote

from sonicmatch.hosted.pricing import PUBLIC_ORIGIN

# Same shape as an mcp.json server entry. The key stays in the user's env.
INSTALL_CONFIG: dict[str, object] = {
    "url": f"{PUBLIC_ORIGIN}/mcp",
    "headers": {"Authorization": "Bearer ${env:SONICMATCH_API_KEY}"},
}


def config_b64() -> str:
    raw = json.dumps(INSTALL_CONFIG, separators=(",", ":")).encode()
    return base64.b64encode(raw).decode()


def cursor_install_link() -> str:
    return (
        "cursor://anysphere.cursor-deeplink/mcp/install"
        f"?name=sonicmatch&config={quote(config_b64(), safe='')}"
    )
