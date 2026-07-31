"""Pipeline error hierarchy.

Modules raise these to signal contract violations and transient failures.
The orchestrator retries *only the failing stage* on retryable errors.
"""


class PipelineError(Exception):
    """Base error for all ACCE pipeline failures."""


class InputValidationError(PipelineError):
    """A stage was invoked with input it cannot process."""


class OutputValidationError(PipelineError):
    """A stage produced artifacts that do not satisfy its contract."""


class StageRetryableError(PipelineError):
    """Transient failure — the orchestrator may retry this stage."""
