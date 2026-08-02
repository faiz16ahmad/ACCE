from core.stages import Stage
from modules.base import StageModule


class ShotsModule(StageModule):
    """Shot planner interface. Implementations: `default.DefaultShotsModule`."""

    name = Stage.SHOTS
