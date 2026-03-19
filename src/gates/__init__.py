"""Gate X-Propagation Model for X-Tracer.

Provides GateModel class for evaluating gate outputs under 4-state
(0/1/x/z) logic and determining causal X-valued inputs.
"""

from .model import GateModel

__all__ = ['GateModel']
