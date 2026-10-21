# Publishing sonicmatch-mcp

PyPI and the MCP Registry are separate. The Python package is `sonicmatch-mcp`. The registry server is `io.github.js713-lab/sonicmatch-mcp`.

Keep this comment in `README.md`:

```html
<!-- mcp-name: io.github.js713-lab/sonicmatch-mcp -->
```

## One-time: PyPI Trusted Publishing

Nothing in this repo is a PyPI token. `.github/workflows/release.yml` asks GitHub for a short-lived OIDC identity and `pypa/gh-action-pypi-publish` exchanges that for an upload. Do not create a PyPI API token, and do not add `PYPI_API_TOKEN` (or any publish password) to GitHub Actions secrets.

As of 2026-10-21, `https://pypi.org/pypi/sonicmatch-mcp/json` returned 404. The name was free. A **pending publisher does not reserve the name** until the first successful upload. If someone else registers `sonicmatch-mcp` first, the pending publisher is invalidated and this package needs a new name.

1. Log in at [pypi.org](https://pypi.org/) and turn on two-factor authentication.
2. Open [Account → Publishing](https://pypi.org/manage/account/publishing/).
3. Under **Add a new pending publisher**, choose GitHub and enter these values exactly:

   | Field | Value |
   |---|---|
   | PyPI project name | `sonicmatch-mcp` |
   | Owner | `js713-lab` |
   | Repository name | `sonic-match-mcp` |
   | Workflow name | `release.yml` |
   | Environment name | `pypi` |

4. On GitHub, open [Settings → Environments](https://github.com/js713-lab/sonic-match-mcp/settings/environments) for this repository.
5. Create an environment named `pypi`. The name is case-sensitive and must match the PyPI form. Add no secrets.
6. PyPI's guide asks you to require a reviewer on that environment. Add yourself as a required reviewer if you want a tag push to wait for your approval before the upload. Leave reviewers off if a green tag should upload on its own.

The publish job is the only job with `id-token: write`. The workflow file name on PyPI must stay `release.yml`. If you rename the file or the environment, update the pending publisher to match or the upload fails with an OIDC mismatch.

## Cut the first PyPI release

Tag `v0.2.0` already exists and points at the MCPB GitHub release. Pushing it again does nothing, and the new workflow was not on that commit. The Python package version to publish is **0.2.1** (`pyproject.toml` and `src/sonicmatch/__init__.py`). `server.json` and `manifest.json` stay at **0.2.0** until you build a new MCPB.

After the packaging pull request is on `main`:

1. Check the two Python version strings are both `0.2.1`.
2. Optional: replace `Unreleased` on the `0.2.1` heading in `CHANGELOG.md` with the date you tag, and commit that on `main`.
3. Tag and push:

   ```bash
   git checkout main
   git pull origin main
   git tag v0.2.1
   git push origin v0.2.1
   ```

   The tag must be `v` plus the exact version. `v0.2.1` publishes `0.2.1`. Any other tag fails the version check in `release.yml` and does not upload.

4. Open Actions → **Publish to PyPI**. If the `pypi` environment has required reviewers, approve the `publish` job.
5. Confirm [pypi.org/project/sonicmatch-mcp](https://pypi.org/project/sonicmatch-mcp/) shows `0.2.1`. The README PyPI badge updates from that page.
6. Smoke test:

   ```bash
   uvx sonicmatch-mcp --version
   pipx install sonicmatch-mcp
   sonicmatch-mcp --version
   ```

   Both should print `0.2.1`.

The pending publisher becomes a normal trusted publisher the first time it succeeds. Later releases are the same steps: bump both Python version strings, update `CHANGELOG.md`, tag `vX.Y.Z`, push the tag.

## MCP Registry

The live listing is `io.github.js713-lab/sonicmatch-mcp` at version `0.2.0` (MCPB on the `v0.2.0` GitHub release). Publishing to PyPI does not update that listing.

To publish a new registry version:

1. Bump `version` in `manifest.json` and `server.json` to the same value.
2. Pack and hash:

   ```bash
   npx -y @anthropic-ai/mcpb pack
   sha256sum sonicmatch-mcp.mcpb
   ```

3. Put the SHA-256 in `server.json` `packages[0].fileSha256`, and set `identifier` to the GitHub release asset URL for that tag.
4. Commit, tag `vX.Y.Z`, and attach `sonicmatch-mcp-X.Y.Z.mcpb` to the GitHub release. The asset URL has to match `identifier`.
5. Actions → **Publish to MCP Registry** → Run workflow → enter the tag, for example `v0.2.0`.

The workflow checks out that tag. It refuses to publish unless `server.json` and `manifest.json` match the tag (without the `v`) and the package identifier contains `/<tag>/`. It does not rewrite `server.json`, and it does not upload to PyPI.

Registry versions are immutable. A metadata fix is a new version and a new tag.

## Open the starter issues

Create GitHub labels `good first issue` and `help wanted` if they are missing (Settings → Labels, or the label field on a new issue).

Open one issue per section in [docs/good-first-issues.md](docs/good-first-issues.md). Use the heading as the title, paste the body, and apply both labels. Leave API keys out of the issues.
