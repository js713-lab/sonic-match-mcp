## Summary

<!-- What changed and why. One or two sentences is enough. -->

## How to test

- [ ] `pytest`
- [ ] `ruff check src tests`

<!-- Note any extra command you ran (ffmpeg fixture, `python -m build`, a manual MCP call). -->

## Checklist

- [ ] Tests cover the behavior I changed, or this change has no runtime behavior.
- [ ] `CHANGELOG.md` has a line under the current unreleased version, or this is docs-only and I left it out on purpose.
- [ ] No API keys, `.env` files, or filled-in user libraries.
- [ ] I did not retag `server.json` / `manifest.json` unless this pull request also ships a new MCPB.
