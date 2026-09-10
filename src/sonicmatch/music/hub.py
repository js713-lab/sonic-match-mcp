"""Pluggable music hub: seed + Jamendo + Freesound + user library + sqlite index."""

from __future__ import annotations

from sonicmatch.config import Settings
from sonicmatch.errors import SonicError
from sonicmatch.models import CATALOG_CHOICES, SearchQuery, Track, VideoSonicProfile
from sonicmatch.music.embed import ensure_embed
from sonicmatch.music.freesound import FreesoundAdapter
from sonicmatch.music.index import TrackIndex
from sonicmatch.music.jamendo import JamendoAdapter
from sonicmatch.music.paid import LibraryAdapter
from sonicmatch.music.seed import SeedAdapter


class MusicHub:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.seed = SeedAdapter()
        self.jamendo = JamendoAdapter(settings)
        self.freesound = FreesoundAdapter(settings)
        self.library = LibraryAdapter(settings)
        self.index = TrackIndex(settings.db_path)
        if self.index.count() == 0:
            self.index.upsert(self.seed.all())
        else:
            # Keep seed rows fresh without wiping Jamendo/Freesound cache.
            self.index.upsert(self.seed.all())

    def get(self, track_id: str) -> Track | None:
        hit = self.index.get(track_id)
        if hit:
            return hit
        if track_id.startswith("jamendo_"):
            if not self.settings.has_jamendo:
                raise SonicError(
                    "JAMENDO_DISABLED",
                    "JAMENDO_CLIENT_ID is not set; cannot fetch Jamendo tracks.",
                )
            t = self.jamendo.get(track_id)
        elif track_id.startswith("freesound_"):
            if not self.settings.has_freesound:
                raise SonicError(
                    "FREESOUND_DISABLED",
                    "FREESOUND_API_KEY is not set; cannot fetch Freesound tracks.",
                )
            t = self.freesound.get(track_id)
        elif track_id.startswith("generated_"):
            t = None
        else:
            t = self.seed.get(track_id) or self.library.get(track_id)
        if t:
            self.index.upsert([t])
        return t

    def collect(
        self,
        profile: VideoSonicProfile,
        *,
        catalog: str,
        limit: int,
        instrumental_only: bool,
        genre: str | None,
        mood: str | None,
    ) -> tuple[list[Track], list[str]]:
        if catalog not in CATALOG_CHOICES:
            raise SonicError("BAD_ARGS", f"catalog must be one of {', '.join(CATALOG_CHOICES)}")
        notes: list[str] = []
        found: list[Track] = []
        queries = list(profile.search_queries) or ["instrumental bed"]
        if mood:
            queries = [mood] + queries
        if genre:
            queries = [genre] + queries

        def _q(text: str) -> SearchQuery:
            return SearchQuery(
                query=text,
                instrumental=True if instrumental_only else None,
                bpm_min=(profile.suggested_bpm[0] - 8) if profile.suggested_bpm else None,
                bpm_max=(profile.suggested_bpm[1] + 8) if profile.suggested_bpm else None,
                limit=limit * 3,
            )

        if catalog in {"auto", "seed"}:
            for q in queries[:3]:
                found.extend(self.seed.search(_q(q)))
            found.extend(self.seed.all())
            notes.append(f"seed catalog: {len(self.seed.all())} tracks")
        # Generated beds are never mixed into "license-safe" auto recs.

        if catalog in {"auto", "jamendo"}:
            if not self.settings.has_jamendo:
                notes.append("Jamendo skipped: JAMENDO_CLIENT_ID is not set.")
            else:
                try:
                    for q in queries[:2]:
                        found.extend(self.jamendo.search(_q(q)))
                    notes.append("Jamendo searched.")
                except SonicError as exc:
                    notes.append(f"Jamendo unavailable: {exc.message}")

        if catalog in {"auto", "freesound"}:
            if not self.settings.has_freesound:
                notes.append("Freesound skipped: FREESOUND_API_KEY is not set.")
            else:
                try:
                    for q in queries[:2]:
                        found.extend(self.freesound.search(_q(q)))
                    notes.append("Freesound searched (beds/loops).")
                except SonicError as exc:
                    notes.append(f"Freesound unavailable: {exc.message}")

        if catalog in {"auto", "library"}:
            if self.library.empty():
                if catalog == "library":
                    notes.append(
                        "User library empty. Point SONICMATCH_LIBRARY_PATH at a JSON "
                        "export of tracks you already license (Epidemic/Artlist)."
                    )
                else:
                    notes.append("User-owned paid library not configured.")
            else:
                try:
                    for q in queries[:2]:
                        found.extend(self.library.search(_q(q)))
                    found.extend(self.library.all())
                    notes.append(f"user library: {len(self.library.all())} tracks")
                except SonicError as exc:
                    notes.append(exc.message)

        found = [ensure_embed(t) for t in found if t.source != "generated"]
        # Embedding nearest-neighbours from the sqlite index as extra candidates.
        try:
            found.extend(
                t
                for _score, t in self.index.similar(profile, limit=limit * 2)
                if t.source != "generated"
            )
        except Exception:
            pass
        self.index.upsert(found)
        return found, notes

    def search(self, query: SearchQuery, catalog: str) -> tuple[list[Track], list[str]]:
        if catalog not in CATALOG_CHOICES:
            raise SonicError("BAD_ARGS", f"catalog must be one of {', '.join(CATALOG_CHOICES)}")
        tracks: list[Track] = []
        notes: list[str] = []
        if catalog in {"auto", "seed"}:
            tracks.extend(self.seed.search(query))
        if catalog in {"auto", "jamendo"}:
            if not self.settings.has_jamendo:
                notes.append("Jamendo skipped: JAMENDO_CLIENT_ID is not set.")
            else:
                try:
                    tracks.extend(self.jamendo.search(query))
                except SonicError as exc:
                    notes.append(exc.message)
        if catalog in {"auto", "freesound"}:
            if not self.settings.has_freesound:
                notes.append("Freesound skipped: FREESOUND_API_KEY is not set.")
            else:
                try:
                    tracks.extend(self.freesound.search(query))
                except SonicError as exc:
                    notes.append(exc.message)
        if catalog in {"auto", "library"}:
            if self.library.empty():
                notes.append("User library empty / not configured.")
            else:
                try:
                    tracks.extend(self.library.search(query))
                except SonicError as exc:
                    notes.append(exc.message)
        seen: set[str] = set()
        uniq: list[Track] = []
        for t in tracks:
            if t.id in seen:
                continue
            seen.add(t.id)
            uniq.append(ensure_embed(t))
        self.index.upsert(uniq)
        return uniq[: query.limit], notes
