# Changelog

All notable changes to the Python package are documented here. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the package version follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The MCP Registry bundle (`server.json`, `manifest.json`, the `.mcpb` on the GitHub release) is still **0.2.0**. It moves only when a new bundle is published. See [PUBLISH.md](PUBLISH.md).

## [0.2.1] - Unreleased

### Fixed

- `CC-BY` and `CC-BY-SA` tracks were dropped from `recommend_bgm`. The license gate normalized hyphens to spaces and then looked for the hyphenated token, so 13 of 22 seed rows never ranked. Non-commercial tracks are still excluded.

### Added

- PyPI metadata and the `sonicmatch-mcp` console script (`uvx` / `pipx` / `python -m sonicmatch`).
- Tag-triggered PyPI Trusted Publishing workflow (`.github/workflows/release.yml`). No API token is stored in the repo. The maintainer still has to create the pending publisher and push the first tag.
- CI lint (`ruff check`) and a `python -m build` / `twine check --strict` job, plus tests for the license gate, the CLI, and version alignment.
- Contributor docs: `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, issue templates, pull request template, and `docs/good-first-issues.md`.
- README install paths for Claude Desktop, Cursor, and Codex, including the PyPI form that works after the first release.

## [0.2.0] - 2026-09-10

Initial public release. stdio and streamable HTTP MCP server, seed catalog, optional Jamendo / Freesound / user-owned library adapters, ffmpeg mix spec, and the MCPB listing `io.github.js713-lab/sonicmatch-mcp`.

[0.2.1]: https://github.com/js713-lab/sonic-match-mcp/compare/v0.2.0...main
[0.2.0]: https://github.com/js713-lab/sonic-match-mcp/releases/tag/v0.2.0
