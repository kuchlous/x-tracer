"""NetlistGraph: connectivity graph for X-Tracer backward tracing."""

from __future__ import annotations

from collections import defaultdict

from .gate import Gate


class NetlistGraph:
    """Stores gates and signal connectivity for backward X-tracing.

    Internally maintains:
      - _gates: dict of instance_path -> Gate
      - _signal_to_drivers: signal -> list[Gate] (gates whose output drives this signal)
      - _signal_to_fanout: signal -> list[Gate] (gates whose input reads this signal)
      - _all_signals: set of all known signal paths
    """

    def __init__(self) -> None:
        self._gates: dict[str, Gate] = {}
        self._signal_to_drivers: dict[str, list[Gate]] = defaultdict(list)
        self._signal_to_fanout: dict[str, list[Gate]] = defaultdict(list)
        self._all_signals: set[str] = set()

    def add_gate(self, gate: Gate) -> None:
        """Register a gate and update signal connectivity maps."""
        self._gates[gate.instance_path] = gate
        for port_name, pin in gate.outputs.items():
            sig = _pin_signal(pin)
            self._signal_to_drivers[sig].append(gate)
            self._all_signals.add(sig)
            # Add port-path alias: "inst.port" → same driver as the wire
            # This lets VCD paths like "tb.dut.ff7.Q" resolve to the gate
            port_path = f"{gate.instance_path}.{port_name}"
            if port_path != sig:
                self._signal_to_drivers[port_path].append(gate)
                self._all_signals.add(port_path)
        for port_name, pin in gate.inputs.items():
            sig = _pin_signal(pin)
            self._signal_to_fanout[sig].append(gate)
            self._all_signals.add(sig)

    def add_gate_fast(self, gate: Gate) -> None:
        """Register a gate -- optimized version with inlined signal key computation.

        Avoids the overhead of _pin_signal function calls and isinstance checks.
        Only call this if all pin values in gate.inputs/outputs are Pin instances.
        """
        inst_path = gate.instance_path
        self._gates[inst_path] = gate
        _drivers = self._signal_to_drivers
        _fanout = self._signal_to_fanout
        _sigs = self._all_signals
        for port_name, pin in gate.outputs.items():
            sig = pin.signal if pin.bit is None else f"{pin.signal}[{pin.bit}]"
            _drivers[sig].append(gate)
            _sigs.add(sig)
            port_path = inst_path + '.' + port_name
            if port_path != sig:
                _drivers[port_path].append(gate)
                _sigs.add(port_path)
        for port_name, pin in gate.inputs.items():
            sig = pin.signal if pin.bit is None else f"{pin.signal}[{pin.bit}]"
            _fanout[sig].append(gate)
            _sigs.add(sig)

    def get_drivers(self, signal: str) -> list[Gate]:
        """Return all gates that drive this signal (usually 1, >1 for multi-driver)."""
        return list(self._signal_to_drivers.get(signal, []))

    def get_fanout(self, signal: str) -> list[Gate]:
        """Return all gates whose inputs include this signal."""
        return list(self._signal_to_fanout.get(signal, []))

    def get_gate(self, instance_path: str) -> Gate | None:
        """Lookup gate by instance path."""
        return self._gates.get(instance_path)

    def get_all_signals(self) -> set[str]:
        """Return set of all signal paths in the netlist."""
        return set(self._all_signals)

    def get_input_cone(self, signal: str, max_depth: int | None = None) -> set[str]:
        """Return all signals in the backward cone of the given signal.

        Args:
            signal: starting signal path
            max_depth: maximum traversal depth (None = unlimited)

        Returns:
            Set of all signal paths reachable by backward traversal.
        """
        visited: set[str] = set()
        # BFS with depth tracking
        from collections import deque
        queue: deque[tuple[str, int]] = deque()
        queue.append((signal, 0))
        while queue:
            sig, depth = queue.popleft()
            if sig in visited:
                continue
            if max_depth is not None and depth > max_depth:
                continue
            visited.add(sig)
            # Try exact signal first, then base signal without bit index
            drivers = self._signal_to_drivers.get(sig, [])
            if not drivers and '[' in sig:
                base_sig = sig[:sig.rindex('[')]
                drivers = self._signal_to_drivers.get(base_sig, [])
            for gate in drivers:
                for pin in gate.inputs.values():
                    inp_sig = _pin_signal(pin)
                    if inp_sig not in visited:
                        queue.append((inp_sig, depth + 1))
        return visited


def _pin_signal(pin: "Gate | Pin") -> str:
    """Canonical signal key for a Pin: 'path[bit]' if bit is set, else 'path'."""
    from .gate import Pin as PinType
    if isinstance(pin, PinType):
        if pin.bit is not None:
            return f"{pin.signal}[{pin.bit}]"
        return pin.signal
    raise TypeError(f"Expected Pin, got {type(pin)}")
