"""VCD Database — unified interface for querying signal values from VCD files."""

from __future__ import annotations

import bisect
from pathlib import Path
from typing import Optional


# Timescale unit to femtoseconds conversion
_TS_UNITS = {
    's': 1_000_000_000_000_000,
    'ms': 1_000_000_000_000,
    'us': 1_000_000_000,
    'ns': 1_000_000,
    'ps': 1_000,
    'fs': 1,
}


class VCDDatabase:
    """Queryable database of signal transitions loaded from a VCD file.

    Internal storage: per-signal sorted list of (time, value_string) tuples.
    Lookups use bisect for O(log n) performance.
    Times are stored in VCD-native units internally; the timescale_fs attribute
    allows callers to convert to/from picoseconds if needed.
    """

    def __init__(self, transitions: dict[str, list[tuple[int, str]]], signals: set[str],
                 timescale_fs: int = 1000):
        """Initialize from pre-parsed transition data.

        Args:
            transitions: signal_path -> sorted list of (time, value_string)
            signals: set of all signal paths present in the VCD
            timescale_fs: timescale in femtoseconds per VCD time unit (default 1000 = 1ps)
        """
        self._transitions = transitions
        self._signals = signals
        self.timescale_fs = timescale_fs
        # Pre-extract sorted time arrays for bisect
        self._times: dict[str, list[int]] = {
            sig: [t for t, _ in tlist] for sig, tlist in transitions.items()
        }

    def ps_to_vcd(self, ps: int) -> int:
        """Convert picoseconds to VCD-native time units."""
        return (ps * 1000) // self.timescale_fs

    def vcd_to_ps(self, vcd_time: int) -> int:
        """Convert VCD-native time units to picoseconds."""
        return (vcd_time * self.timescale_fs) // 1000

    def get_value(self, signal: str, time: int) -> str:
        """Get full value string of signal at time (e.g., '01x0' for a 4-bit bus)."""
        tlist = self._transitions.get(signal)
        if tlist is None:
            raise KeyError(f"Signal '{signal}' not found in VCD")
        times = self._times[signal]
        idx = bisect.bisect_right(times, time) - 1
        if idx < 0:
            return 'x'  # no transition yet — value unknown
        return tlist[idx][1]

    def get_bit(self, signal: str, bit: int, time: int) -> str:
        """Get single-bit value ('0','1','x','z') of signal[bit] at time.

        For bus: bit 0 = LSB (rightmost in VCD binary string).
        Treats 'z' as 'x' per spec (Section 2.2).
        """
        value = self.get_value(signal, time)
        val = _extract_bit(value, bit)
        if val == 'z':
            return 'x'
        return val

    def get_transitions(self, signal: str) -> list[tuple[int, str]]:
        """Return sorted list of (time, value) transitions for signal."""
        tlist = self._transitions.get(signal)
        if tlist is None:
            raise KeyError(f"Signal '{signal}' not found in VCD")
        return list(tlist)

    def first_x_time(self, signal: str, bit: int, after: int = 0) -> int | None:
        """Return earliest time >= after where signal[bit] is 'x' (or 'z'). None if never."""
        tlist = self._transitions.get(signal)
        if tlist is None:
            raise KeyError(f"Signal '{signal}' not found in VCD")
        times = self._times[signal]

        # Check value at 'after' first
        idx = bisect.bisect_right(times, after) - 1
        if idx < 0:
            # Before first transition — value is x
            return after

        # Check from the transition at or before 'after' onwards
        start_idx = max(0, idx)
        for i in range(start_idx, len(tlist)):
            t, val = tlist[i]
            effective_t = max(t, after)
            bit_val = _extract_bit(val, bit)
            if bit_val in ('x', 'z'):
                return effective_t

        return None

    def find_edge(self, signal: str, bit: int, edge: str, before: int) -> int | None:
        """Find last rising ('rise') or falling ('fall') edge of signal[bit] before time.

        Returns the time of the edge, or None if not found.
        """
        tlist = self._transitions.get(signal)
        if tlist is None:
            raise KeyError(f"Signal '{signal}' not found in VCD")
        times = self._times[signal]

        # Find last transition index strictly before 'before'
        end_idx = bisect.bisect_left(times, before)

        # Walk backwards looking for the edge
        for i in range(end_idx - 1, 0, -1):
            t_cur, val_cur = tlist[i]
            _, val_prev = tlist[i - 1]
            bit_cur = _extract_bit(val_cur, bit)
            bit_prev = _extract_bit(val_prev, bit)

            if edge == 'rise' and bit_prev == '0' and bit_cur == '1':
                return t_cur
            if edge == 'fall' and bit_prev == '1' and bit_cur == '0':
                return t_cur

        return None

    def has_signal(self, signal: str) -> bool:
        """Check if signal exists in VCD."""
        return signal in self._signals

    def get_all_signals(self) -> set[str]:
        """Return set of all signal paths in VCD."""
        return set(self._signals)


def _extract_bit(value: str, bit: int) -> str:
    """Extract a single bit from a value string.

    bit 0 = LSB = rightmost character.
    If value is shorter than needed, extends with MSB (leftmost char).
    """
    if len(value) == 1:
        return value.lower()
    idx = len(value) - 1 - bit
    if idx < 0:
        # Extend with MSB
        return value[0].lower()
    return value[idx].lower()


class PrefixMappedVCD(VCDDatabase):
    """VCD wrapper that translates between netlist paths and VCD paths.

    Example: if vcd_prefix='rjn_top.u_rjn_soc_top' and netlist_top='rjn_soc_top',
    then netlist signal 'rjn_soc_top.inst_foo.Y' maps to VCD signal
    'rjn_top.u_rjn_soc_top.inst_foo.Y'.
    """

    def __init__(self, inner: VCDDatabase, vcd_prefix: str, netlist_top: str):
        # Don't call super().__init__ — we delegate to inner
        self._inner = inner
        self._vcd_prefix = vcd_prefix.rstrip('.')
        self._netlist_top = netlist_top.rstrip('.')
        self.timescale_fs = inner.timescale_fs

    def _to_vcd(self, signal: str) -> str:
        """Translate netlist signal path to VCD signal path."""
        if signal.startswith(self._netlist_top + '.'):
            return self._vcd_prefix + signal[len(self._netlist_top):]
        if signal.startswith(self._vcd_prefix + '.'):
            return signal  # already a VCD path
        return signal

    def get_value(self, signal: str, time: int) -> str:
        return self._inner.get_value(self._to_vcd(signal), time)

    def get_bit(self, signal: str, bit: int, time: int) -> str:
        return self._inner.get_bit(self._to_vcd(signal), bit, time)

    def get_transitions(self, signal: str) -> list[tuple[int, str]]:
        return self._inner.get_transitions(self._to_vcd(signal))

    def first_x_time(self, signal: str, bit: int, after: int = 0) -> int | None:
        return self._inner.first_x_time(self._to_vcd(signal), bit, after)

    def find_edge(self, signal: str, bit: int, edge: str, before: int) -> int | None:
        return self._inner.find_edge(self._to_vcd(signal), bit, edge, before)

    def has_signal(self, signal: str) -> bool:
        return self._inner.has_signal(self._to_vcd(signal))

    def get_all_signals(self) -> set[str]:
        return self._inner.get_all_signals()

    def ps_to_vcd(self, ps: int) -> int:
        return self._inner.ps_to_vcd(ps)

    def vcd_to_ps(self, vcd_time: int) -> int:
        return self._inner.vcd_to_ps(vcd_time)


def load_vcd_header(vcd_path: Path | str) -> tuple[set[str], int]:
    """Parse only the VCD header for fast signal existence checking.

    Returns (signal_names: set[str], timescale_fs: int).
    Does not load any value-change data -- only reads up to $enddefinitions $end.
    """
    vcd_path = Path(vcd_path)
    from .pyvcd_backend import parse_vcd_header
    return parse_vcd_header(vcd_path)


def load_vcd_fast_rust(vcd_path: Path | str, signal_names: set[str] | list[str],
                       timescale_fs: int = 1000) -> VCDDatabase:
    """Load specific signals from a VCD using the Rust streaming backend.

    This is the fastest path for large VCDs (multi-GB) when you only need a
    handful of signals.  It streams through the file once, decoding only the
    requested signals, so memory usage is proportional to the number of
    transitions in those signals rather than the file size.

    Args:
        vcd_path: Path to the VCD file.
        signal_names: Hierarchical signal names (dot-separated).
        timescale_fs: Timescale in femtoseconds per VCD time unit (default 1000 = 1ps).

    Returns:
        VCDDatabase populated with the requested signals' transitions.
    """
    import xtracer_vcd
    signal_list = list(signal_names)
    raw = xtracer_vcd.extract_signals(str(vcd_path), signal_list)
    # raw is dict[str, list[tuple[int, str]]] — exactly what VCDDatabase expects
    transitions = {name: list(tlist) for name, tlist in raw.items()}
    all_signals = set(transitions.keys())
    return VCDDatabase(transitions, all_signals, timescale_fs=timescale_fs)


def load_vcd(vcd_path: Path | str, signals: set[str] | None = None) -> VCDDatabase:
    """Load VCD file. If signals is provided, only load those signals (optimization).

    Tries Rust streaming backend first for selective loading, then pywellen,
    then falls back to pyvcd.
    """
    vcd_path = Path(vcd_path)

    # Fast path: if specific signals requested, try the Rust streaming backend
    if signals:
        try:
            return load_vcd_fast_rust(vcd_path, signals)
        except Exception:
            pass

    try:
        from .pywellen_backend import load as _load_pywellen
        return _load_pywellen(vcd_path, signals)
    except BaseException:
        pass

    from .pyvcd_backend import load as _load_pyvcd
    return _load_pyvcd(vcd_path, signals)
