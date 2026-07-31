"""Provider layer.

No module calls an external API directly — every external capability is
reached through an interface in `providers.base` and resolved via
`providers.registry`. V1 ships stub implementations only.
"""
