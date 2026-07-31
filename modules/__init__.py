"""Pipeline modules.

One responsibility per module, one module per stage. See `modules.base` for
the `StageModule` contract every module implements, and `modules.factory` for
the settings-driven wiring.
"""

from .factory import build_orchestrator

__all__ = ["build_orchestrator"]
