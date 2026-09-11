"""Compatibility import for the checkpointed runtime engine.

The implementation is split into engine_core (lifecycle/state transitions) and
engine_execution (coding/verification loop) so the state machine stays reviewable.
"""

from .engine_execution import RuntimeEngine

__all__ = ["RuntimeEngine"]
