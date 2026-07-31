from core.stages import Stage
from modules.base import StageModule


class ScriptModule(StageModule):
    """Script stage interface. Implementations: `default.DefaultScriptModule`."""

    name = Stage.SCRIPT
