from core.stages import Stage
from modules.base import StageModule


class MediaModule(StageModule):
    """Media search interface. Implementations: `default.DefaultMediaModule`."""

    name = Stage.MEDIA
