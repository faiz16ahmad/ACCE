"""Director Mode — post-production overlay on the Audio Pipeline.

Not a pipeline stage: a read-only-over-the-pipeline service wired at the API
layer (docs/director-mode.md). V1 edits only the background music (keep /
remove / swap / upload / volume / fades), previews by remix + video-copy remux,
and produces immutable exports. The automatic pipeline and its outputs are
never modified.
"""
