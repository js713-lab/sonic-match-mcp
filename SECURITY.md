# Security policy

## Credentials this project uses

- **GEMINI_API_KEY**, **JAMENDO_CLIENT_ID**, **FREESOUND_API_KEY** — optional, from the environment or a gitignored `.env`. `status` reports whether they are set, never the values.
- **User-owned library JSON** — may contain local paths to audio you already licensed. Do not commit a filled-in file; use `examples/user_library.example.json` as the shape only.

Copy `.env.example` locally. Never commit a filled-in `.env`, never paste keys into issues.

## Reporting a vulnerability

Do not open a public issue for credential leaks, SSRF, or unauthenticated HTTP exposure.

1. Use GitHub's private vulnerability reporting on this repository if it is enabled, or
2. Open a draft security advisory.

Include reproduction steps and affected versions. Redact API keys.

## Scope

**In scope:** SSRF on URL ingest/mix downloads, path handling for `asset_id`, secret handling, MCP tool output, and the unauthenticated HTTP transport.

**Out of scope:** Gemini / Jamendo / Freesound themselves, ffmpeg bugs, and a compromised local machine.

## Runtime notes

- Default transport is **stdio**. That is the right mode for Claude Desktop, Cursor, and Grok.
- `--http` has **no authentication**. Default bind is `127.0.0.1`. The Docker image binds `0.0.0.0` so the container port can be published — do not map that port to the public internet. Anyone who can reach the HTTP port can ingest local files the process can read and run mixes.
- Remote ingest is HTTPS-only. `file://`, loopback, private IPs, and URLs with credentials are rejected. Redirect hops are re-checked. Size is capped by `SONICMATCH_MAX_DOWNLOAD_MB` (default 200).
- yt-dlp platform ingest is **off** unless `SONICMATCH_ALLOW_YTDLP=1`.
- Tools return paths and `asset_id`s, never raw video bytes.
- Generated beds require `i_understand_not_commercially_cleared=true` and are excluded from auto recommendations.
