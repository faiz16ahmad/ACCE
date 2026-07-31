from core.stages import Stage
from modules.base import StageModule


class ProductionModule(StageModule):
    """Production stage interface. Implementations: `default.DefaultProductionModule`."""

    name = Stage.PRODUCTION
