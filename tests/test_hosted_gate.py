from __future__ import annotations

import base64
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from sonicmatch.hosted.gate import Gate, charge_total, make_handler, tool_calls
from sonicmatch.hosted.install_link import INSTALL_CONFIG, config_b64, cursor_install_link
from sonicmatch.hosted.ledger import Ledger
from sonicmatch.hosted.page import render_home, render_open_source, render_pricing
from sonicmatch.hosted.portal import form_fields, public_url, search_catalog
from sonicmatch.hosted.pricing import GITHUB_REPO, TRIAL_CREDITS, credits_for


def test_public_url_upgrades_http():
    assert public_url("http://youtube.com/watch?v=U1GjF4CLgh8") == "https://youtube.com/watch?v=U1GjF4CLgh8"


def test_install_link_points_at_hosted_mcp():
    decoded = json.loads(base64.b64decode(config_b64()))
    assert decoded == INSTALL_CONFIG
    assert decoded["url"] == "https://sonic.codecrafter.dev/mcp"
    assert "SONICMATCH_API_KEY" in decoded["headers"]["Authorization"]
    assert cursor_install_link().startswith("cursor://anysphere.cursor-deeplink/mcp/install?name=sonicmatch&config=")


def test_home_page_lists_open_source_and_prices():
    page = render_home()
    assert ">Home</a>" in page
    assert ">Open source</a>" in page
    assert ">Pricing</a>" in page
    assert ">Search</a>" not in page
    assert ">Agents</a>" not in page
    assert 'id="match-form"' in page
    assert 'name="file"' in page
    assert 'id="thumb"' in page
    assert 'id="use-sample"' in page
    assert ">Process</button>" in page
    assert "Search the catalog" not in page
    assert 'name="platform"' not in page
    assert "console." not in page
    assert "lattice-loader" in page
    assert 'rel="icon"' in page
    opened = render_open_source()
    assert GITHUB_REPO in opened
    assert "MIT" in opened
    priced = render_pricing()
    assert "500 credits" in priced
    assert "$9" in priced
    assert "$39" in priced


def test_tool_call_parser_ignores_list_and_charges_recommend():
    body = json.dumps(
        {"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": "recommend_bgm"}}
    ).encode()
    calls = tool_calls(body)
    assert calls == [(7, "recommend_bgm")]
    assert charge_total(calls) == credits_for("recommend_bgm")
    assert tool_calls(json.dumps({"method": "tools/list"}).encode()) == []


def test_ledger_rejects_overdraft(tmp_path: Path):
    ledger = Ledger(tmp_path / "ledger.sqlite")
    raw = ledger.create_key("t", 3)
    row = ledger.lookup(raw)
    assert row is not None
    assert ledger.debit(row["id"], "recommend_bgm", 4) is False
    assert ledger.balance(row["id"]) == 3
    assert ledger.debit(row["id"], "ingest_video", 2) is True
    assert ledger.balance(row["id"]) == 1


class _Upstream(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: object) -> None:
        return

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        # The user key must not reach the open MCP process.
        assert "authorization" not in {k.lower() for k in self.headers}
        body = b'{"jsonrpc":"2.0","id":1,"result":{"ok":true}}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _serve(handler, host: str = "127.0.0.1") -> tuple[ThreadingHTTPServer, int]:
    httpd = ThreadingHTTPServer((host, 0), handler)
    Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def test_gate_charges_and_blocks(tmp_path: Path):
    upstream, up_port = _serve(_Upstream)
    ledger = Ledger(tmp_path / "ledger.sqlite")
    raw = ledger.create_key("trial", TRIAL_CREDITS)
    gate_httpd, gate_port = _serve(make_handler(Gate(ledger, f"http://127.0.0.1:{up_port}")))
    try:
        home = urlopen(f"http://127.0.0.1:{gate_port}/").read().decode()
        assert "Process" in home

        denied = Request(
            f"http://127.0.0.1:{gate_port}/mcp",
            data=b'{"jsonrpc":"2.0","id":1,"method":"tools/list"}',
            method="POST",
        )
        try:
            urlopen(denied)
            raise AssertionError("expected 401")
        except HTTPError as exc:
            assert exc.code == 401

        call = json.dumps(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "recommend_bgm"}}
        ).encode()
        ok = urlopen(
            Request(
                f"http://127.0.0.1:{gate_port}/mcp",
                data=call,
                headers={"Authorization": f"Bearer {raw}"},
                method="POST",
            )
        )
        assert ok.status == 200
        assert ledger.balance(ledger.lookup(raw)["id"]) == TRIAL_CREDITS - credits_for("recommend_bgm")

        poor = ledger.create_key("empty", 0)
        try:
            urlopen(
                Request(
                    f"http://127.0.0.1:{gate_port}/mcp",
                    data=call,
                    headers={"Authorization": f"Bearer {poor}"},
                    method="POST",
                )
            )
            raise AssertionError("expected 402")
        except HTTPError as exc:
            assert exc.code == 402
            assert ledger.balance(ledger.lookup(poor)["id"]) == 0
    finally:
        gate_httpd.shutdown()
        upstream.shutdown()


def test_browser_mcp_path_opens_the_portal(tmp_path: Path):
    ledger = Ledger(tmp_path / "ledger.sqlite")
    gate_httpd, gate_port = _serve(make_handler(Gate(ledger, "http://127.0.0.1:9")))
    try:
        page = urlopen(
            Request(
                f"http://127.0.0.1:{gate_port}/mcp",
                headers={"Accept": "text/html"},
                method="GET",
            )
        ).read().decode()
        assert "Open source" in page
        assert "Process" in page
    finally:
        gate_httpd.shutdown()


def test_catalog_search_returns_tracks():
    found = search_catalog("cafe", limit=5)
    assert found["ok"] is True
    assert found["tracks"]
    assert "embed" not in found["tracks"][0]


def test_multipart_file_field():
    body = (
        b"--bound\r\n"
        b'Content-Disposition: form-data; name="platform"\r\n\r\n'
        b"tiktok\r\n"
        b"--bound\r\n"
        b'Content-Disposition: form-data; name="file"; filename="clip.mp4"\r\n'
        b"Content-Type: video/mp4\r\n\r\n"
        b"fake-bytes\r\n"
        b"--bound--\r\n"
    )
    fields = form_fields(body, 'multipart/form-data; boundary=bound')
    assert fields["platform"] == "tiktok"
    assert fields["file"][0] == "clip.mp4"
    assert fields["file"][1] == b"fake-bytes"
