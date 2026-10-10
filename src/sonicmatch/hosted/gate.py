"""Auth, credit meter, and reverse proxy in front of loopback sonicmatch-mcp."""

from __future__ import annotations

import json
import logging
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from sonicmatch.config import load_settings
from sonicmatch.hosted.ledger import Ledger
from sonicmatch.hosted.page import render_home, render_key, render_message, render_open_source, render_pricing
from sonicmatch.hosted.portal import (
    form_fields,
    load_timeline,
    match_job,
    public_url,
    save_upload,
    search_catalog,
    start_match,
)
from sonicmatch.hosted.pricing import PUBLIC_ORIGIN, TRIAL_CREDITS, credits_for

LOGGER = logging.getLogger("sonicmatch.hosted")

HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
    "authorization",
    "x-api-key",
}


def tool_calls(body: bytes) -> list[tuple[Any, str]]:
    """Return (jsonrpc id, tool name) for tools/call messages. Others are ignored."""
    if not body:
        return []
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return []
    messages = data if isinstance(data, list) else [data]
    found: list[tuple[Any, str]] = []
    for message in messages:
        if not isinstance(message, dict) or message.get("method") != "tools/call":
            continue
        params = message.get("params") if isinstance(message.get("params"), dict) else {}
        name = params.get("name")
        found.append((message.get("id"), name if isinstance(name, str) and name else "unknown"))
    return found


def charge_total(calls: list[tuple[Any, str]]) -> int:
    return sum(credits_for(name) for _, name in calls)


class Gate:
    def __init__(self, ledger: Ledger, upstream: str) -> None:
        self.ledger = ledger
        self.upstream = upstream.rstrip("/")

    def bearer(self, header: str | None) -> str | None:
        if not header:
            return None
        parts = header.split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer" and parts[1].strip():
            return parts[1].strip()
        return None


def make_handler(gate: Gate):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args: object) -> None:
            LOGGER.info("%s - %s", self.address_string(), fmt % args)

        def do_GET(self) -> None:  # noqa: N802
            self._route()

        def do_POST(self) -> None:  # noqa: N802
            self._route()

        def do_DELETE(self) -> None:  # noqa: N802
            self._route()

        def do_OPTIONS(self) -> None:  # noqa: N802
            self._route()

        def _route(self) -> None:
            try:
                self._dispatch()
            except Exception:
                LOGGER.exception("request failed")
                try:
                    self._send(500, "text/plain; charset=utf-8", b"error\n")
                except Exception:
                    return

        def _dispatch(self) -> None:
            path = self.path.split("?", 1)[0]
            pages = {
                "/": render_home,
                "/pricing": render_pricing,
                "/open-source": render_open_source,
            }
            if path in pages and self.command == "GET":
                self._send(200, "text/html; charset=utf-8", pages[path]().encode())
                return
            if path == "/health" and self.command == "GET":
                self._send(
                    200,
                    "application/json",
                    json.dumps({"ok": True, "origin": PUBLIC_ORIGIN}).encode(),
                )
                return
            if path == "/v1/trial" and self.command == "POST":
                self._trial()
                return
            if path == "/v1/me" and self.command == "GET":
                self._me()
                return
            if path == "/samples/sample-clip.mp4" and self.command == "GET":
                self._sample()
                return
            if path == "/api/search" and self.command == "GET":
                self._search()
                return
            if path == "/api/match" and self.command == "POST":
                self._match()
                return
            if path.startswith("/api/match/") and self.command == "GET":
                self._match_status(path.rsplit("/", 1)[-1])
                return
            if path.startswith("/api/timeline/") and self.command == "GET":
                self._timeline(path.rsplit("/", 1)[-1])
                return
            if path == "/api/feedback" and self.command == "POST":
                self._feedback()
                return
            if path == "/mcp" or path.startswith("/mcp/"):
                if self.command == "GET" and self._wants_html():
                    self._redirect("/")
                    return
                self._proxy()
                return
            self._send(404, "text/plain; charset=utf-8", b"not found\n")

        def _wants_html(self) -> bool:
            accept = (self.headers.get("Accept") or "").lower()
            return "text/html" in accept and "text/event-stream" not in accept

        def _redirect(self, location: str) -> None:
            self.send_response(302)
            self.send_header("Location", location)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def _json(self, status: int, payload: dict[str, Any]) -> None:
            self._send(status, "application/json", json.dumps(payload).encode())

        def _timeline(self, asset_id: str) -> None:
            found = load_timeline(asset_id)
            if not found:
                self._json(404, {"ok": False, "error": "That timeline is not on this host."})
                return
            self._json(200, found)

        def _feedback(self) -> None:
            body = self._read_body(limit=20_000)
            if body is None:
                return
            try:
                data = json.loads(body.decode() or "{}")
            except json.JSONDecodeError:
                self._json(400, {"ok": False, "error": "Bad feedback."})
                return
            if not isinstance(data, dict):
                self._json(400, {"ok": False, "error": "Bad feedback."})
                return
            vote = str(data.get("vote") or "")
            if vote not in {"up", "down"}:
                self._json(400, {"ok": False, "error": "Vote up or down."})
                return
            asset = str(data.get("asset_id") or "")[:32]
            index = data.get("section")
            LOGGER.info("timeline feedback asset=%s section=%s vote=%s", asset, index, vote)
            self._json(200, {"ok": True})

        def _sample(self) -> None:
            path = Path(__file__).resolve().parents[3] / "examples" / "sample-clip.mp4"
            if not path.is_file():
                self._send(404, "text/plain; charset=utf-8", b"sample missing\n")
                return
            self._send(200, "video/mp4", path.read_bytes())

        def _search(self) -> None:
            ip = self._client_ip()
            if not gate.ledger.hit_allowed(ip, "search", 40):
                self._json(429, {"ok": False, "error": "Search limit reached. Try again in an hour."})
                return
            query = parse_qs(urlparse(self.path).query).get("q", [""])[0]
            gate.ledger.record_hit(ip, "search")
            try:
                self._json(200, search_catalog(query))
            except Exception:
                LOGGER.exception("catalog search failed")
                self._json(500, {"ok": False, "error": "Search failed."})

        def _match(self) -> None:
            ip = self._client_ip()
            if not gate.ledger.hit_allowed(ip, "match", 8):
                self._json(429, {"ok": False, "error": "Match limit reached. Try again in an hour."})
                return
            body = self._read_body(limit=80_000_000)
            if body is None:
                return
            try:
                fields = form_fields(body, self.headers.get("Content-Type") or "")
                platform = str(fields.get("platform") or "instagram_reel")
                upload = fields.get("file")
                if upload and upload[1]:
                    directory = load_settings().cache_dir / "portal"
                    path = save_upload(upload[0], upload[1], directory)
                    source = str(path)
                else:
                    source = public_url(str(fields.get("url") or ""))
            except ValueError as exc:
                self._json(400, {"ok": False, "error": str(exc)})
                return
            except json.JSONDecodeError:
                self._json(400, {"ok": False, "error": "That request was not valid JSON."})
                return
            gate.ledger.record_hit(ip, "match")
            LOGGER.info("portal match ip=%s platform=%s", ip, platform)
            job_id = start_match(source, platform)
            self._json(202, {"ok": True, "status": "working", "job_id": job_id})

        def _match_status(self, job_id: str) -> None:
            job = match_job(job_id)
            if not job:
                self._json(404, {"ok": False, "error": "That process is gone. Start it again."})
                return
            if job.get("status") != "done":
                self._json(200, {"ok": True, "status": "working"})
                return
            result = job.get("result") if isinstance(job.get("result"), dict) else {}
            status = 200 if result.get("ok") is not False else 400
            if status != 200:
                LOGGER.error("portal match rejected: %s", result.get("error") or result.get("code"))
            self._json(status, result)

        def _client_ip(self) -> str:
            cf = self.headers.get("CF-Connecting-IP")
            if cf:
                return cf.split(",")[0].strip()[:80]
            return self.client_address[0]

        def _read_body(self, limit: int = 8_000_000) -> bytes | None:
            raw = self.headers.get("Content-Length")
            if not raw:
                return b""
            try:
                length = int(raw)
            except ValueError:
                self._send(400, "text/plain; charset=utf-8", b"bad content-length\n")
                return None
            if length < 0 or length > limit:
                self._send(413, "text/plain; charset=utf-8", b"body too large\n")
                return None
            return self.rfile.read(length)

        def _trial(self) -> None:
            ip = self._client_ip()
            if not gate.ledger.trial_allowed(ip):
                page = render_message(
                    "Trial limit",
                    "This network already has trial keys. Self-host the MIT repo, or ask for a paid balance.",
                )
                self._send(429, "text/html; charset=utf-8", page.encode())
                return
            raw = gate.ledger.create_key("trial", TRIAL_CREDITS)
            gate.ledger.record_trial(ip)
            LOGGER.info("trial key issued ip=%s credits=%s", ip, TRIAL_CREDITS)
            self._send(200, "text/html; charset=utf-8", render_key(raw, TRIAL_CREDITS).encode())

        def _me(self) -> None:
            raw = gate.bearer(self.headers.get("Authorization"))
            row = gate.ledger.lookup(raw) if raw else None
            if row is None:
                self._send(401, "application/json", b'{"error":"missing or unknown key"}\n')
                return
            payload = {"label": row["label"], "credits": row["credits"]}
            self._send(200, "application/json", json.dumps(payload).encode())

        def _proxy(self) -> None:
            raw = gate.bearer(self.headers.get("Authorization")) or (
                self.headers.get("X-Api-Key") or ""
            ).strip()
            row = gate.ledger.lookup(raw) if raw else None
            if row is None:
                self._jsonrpc_error(
                    None,
                    401,
                    "Hosted Sonicmatch requires a Bearer key. "
                    f"Open source: run the MIT repo yourself. Keys: {PUBLIC_ORIGIN}",
                )
                return
            body = self._read_body()
            if body is None:
                return
            calls = tool_calls(body) if self.command == "POST" else []
            cost = charge_total(calls)
            if cost and not gate.ledger.debit(row["id"], "+".join(n for _, n in calls), cost):
                balance = gate.ledger.balance(row["id"])
                self._jsonrpc_error(
                    calls[0][0] if calls else None,
                    402,
                    f"Out of credits ({balance} left, {cost} required). "
                    f"Prices: {PUBLIC_ORIGIN}/#pricing",
                )
                return
            if calls and cost == 0:
                gate.ledger.debit(row["id"], calls[0][1], 0)
            try:
                status, resp_headers, resp_body = self._forward(body)
            except HTTPError as exc:
                status = exc.code
                resp_headers = list(exc.headers.items())
                resp_body = exc.read()
            except (URLError, TimeoutError, OSError) as exc:
                if cost:
                    gate.ledger.credit(row["id"], cost, "refund")
                LOGGER.error("upstream failed: %s", exc)
                self._jsonrpc_error(calls[0][0] if calls else None, 502, "Sonicmatch upstream is down")
                return
            if status >= 500 and cost:
                gate.ledger.credit(row["id"], cost, "refund")
            self.send_response(status)
            for key, value in resp_headers:
                if key.lower() in HOP or key.lower() == "content-length":
                    continue
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(resp_body)))
            self.end_headers()
            self.wfile.write(resp_body)

        def _forward(self, body: bytes) -> tuple[int, list[tuple[str, str]], bytes]:
            headers = {}
            for key, value in self.headers.items():
                if key.lower() in HOP:
                    continue
                headers[key] = value
            req = Request(
                gate.upstream + self.path,
                data=body if self.command in {"POST", "PUT", "PATCH"} else None,
                headers=headers,
                method=self.command,
            )
            with urlopen(req, timeout=300) as resp:
                return resp.status, list(resp.headers.items()), resp.read()

        def _jsonrpc_error(self, rpc_id: Any, http_status: int, message: str) -> None:
            payload = {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {"code": -32000 - (http_status % 100), "message": message},
            }
            self._send(http_status, "application/json", json.dumps(payload).encode())

        def _send(self, status: int, content_type: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    return Handler


def serve(gate: Gate, host: str, port: int) -> None:
    httpd = ThreadingHTTPServer((host, port), make_handler(gate))
    LOGGER.info("sonicmatch hosted gate on http://%s:%s", host, port)
    httpd.serve_forever()


def configure_logging(path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    handler = logging.FileHandler(path)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger("sonicmatch")
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    # Keep the library from also writing these lines to a browser console.
    root.propagate = False
