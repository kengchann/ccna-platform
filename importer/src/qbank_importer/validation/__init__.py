"""Modular validation framework (the pipeline's Validator stage).

- :class:`ValidationRule` — the contract one independent check implements.
- :class:`Validator` — the engine that runs a rule set over the item stream.
- :func:`default_rules` — the built-in rule set.

Rules observe and flag; they never mutate or reject. See base.py for the
design constraints.
"""

from .base import RunState, ValidationRule
from .engine import Validator
from .rules import default_rules

__all__ = ["RunState", "ValidationRule", "Validator", "default_rules"]
