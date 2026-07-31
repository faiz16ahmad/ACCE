"""The ordered pipeline stages.

Enum definition order is the execution order — the orchestrator iterates
`Stage` and runs each registered module in sequence.
"""

from enum import StrEnum


class Stage(StrEnum):
    RESEARCH = "research"
    SCRIPT = "script"
    SCENES = "scenes"
    MEDIA = "media"
    AUDIO = "audio"
    PRODUCTION = "production"
    QUALITY = "quality"
