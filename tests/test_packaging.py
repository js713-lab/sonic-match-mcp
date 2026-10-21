"""Packaging invariants that CI and the PyPI release workflow both rely on."""

from __future__ import annotations

import filecmp
import json
import tomllib
from pathlib import Path

import pytest

from sonicmatch import __version__
from sonicmatch.server import main

ROOT = Path(__file__).resolve().parents[1]


def _pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_package_version_matches_pyproject():
    project = _pyproject()["project"]
    assert project["name"] == "sonicmatch-mcp"
    assert project["version"] == __version__
    assert project["scripts"]["sonicmatch-mcp"] == "sonicmatch.server:main"
    assert project["requires-python"] == ">=3.10"


def test_readme_declares_mcp_registry_name():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "<!-- mcp-name: io.github.js713-lab/sonicmatch-mcp -->" in readme


def test_seed_catalog_copies_match():
    repo = ROOT / "data" / "seed_tracks.json"
    bundled = ROOT / "src" / "sonicmatch" / "data" / "seed_tracks.json"
    assert repo.is_file()
    assert bundled.is_file()
    assert filecmp.cmp(repo, bundled, shallow=False)


def test_mcpb_metadata_versions_match_each_other():
    """The published MCPB bundle is versioned apart from the Python package.

    server.json and manifest.json describe the GitHub Release artifact.
    pyproject.toml is what PyPI trusted publishing uploads. They meet again
    when the maintainer cuts a registry release; see PUBLISH.md.
    """
    server = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    assert server["version"] == manifest["version"]
    assert server["name"] == "io.github.js713-lab/sonicmatch-mcp"
    assert manifest["name"] == "sonicmatch-mcp"


def test_cli_version(capsys: pytest.CaptureFixture[str]):
    main(["--version"])
    assert capsys.readouterr().out.strip() == __version__


def test_cli_help():
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
