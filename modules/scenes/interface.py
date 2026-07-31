from core.stages import Stage
from modules.base import StageModule


class ScenesModule(StageModule):
    """Scene planner interface. Implementations: `default.DefaultScenesModule`."""

    name = Stage.SCENES
