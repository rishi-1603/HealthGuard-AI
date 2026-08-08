"""Planned extension point for HealthGuard AI MVP.

This boundary is intentionally explicit so future production work can be added safely.
"""

def not_implemented(*args, **kwargs):
    raise NotImplementedError("This production extension is outside the runnable MVP; see README roadmap.")
