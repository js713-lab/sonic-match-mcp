"""SSRF guard for URL ingest. Reject file://, loopback, and private IPs."""

from __future__ import annotations

import ipaddress
import socket
from pathlib import Path
from urllib.parse import urlparse

import httpx

from sonicmatch.errors import SonicError

ALLOWED_HOST_SUFFIXES = (
    "youtube.com",
    "youtu.be",
    "tiktok.com",
    "instagram.com",
    "cdninstagram.com",
    "facebook.com",
    "fb.com",
    "fb.watch",
    "fbcdn.net",
)

VIDEO_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".webm",
    ".mkv",
    ".m4v",
    ".avi",
    ".mpeg",
    ".mpg",
    ".3gp",
}

VIDEO_CONTENT_TYPES = (
    "video/",
    "application/octet-stream",
    "application/mp4",
    "application/x-mpegurl",
    "application/vnd.apple.mpegurl",
)


def _host_allowed_platform(host: str) -> bool:
    h = host.lower().rstrip(".")
    if h.startswith("www."):
        h = h[4:]
    for suffix in ALLOWED_HOST_SUFFIXES:
        if h == suffix or h.endswith("." + suffix):
            return True
    return False


def _is_blocked_ip(ip: ipaddress._BaseAddress) -> bool:
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or (getattr(ip, "is_site_local", False))
    )


def resolve_and_check_host(host: str) -> list[str]:
    """Resolve host and reject if any address is private/loopback."""
    if not host:
        raise SonicError("SSRF_REJECTED", "URL host is empty.")
    lowered = host.lower().strip("[]")
    try:
        ip = ipaddress.ip_address(lowered)
        if _is_blocked_ip(ip):
            raise SonicError(
                "SSRF_REJECTED",
                f"Refusing to fetch private or loopback address: {host}",
            )
        return [str(ip)]
    except ValueError:
        pass

    blocked_names = {
        "localhost",
        "localhost.localdomain",
        "ip6-localhost",
        "ip6-loopback",
        "metadata.google.internal",
    }
    if lowered in blocked_names or lowered.endswith(".localhost"):
        raise SonicError("SSRF_REJECTED", f"Refusing to fetch host: {host}")

    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise SonicError("BAD_URL", f"Could not resolve host {host}: {exc}") from exc

    ips: list[str] = []
    for info in infos:
        addr = info[4][0]
        ip = ipaddress.ip_address(addr)
        if _is_blocked_ip(ip):
            raise SonicError(
                "SSRF_REJECTED",
                f"Host {host} resolves to a private or loopback address ({addr}).",
            )
        ips.append(addr)
    if not ips:
        raise SonicError("BAD_URL", f"No addresses for host {host}")
    return ips


def parse_source_url(source: str) -> tuple[str, str, str]:
    """Return (scheme, host, path). Raises SonicError if clearly unsafe."""
    raw = source.strip()
    if not raw:
        raise SonicError("BAD_URL", "Empty source.")
    lowered = raw.lower()
    if lowered.startswith("file:"):
        raise SonicError("SSRF_REJECTED", "file:// URLs are not allowed.")
    if lowered.startswith(("javascript:", "data:", "ftp:", "sftp:", "smb:")):
        raise SonicError("SSRF_REJECTED", f"Scheme not allowed: {raw.split(':', 1)[0]}")

    parsed = urlparse(raw)
    if parsed.scheme != "https":
        raise SonicError(
            "SSRF_REJECTED",
            "Remote ingest is HTTPS-only. Use a local file path, or an https URL.",
        )
    host = parsed.hostname or ""
    if not host:
        raise SonicError("BAD_URL", "URL is missing a host.")
    if parsed.username or parsed.password:
        raise SonicError("SSRF_REJECTED", "URLs with credentials are not allowed.")
    resolve_and_check_host(host)
    return parsed.scheme, host, parsed.path or "/"


def classify_url(source: str) -> str:
    """
    Return 'platform' for yt-dlp hosts, 'direct' for likely raw video URLs.
    """
    _, host, path = parse_source_url(source)
    if _host_allowed_platform(host):
        return "platform"
    ext = ""
    if "." in path.rsplit("/", 1)[-1]:
        ext = "." + path.rsplit(".", 1)[-1].lower()
    if ext in VIDEO_EXTENSIONS:
        return "direct"
    return "direct"


def content_type_looks_like_video(content_type: str | None) -> bool:
    if not content_type:
        return False
    ct = content_type.split(";", 1)[0].strip().lower()
    return any(ct.startswith(prefix) or ct == prefix.rstrip("/") for prefix in VIDEO_CONTENT_TYPES)


def join_https_redirect(current: str, location: str) -> str:
    """Join a Location header and re-run the SSRF checks on the next hop."""
    nxt = str(httpx.URL(current).join(location))
    parse_source_url(nxt)
    return nxt


def fetch_https_capped(
    url: str,
    dest: Path,
    *,
    max_bytes: int,
    user_agent: str = "sonicmatch-mcp/0.2",
    timeout: httpx.Timeout | None = None,
) -> Path:
    """GET an HTTPS URL to disk. Re-check every redirect hop. Cap size.

    Does not follow redirects automatically — each Location is parsed and
    resolved so a public URL cannot bounce into loopback/private space.
    """
    parse_source_url(url)
    dest.parent.mkdir(parents=True, exist_ok=True)
    t = timeout or httpx.Timeout(30.0, read=120.0)
    with httpx.Client(timeout=t, follow_redirects=False) as client:
        current = url
        for _ in range(5):
            _, host, _ = parse_source_url(current)
            resolve_and_check_host(host)
            with client.stream(
                "GET", current, headers={"User-Agent": user_agent}
            ) as resp:
                if resp.status_code in {301, 302, 303, 307, 308}:
                    nxt = resp.headers.get("location")
                    if not nxt:
                        raise SonicError("DOWNLOAD_FAILED", "Redirect missing Location.")
                    current = join_https_redirect(current, nxt)
                    continue
                if resp.status_code >= 400:
                    raise SonicError(
                        "DOWNLOAD_FAILED",
                        f"HTTP {resp.status_code} fetching {current}.",
                    )
                cl = resp.headers.get("content-length")
                if cl and int(cl) > max_bytes:
                    raise SonicError(
                        "TOO_LARGE",
                        f"Remote file is {int(cl)} bytes; max is {max_bytes} bytes.",
                    )
                written = 0
                with dest.open("wb") as fh:
                    for chunk in resp.iter_bytes(1024 * 64):
                        written += len(chunk)
                        if written > max_bytes:
                            fh.close()
                            dest.unlink(missing_ok=True)
                            raise SonicError(
                                "TOO_LARGE",
                                f"Download exceeded {max_bytes} bytes.",
                            )
                        fh.write(chunk)
                return dest
        raise SonicError("DOWNLOAD_FAILED", "Too many redirects.")
