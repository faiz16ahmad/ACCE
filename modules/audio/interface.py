from core.stages import Stage
from modules.base import StageModule


class AudioModule(StageModule):
    """Audio stage interface. Implementations: `default.DefaultAudioModule`."""

    name = Stage.AUDIO
