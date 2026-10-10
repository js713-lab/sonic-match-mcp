"""Run loopback sonicmatch-mcp and the public credit gate."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from sonicmatch.hosted.gate import Gate, configure_logging, serve
from sonicmatch.hosted.ledger import Ledger

REPO = Path(__file__).resolve().parents[3]


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    return int(raw) if raw else default


def main() -> None:
    log_path = os.environ.get("SONICMATCH_ERROR_LOG", str(REPO / "error.logs"))
    configure_logging(log_path)
    host = os.environ.get("SONICMATCH_GATE_HOST", "127.0.0.1")
    gate_port = _env_int("SONICMATCH_GATE_PORT", 8775)
    upstream_port = _env_int("SONICMATCH_UPSTREAM_PORT", 8776)
    db_path = Path(
        os.environ.get("SONICMATCH_HOSTED_DB", str(REPO / "hosted" / "data" / "ledger.sqlite"))
    )
    ledger = Ledger(db_path)
    operator_path = db_path.parent / "operator.key"
    if not operator_path.exists():
        credits = _env_int("SONICMATCH_OPERATOR_CREDITS", 2000)
        raw = ledger.create_key("operator", credits)
        operator_path.write_text(raw + "\n", encoding="utf-8")
        operator_path.chmod(0o600)

    src = str(REPO / "src")
    env = os.environ.copy()
    env["PYTHONPATH"] = src + os.pathsep + env.get("PYTHONPATH", "")
    upstream = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "sonicmatch",
            "--http",
            "--host",
            "127.0.0.1",
            "--port",
            str(upstream_port),
        ],
        cwd=str(REPO),
        env=env,
    )
    deadline = time.time() + 20
    while time.time() < deadline:
        if upstream.poll() is not None:
            raise SystemExit(f"sonicmatch-mcp exited {upstream.returncode}")
        try:
            import socket

            with socket.create_connection(("127.0.0.1", upstream_port), timeout=0.3):
                break
        except OSError:
            time.sleep(0.2)
    else:
        upstream.terminate()
        raise SystemExit("sonicmatch-mcp did not listen")

    try:
        serve(Gate(ledger, f"http://127.0.0.1:{upstream_port}"), host, gate_port)
    finally:
        upstream.terminate()
        try:
            upstream.wait(timeout=5)
        except subprocess.TimeoutExpired:
            upstream.kill()


if __name__ == "__main__":
    main()
