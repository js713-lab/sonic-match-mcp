# Publish sonicmatch-mcp

The official MCP Registry listing for `io.github.js713-lab/sonicmatch-mcp` is an **MCPB** on the GitHub release. PyPI is optional and separate.

Keep this comment in `README.md` if you later add a PyPI package:

```html
<!-- mcp-name: io.github.js713-lab/sonicmatch-mcp -->
```

## Current release path (MCPB)

1. Bump `version` in `pyproject.toml`, `manifest.json`, and `server.json`.
2. Pack and hash:

```bash
npx -y @anthropic-ai/mcpb pack
sha256sum sonicmatch-mcp.mcpb
```

3. Put the SHA-256 into `server.json` `packages[0].fileSha256` and the release URL into `identifier`.
4. Commit, tag `v0.2.0`, attach `sonicmatch-mcp-0.2.0.mcpb` to the GitHub release.
5. `mcp-publisher login github && mcp-publisher publish`

Registry versions are immutable. A metadata fix is a new version + a new tag.

## Optional later: PyPI

Create a [pending trusted publisher](https://pypi.org/manage/account/publishing/) for project `sonicmatch-mcp`, owner `js713-lab`, repository `sonic-match-mcp`, workflow `publish-mcp.yml`. Then run the workflow from the Actions tab.
