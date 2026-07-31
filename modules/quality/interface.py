from core.stages import Stage
from modules.base import StageModule


class QualityModule(StageModule):
    """Quality check interface. Implementations: `default.DefaultQualityModule`."""

    name = Stage.QUALITY
