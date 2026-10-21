# Contributing to sonicmatch-mcp

Thanks for looking. The useful work is catalog quality, license honesty, and editor-shaped output (hook in/out, ducking, an ffmpeg command). A new tool that wraps another search box is not the goal.

By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).

## Setup

Python 3.10 or newer, plus `ffmpeg` and `ffprobe` on `PATH`. Tests render tiny color clips with ffmpeg.

```bash
git clone https://github.com/js713-lab/sonic-match-mcp.git
cd sonic-match-mcp
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # optional; leave keys empty
```

```bash
pytest
ruff check src tests
```

`pytest` is the test suite. `ruff check` is the lint CI runs. Both should pass before you open a pull request.

Do not commit `.env`, API keys, or a filled-in user library. `examples/user_library.example.json` is the shape only.

## Pull requests

- One change per pull request when you can.
- Describe what changed and how you ran tests.
- Add or update a test when you change ranking, ingest, licenses, or the CLI.
- User-facing changes get a line in [CHANGELOG.md](CHANGELOG.md) under `Unreleased` (or the version you are cutting).
- Do not bump `server.json` / `manifest.json` unless you are also shipping a new MCPB. Those versions track the registry bundle, not every Python commit. See [PUBLISH.md](PUBLISH.md).

The Python package version lives in both `pyproject.toml` (`project.version`) and `src/sonicmatch/__init__.py` (`__version__`). CI checks that they match. Maintainers cut a PyPI release by tagging `v` plus that version. Contributors do not need to tag.

## Good first issues

Scoped starters are written out in [docs/good-first-issues.md](docs/good-first-issues.md). Comment on one before you start if it is already open, so two people do not take the same patch.

## Security

Do not file public issues for credential leaks, SSRF, or the unauthenticated HTTP transport. Use [SECURITY.md](SECURITY.md).
