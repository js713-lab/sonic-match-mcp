"""Structured tool errors — never leak stack traces to the MCP client."""

from __future__ import annotations

from typing import Any


class SonicError(Exception):
    """Recoverable tool failure with a stable error code."""

    def __init__(self, code: str, message: str, **extra: Any) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.extra = extra

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": False,
            "code": self.code,
            "error": self.message,
        }
        payload.update(self.extra)
        return payload


def ok(**payload: Any) -> dict[str, Any]:
    return {"ok": True, **payload}


def fail(code: str, message: str, **extra: Any) -> dict[str, Any]:
    return SonicError(code, message, **extra).to_dict()
