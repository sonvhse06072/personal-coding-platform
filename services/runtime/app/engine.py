"""Compatibility import for the checkpointed runtime engine.

The implementation is split into engine_core (lifecycle/state transitions),
engine_execution (coding/verification loop), and engine_delivery (bounded GitHub
branch/PR/CI delivery) so each trust boundary stays reviewable.
"""

from .engine_delivery import RuntimeEngine

__all__ = ["RuntimeEngine"]
