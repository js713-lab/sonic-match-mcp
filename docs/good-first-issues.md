# Good first issues

These are not open yet. A maintainer can paste each section into a GitHub issue and add the labels `good first issue` and `help wanted`. Create those labels first if the repository does not have them.

Each task is local, has a done check, and does not need API keys.

## Use one seed catalog file

**Labels:** `good first issue`, `help wanted`

`data/seed_tracks.json` and `src/sonicmatch/data/seed_tracks.json` are the same file twice. `seed_catalog_path()` in `src/sonicmatch/config.py` prefers the repo copy when `pyproject.toml` is two directories above the module, and the packaged copy otherwise. The Docker image copies `data/` because the image also copies `pyproject.toml`. `tests/test_packaging.py::test_seed_catalog_copies_match` fails if they drift.

**Done when:**

- One JSON file is the source of truth.
- A checkout, an installed wheel, and `docker build` all still load at least 20 seed tracks.
- `pytest` and `python -m build` pass. The wheel must still contain `sonicmatch/data/seed_tracks.json` (the CI package job checks this).

**Files:** `src/sonicmatch/config.py`, `Dockerfile`, `tests/test_packaging.py`, and whichever JSON file you delete.

## Report invalid rows in user-owned library JSON

**Labels:** `good first issue`, `help wanted`

`LibraryAdapter` in `src/sonicmatch/music/paid.py` does `except Exception: continue` while reading JSON. A typo in an Epidemic or Artlist export drops that track with no error. The adapter must keep refusing to scrape those sites.

**Done when:**

- A broken row produces a structured error the caller can see (a `SonicError` with a stable code such as `LIBRARY_INVALID`, or notes on `status`), including the file path and row index.
- Valid rows still load.
- A unit test covers one bad row and one good row in the same file.
- No network calls.

**Files:** `src/sonicmatch/music/paid.py`, a test under `tests/`.

## Stop treating Freesound previews as downloads

**Labels:** `good first issue`, `help wanted`

`_map_sound` in `src/sonicmatch/music/freesound.py` sets `download_url` to the preview MP3. Preview files are not the licensed download. `preview_url` can stay.

**Done when:**

- `download_url` is empty unless the API payload actually includes a download field.
- `tests/test_freesound.py` covers a preview-only payload and, if you add it, a payload that has a real download URL.
- Attribution text is unchanged.

**Files:** `src/sonicmatch/music/freesound.py`, `tests/test_freesound.py`.

## Quote ffmpeg arguments that contain spaces

**Labels:** `good first issue`, `help wanted`

`quote_ffmpeg_path` in `src/sonicmatch/ffmpeg_util.py` wraps a path in single quotes. `src/sonicmatch/mix.py` only uses it for the rendered command when the argument contains `/` or `\`:

```python
pretty = " ".join(quote_ffmpeg_path(c) if ("/" in c or "\\" in c) else c for c in cmd)
```

A relative path such as `my clip.mp4` is printed unquoted, so the command splits on the space. A path that contains a single quote needs the existing `'\''` escape.

**Done when:**

- The printed ffmpeg command quotes any argument that contains whitespace or a quote, not only arguments with a slash.
- Unit tests cover a space and a single quote. They do not need to run ffmpeg.
- Existing mix tests still pass.

**Files:** `src/sonicmatch/mix.py`, `src/sonicmatch/ffmpeg_util.py`, a test under `tests/`.

## Put the Jamendo license URL in the attribution line

**Labels:** `good first issue`, `help wanted`

`_map_track` in `src/sonicmatch/music/jamendo.py` appends `shareurl` to `attribution_text` and does not append `license_ccurl`. The license link is the part a Reel editor needs next to CC-BY.

**Done when:**

- Attribution text includes the license URL when the payload has `license_ccurl` or `licenseccurl`.
- A CC-BY-NC URL still maps to a non-commercial license name (see `_cc_from_url`).
- A fixture test builds a track from a dict and does not call the network.

**Files:** `src/sonicmatch/music/jamendo.py`, a test under `tests/`.

## Run CI on Python 3.13

**Labels:** `good first issue`, `help wanted`

`pyproject.toml` classifiers list Python 3.13. `.github/workflows/ci.yml` tests 3.10, 3.11, and 3.12 only.

**Done when:**

- The test matrix includes `3.13`.
- `pytest` passes on that version, with a dependency pin only if something actually breaks.
- No change to the 3.10 floor.

**Files:** `.github/workflows/ci.yml`, and `pyproject.toml` only if a dependency cap is required.
