"""Director Mode unit tests (V1): schemas, store, remix, library, service.

Tests exercise the new modules/director/ package in isolation (tmp_path),
except for one integration test that uses a real generated job to verify the
preview/export flow end-to-end with real ffmpeg.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from config.settings import Settings
from modules.audio.schemas import AudioMixPlan, MixSegment
from modules.director.library import BundledSource, UploadSource, MusicLibrary, probe_duration
from modules.director.remix import build_director_plan, remix_master
from modules.director.schemas import (
    DirectorSnapshot,
    DirectorState,
    ExportRecord,
    MusicEdit,
    MusicTrack,
    TrackRef,
)
from modules.director.service import DirectorService
from modules.director.store import DirectorStore, new_export_id


# ── schemas ----------------------------------------------------------------


def test_music_edit_defaults():
    m = MusicEdit()
    assert m.mode == "ai"
    assert m.volume == 0.2
    assert m.duck is True
    assert m.loop is True


def test_director_state_roundtrip():
    state = DirectorState(
        base={"ai_track": "bundled:calm_ambient_bed"},
        music=MusicEdit(mode="ai"),
        updated_at="2026-01-01T00:00:00Z",
    )
    data = state.model_dump(mode="json")
    restored = DirectorState.model_validate(data)
    assert restored.music.mode == "ai"
    assert restored.base.ai_track == "bundled:calm_ambient_bed"
    assert restored.version == 1


def test_export_record_roundtrip():
    rec = ExportRecord(
        export_id="ex_123",
        created_at="2026-01-01T00:00:00Z",
        video_path="exports/ex_123/final_video.mp4",
        size=1000,
        duration=60.0,
        music=MusicEdit(mode="library", volume=0.3),
        url="/artifacts/job-x/exports/ex_123/final_video.mp4",
    )
    data = rec.model_dump(mode="json")
    restored = ExportRecord.model_validate(data)
    assert restored.export_id == "ex_123"
    assert restored.music.volume == 0.3


# ── store ------------------------------------------------------------------


def test_store_initializes_from_audio_json(tmp_path):
    job_dir = tmp_path / "job-x"
    audio_dir = job_dir / "audio"
    audio_dir.mkdir(parents=True)
    (audio_dir / "audio.json").write_text(
        json.dumps({"music_path": "assets/music/cinematic_tense_bed.wav", "duration": 50.0}),
        encoding="utf-8",
    )
    store = DirectorStore(job_dir)
    state = store.load()
    assert state.base.ai_track == "bundled:cinematic_tense_bed"
    assert state.music.mode == "ai"
    assert (job_dir / "director" / "director.json").is_file()


def test_store_roundtrip(tmp_path):
    job_dir = tmp_path / "job-y"
    audio_dir = job_dir / "audio"
    audio_dir.mkdir(parents=True)
    (audio_dir / "audio.json").write_text("{}", encoding="utf-8")
    store = DirectorStore(job_dir)
    state = store.load()
    state.music = MusicEdit(mode="library", track_ref=TrackRef(track_id="bundled:cinematic_tense_bed"))
    store.save(state)
    loaded = DirectorStore(job_dir).load()
    assert loaded.music.mode == "library"
    assert loaded.music.track_ref.track_id == "bundled:cinematic_tense_bed"


def test_store_add_upload(tmp_path):
    job_dir = tmp_path / "job-u"
    audio_dir = job_dir / "audio"
    audio_dir.mkdir(parents=True)
    (audio_dir / "audio.json").write_text("{}", encoding="utf-8")
    store = DirectorStore(job_dir)
    # filename is sanitized (spaces → dashes)
    store.add_upload("my song.mp3", b"fake-audio")
    assert (job_dir / "director" / "uploads" / "my-song.mp3").is_file()
    state = store.load()
    assert "my-song.mp3" in state.uploads


# ── library ----------------------------------------------------------------


def test_bundled_source_scans_local_dir(tmp_path):
    bed = tmp_path / "music"
    bed.mkdir()
    (bed / "calm_ambient_bed.wav").write_bytes(b"x")
    (bed / "cinematic_tense_bed.wav").write_bytes(b"y")
    source = BundledSource(local_dir=str(bed))
    tracks = source.list()
    assert len(tracks) == 2
    ids = {t.track_id for t in tracks}
    assert "bundled:calm_ambient_bed" in ids
    assert "bundled:cinematic_tense_bed" in ids
    assert source.resolve("bundled:calm_ambient_bed") is not None
    assert source.resolve("bundled:other") is None


def test_upload_source_scans_job_uploads(tmp_path):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "mytrack.mp3").write_bytes(b"z")
    source = UploadSource(uploads)
    tracks = source.list()
    assert len(tracks) == 1
    assert tracks[0].track_id == "upload:mytrack"


def test_music_library_aggregates(tmp_path):
    music = tmp_path / "music"
    music.mkdir()
    (music / "a.wav").write_bytes(b"1")
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "b.wav").write_bytes(b"2")
    lib = MusicLibrary(
        [BundledSource(str(music)), UploadSource(uploads)],
    )
    assert len(lib.list()) == 2
    assert lib.resolve("bundled:a") is not None
    assert lib.resolve("upload:b") is not None
    assert lib.resolve("other:z") is None


# ── remix ------------------------------------------------------------------


def _narration_plan() -> AudioMixPlan:
    segs = [
        MixSegment(kind="narration", source_path=Path("n1.txt"), start=0.0, end=3.0, volume=1.0, fade_in=0.2, fade_out=0.2),
        MixSegment(kind="narration", source_path=Path("n2.txt"), start=3.0, end=6.0, volume=1.0, fade_in=0.2, fade_out=0.2),
    ]
    return AudioMixPlan(segments=segs, master_gain=1.0)


def _original_with_music(bed: Path) -> AudioMixPlan:
    segs = [
        MixSegment(kind="music", source_path=bed, start=0.0, end=6.0, volume=0.2, fade_in=1.0, fade_out=1.0, duck={"depth_db": 8.0, "attack": 0.05, "release": 0.5}),
        MixSegment(kind="narration", source_path=Path("n1.txt"), start=0.0, end=3.0, volume=1.0, fade_in=0.2, fade_out=0.2),
        MixSegment(kind="narration", source_path=Path("n2.txt"), start=3.0, end=6.0, volume=1.0, fade_in=0.2, fade_out=0.2),
    ]
    return AudioMixPlan(segments=segs, master_gain=1.0)


def test_director_plan_mode_ai(tmp_path):
    bed = tmp_path / "calm_ambient_bed.wav"
    bed.write_bytes(b"x")
    plan = build_director_plan(
        _original_with_music(bed),
        MusicEdit(mode="ai", volume=0.3),
        bed,
    )
    narr = [s for s in plan.segments if s.kind == "narration"]
    mus = [s for s in plan.segments if s.kind == "music"]
    assert len(narr) == 2 and len(mus) == 1
    assert mus[0].source_path == bed
    assert mus[0].volume == 0.3
    assert mus[0].end == 6.0


def test_director_plan_mode_none_removes_music(tmp_path):
    bed = tmp_path / "calm_ambient_bed.wav"
    bed.write_bytes(b"x")
    plan = build_director_plan(
        _original_with_music(bed),
        MusicEdit(mode="none"),
        None,
    )
    mus = [s for s in plan.segments if s.kind == "music"]
    narr = [s for s in plan.segments if s.kind == "narration"]
    assert mus == [] and len(narr) == 2


def test_director_plan_unresolvable_track_falls_back_to_master(tmp_path):
    """When track_path is None (unresolvable), the plan is narration-only."""
    plan = build_director_plan(
        _original_with_music(tmp_path / "missing.bed"),
        MusicEdit(mode="library", track_ref=TrackRef(track_id="bundled:missing")),
        None,  # unresolvable
    )
    assert all(s.kind == "narration" for s in plan.segments)


# ── export -----------------------------------------------------------------


def test_remux_produces_file(tmp_path):
    """Minimal remux: create a tiny video + audio, remux, verify file exists."""
    import subprocess
    from config.settings import Settings
    from modules.director.export import remux
    ff = Settings().production.ffmpeg_path
    # create a 1s silent video
    video = tmp_path / "in.mp4"
    subprocess.run([ff, "-y", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1", "-c:v", "libx264", "-an", str(video)],
                   capture_output=True, timeout=30, check=True)
    # create a 1s silent audio
    audio = tmp_path / "in.wav"
    subprocess.run([ff, "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", "1", str(audio)],
                   capture_output=True, timeout=30, check=True)
    out = tmp_path / "out.mp4"
    remux(video, audio, out, ffmpeg_path=ff)
    assert out.is_file() and out.stat().st_size > 0


def test_remux_atomic_no_partial_on_failure(tmp_path):
    """A failed remux must not leave a partial file at the target path.

    Regression: a corrupt master made ffmpeg abort mid-encode, leaving a
    truncated preview that the cache then served forever (10s video, no audio).
    """
    import subprocess
    from config.settings import Settings
    from modules.director.export import remux
    ff = Settings().production.ffmpeg_path
    video = tmp_path / "in.mp4"
    subprocess.run([ff, "-y", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1", "-c:v", "libx264", "-an", str(video)],
                   capture_output=True, timeout=30, check=True)
    # a text file is not decodable audio → remux must fail
    bad_audio = tmp_path / "bad.m4a"
    bad_audio.write_text("this is not audio", encoding="utf-8")
    out = tmp_path / "out.mp4"
    with pytest.raises(Exception):
        remux(video, bad_audio, out, ffmpeg_path=ff)
    assert not out.exists(), "no partial file may remain at the target"
    assert not list(tmp_path.glob("*.part*")), "no .part temp may remain"


def test_decode_check_rejects_garbage(tmp_path):
    from config.settings import Settings
    from modules.director.library import decode_check
    ff = Settings().production.ffmpeg_path
    bad = tmp_path / "bad.m4a"
    bad.write_bytes(b"garbage" * 100)
    assert decode_check(bad, ff) is False
    # a real generated master passes the check
    master = tmp_path / "ok.wav"
    import subprocess
    subprocess.run([ff, "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", "1", str(master)],
                   capture_output=True, timeout=30, check=True)
    assert decode_check(master, ff) is True


# ── integration (uses real job) --------------------------------------------


@pytest.mark.skipif(
    not Path("out/job-33025d0ae04e/audio/audio.json").exists(),
    reason="requires real generated Bitcoin job",
)
def test_service_preview_and_export():
    """End-to-end against a real job: set music → preview → export → verify files."""
    settings = Settings()
    svc = DirectorService("job-33025d0ae04e", settings)

    # start from a clean state: revert to AI, then snapshot
    snap0 = svc.set_music(MusicEdit(mode="ai"))
    assert snap0.state.music.mode == "ai"
    assert snap0.current_track is not None
    assert len(snap0.library) >= 5

    # swap
    snap2 = svc.set_music(MusicEdit(mode="library", track_ref=TrackRef(track_id="bundled:cinematic_tense_bed"), volume=0.3))
    assert snap2.state.music.mode == "library"
    assert snap2.state.music.track_ref.track_id == "bundled:cinematic_tense_bed"

    # preview
    preview = svc.preview()
    assert preview.is_file() and preview.stat().st_size > 0

    # export
    rec = svc.export()
    assert rec.duration > 0
    assert rec.video_path.endswith("final_video.mp4")
    assert Path("out/job-33025d0ae04e") / rec.video_path
    assert Path("out/job-33025d0ae04e") / rec.video_path.replace("final_video.mp4", "export.json")

    # revert to AI
    snap3 = svc.set_music(MusicEdit(mode="ai"))
    assert snap3.state.music.mode == "ai"

    # remove music
    snap4 = svc.set_music(MusicEdit(mode="none"))
    assert snap4.state.music.mode == "none"
    assert snap4.current_track is None


# ── uploads: global library + naming -----------------------------------------


def test_upload_source_add_file_records_name(tmp_path):
    source = UploadSource(str(tmp_path))
    track_id = source.add_file("my groove.wav", b"fake", name="Deep Space Groove")
    assert track_id == "upload:my-groove"
    assert (tmp_path / "my-groove.wav").is_file()
    tracks = source.list()
    assert len(tracks) == 1
    assert tracks[0].title == "Deep Space Groove"
    assert tracks[0].track_id == "upload:my-groove"


def test_upload_source_rename_updates_title(tmp_path):
    source = UploadSource(str(tmp_path))
    source.add_file("bed.wav", b"x", name="Original")
    source.rename("upload:bed", "Moon Mission BGM")
    tracks = source.list()
    assert tracks[0].title == "Moon Mission BGM"
    # renaming never changes the stable track_id
    assert tracks[0].track_id == "upload:bed"


def test_upload_source_name_falls_back_to_stem(tmp_path):
    source = UploadSource(str(tmp_path))
    source.add_file("somethingsong.wav", b"x")  # no name given
    tracks = source.list()
    assert tracks[0].title == "somethingsong"


def test_upload_visible_in_every_job_library(tmp_path):
    """Uploads are GLOBAL: one upload appears in any job's Director library."""
    music_dir = tmp_path / "music"
    music_dir.mkdir()
    (music_dir / "calm.wav").write_bytes(b"1")
    upload_root = tmp_path / "uploads"

    from modules.director.service import DirectorService

    class _Settings:
        class music:
            local_dir = str(music_dir)
            upload_dir = str(upload_root)

        class production:
            ffmpeg_path = "ffmpeg"

        class paths:
            output_dir = tmp_path / "out"

    # job A uploads a track
    svc_a = DirectorService("job-a", _Settings())
    svc_a.upload("mine.wav", b"audio", name="My Track")

    # job B sees it in its library
    svc_b = DirectorService("job-b", _Settings())
    titles = [t.title for t in svc_b.list_library() if t.provider == "upload"]
    assert "My Track" in titles


def test_remix_master_raises_clean_error_on_corrupt_track(tmp_path):
    """A garbage upload must raise a clear error, not a raw ffmpeg dump."""
    from modules.audio.engine import AudioEngineError
    from config.settings import Settings
    from modules.director.remix import build_director_plan, remix_master
    from modules.director.schemas import MusicEdit, TrackRef
    ff = Settings().production.ffmpeg_path

    bad = tmp_path / "bad.mp3"
    bad.write_bytes(b"this is not a valid mp3" * 50)

    plan = AudioMixPlan(
        segments=[
            MixSegment(kind="music", source_path=bad, start=0.0, end=10.0, volume=0.3),
        ],
        master_gain=1.0,
    )
    out = tmp_path / "master.m4a"
    with pytest.raises(AudioEngineError, match="invalid or partial audio file"):
        remix_master(plan, out, ffmpeg_path=ff)
    assert not out.exists(), "failed remix must not leave a master behind"
