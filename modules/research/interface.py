from core.stages import Stage
from modules.base import StageModule


class ResearchModule(StageModule):
    """Research stage interface. Implementations: `default.DefaultResearchModule`."""

    name = Stage.RESEARCH
