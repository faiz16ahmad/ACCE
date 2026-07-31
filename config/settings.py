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


class TTSConfig(BaseModel):
    provider: str = "stub"
    voice: str = "en-US-Wavenet-D"


class AudioConfig(BaseModel):
    engine: str = "stub"  # "stub" | "ffmpeg"
    music_style: str = "ambient background music"
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
    width: int = 1920
    height: int = 1080
    fps: int = 30
    ffmpeg_path: str | None = None


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
    pipeline: PipelineConfig = PipelineConfig()
