"""Pipeline settings.

All values come from the environment (prefix `ACCE_`, nested delimiter `__`)
and/or a `.env` file. No secret material should ever live in the repo.
"""

from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class PathsConfig(BaseModel):
    output_dir: Path = Path("out")
    cache_dir: Path = Path(".cache")


class LLMConfig(BaseModel):
    provider: str = "stub"
    model: str = "gemini-2.5-flash"
    api_key: str = ""  # or set GEMINI_API_KEY in the environment
    temperature: float = 0.2
    max_output_tokens: int = 4096
    base_url: str | None = None


class MediaConfig(BaseModel):
    # Ordered fallback chain (cache is always priority 1). "stub" is the
    # key-free default; e.g. ["pexels", "pixabay", "wikimedia"] for real runs.
    providers: list[str] = Field(default_factory=lambda: ["stub"])
    pexels_api_key: str = ""  # or set PEXELS_API_KEY
    pixabay_api_key: str = ""  # or set PIXABAY_API_KEY
    candidates: int = 10  # candidates fetched per provider before ranking
    satisfactory_score: float = 0.6  # minimum rank to stop the chain
    download: bool = True
    download_timeout: float = 15.0


class MusicConfig(BaseModel):
    # Ordered priority chain: Pixabay Music -> Local assets -> Stub.
    providers: list[str] = Field(default_factory=lambda: ["stub"])
    pixabay_api_key: str = ""  # or set PIXABAY_API_KEY
    local_dir: str = "assets/music"
    # Global user-uploaded music library (Director Mode); shared across jobs.
    upload_dir: str = "assets/uploads"

    # --- Music planning/retrieval policy (architecture-audio.md §3.5) ---
    # Normalizer bounds (A7): the LLM proposes, this config enforces.
    emotions: tuple[str, ...] = (
        "calm", "uplifting", "tense", "hopeful", "serious", "playful", "melancholic"
    )
    tempo_min: int = 60
    tempo_max: int = 180
    tempo_tolerance: int = 25  # bpm window for the deterministic tempo score
    max_fade_seconds: float = 8.0

    # Deterministic retrieval ranking weights (§3.5); must sum > 0.
    music_rank_duration: float = 0.40
    music_rank_tempo: float = 0.30
    music_rank_energy: float = 0.10
    music_rank_keyword: float = 0.20
    music_satisfactory_score: float = 0.5  # below this, a match is rejected
    music_candidates: int = 5  # candidates fetched per search before ranking


class TTSConfig(BaseModel):
    provider: str = "stub"  # "stub" | "edge" | "auto" (language pack decides)
    # Edge TTS default voice (Microsoft neural); stub ignores the name.
    voice: str = "en-US-AriaNeural"
    # Per-provider credentials for TTS plugins, e.g. {"elevenlabs": "..."}.
    api_keys: dict[str, str] = {}


class AudioConfig(BaseModel):
    engine: str = "stub"  # "stub" | "ffmpeg"
    ffmpeg_path: str | None = None  # path to ffmpeg binary (for duration measurement)
    music_duck: bool = True  # duck the music bed under narration (ffmpeg mix)
    music_volume: float = 0.2
    narration_volume: float = 1.0
    master_gain: float = 1.0
    music_fade: float = 1.0  # fade in/out (seconds) for the music bed
    narration_fade: float = 0.2
    # Script style -> music genre, driving the music search query.
    # Configurable via ACCE_AUDIO__STYLE_GENRES={"educational":"calm",...} (JSON env).
    style_genres: dict[str, str] = Field(
        default_factory=lambda: {
            "educational": "calm",
            "storytelling": "cinematic",
            "news": "neutral",
            "documentary": "atmospheric",
            "explainer": "ambient",
            "top10": "upbeat",
        }
    )


class ProductionConfig(BaseModel):
    renderer: str = "stub"  # "stub" | "ffmpeg"
    width: int = 1920
    height: int = 1080
    fps: int = 30
    ffmpeg_path: str | None = None
    fade: float = 0.5  # V1 transition fade duration (seconds)
    # x264 encoding quality / speed (milestone 10 publish-ready tuning).
    crf: int = 18  # lower = better quality; 18 is visually lossless for web
    preset: str = "veryfast"  # speed/compression tradeoff
    faststart: bool = True  # -movflags +faststart for instant web playback


class ScriptConfig(BaseModel):
    style: str = "explainer"  # educational|documentary|storytelling|news|top10|explainer
    words_per_minute: int = 150  # approximate narration speaking rate


class ResearchConfig(BaseModel):
    fetch_timeout: float = 8.0
    fetch_retries: int = 2
    max_excerpt_chars: int = 2000
    max_urls: int = 12
    refine: bool = True  # second LLM pass over facts + excerpts (non-authoritative)


class PipelineConfig(BaseModel):
    retries: int = 2


class TimelineConfig(BaseModel):
    """Edit-layer pacing rules (architecture v2, Phase 3).

    The Shot Planner (LLM or template) *proposes* shots; these rules are
    enforced by the normalizer and the Timeline Sync allocation — never by the
    LLM prompt, so the limits stay deterministic and configurable.
    """

    min_shots: int = 1  # shots per scene (lower bound)
    max_shots: int = 6  # shots per scene (upper bound; the LLM is asked for 2-5)
    min_shot_duration: float = 1.5  # seconds per clip
    max_shot_duration: float = 12.0  # seconds per clip
    # Importance -> relative duration weight (Timeline Sync allocation).
    importance_weights: dict[str, float] = Field(
        default_factory=lambda: {"low": 0.8, "medium": 1.0, "high": 1.25, "critical": 1.5}
    )
    # Rhythm -> per-position shaping of the allocation (see timeline.py).
    rhythm_multipliers: dict[str, str] = Field(
        default_factory=lambda: {
            "low": "calm",      # first shot longest, then decays
            "medium": "flat",   # importance weights only
            "high": "build",    # gets busier toward the last shot
            "intense": "rapid", # near-even cuts
        }
    )


class QualityConfig(BaseModel):
    # Deterministic score penalties subtracted from a perfect 100 per issue level.
    penalty_error: float = 25.0
    penalty_warning: float = 5.0
    penalty_info: float = 1.0
    # Script readability thresholds (Flesch Reading Ease, 0–100).
    readability_min: float = 30.0
    readability_max: float = 90.0
    # Duration mismatch tolerance (fraction of the expected duration).
    duration_tolerance: float = 0.15


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ACCE_",
        env_nested_delimiter="__",
        env_file=".env",
        extra="ignore",
    )

    app_name: str = "acce"
    app_version: str = "0.1.0"

    paths: PathsConfig = PathsConfig()
    llm: LLMConfig = LLMConfig()
    media: MediaConfig = MediaConfig()
    music: MusicConfig = MusicConfig()
    tts: TTSConfig = TTSConfig()
    audio: AudioConfig = AudioConfig()
    production: ProductionConfig = ProductionConfig()
    research: ResearchConfig = ResearchConfig()
    script: ScriptConfig = ScriptConfig()
    timeline: TimelineConfig = TimelineConfig()
    pipeline: PipelineConfig = PipelineConfig()
    quality: QualityConfig = QualityConfig()
