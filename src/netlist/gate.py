"""Gate and Pin dataclasses for the X-Tracer netlist representation."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Pin:
    """A connection to a single bit of a signal."""
    signal: str      # hierarchical signal path, e.g. "tb.dut.n42"
    bit: int | None  # bit index, or None for scalar connections


@dataclass
class Gate:
    """A gate instance in the netlist."""
    cell_type: str              # e.g. "and", "sky130_fd_sc_hd__dfxtp_1"
    instance_path: str          # e.g. "tb.dut.U42"
    inputs: dict[str, Pin] = field(default_factory=dict)
    outputs: dict[str, Pin] = field(default_factory=dict)
    is_sequential: bool = False
    clock_port: str | None = None
    d_port: str | None = None
    q_port: str | None = None
    reset_port: str | None = None
    set_port: str | None = None
