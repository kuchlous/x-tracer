"""VCD loading backend using pyvcd (pure Python fallback)."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

from .database import VCDDatabase


def _import_pyvcd_reader():
    """Import the external pyvcd 'vcd.reader' module, avoiding collision with our package."""
    # Our src/vcd shadows the installed pyvcd 'vcd' package.
    # Temporarily remove src paths so importlib finds the real pyvcd.
    saved = sys.modules.pop("vcd", None)
    saved_reader = sys.modules.pop("vcd.reader", None)
    try:
        # Find the external vcd package by removing local src entries temporarily
        orig_path = list(sys.path)
        src_dir = str(Path(__file__).parent.parent)
        sys.path = [p for p in sys.path if p != src_dir]
        try:
            reader = importlib.import_module("vcd.reader")
        finally:
            sys.path = orig_path
        return reader
    finally:
        # Restore original module state
        if saved is not None:
            sys.modules["vcd"] = saved
        if saved_reader is not None:
            sys.modules["vcd.reader"] = saved_reader


_reader = _import_pyvcd_reader()
TokenKind = _reader.TokenKind
tokenize = _reader.tokenize


def load(vcd_path: Path, signals: set[str] | None = None) -> VCDDatabase:
    """Load VCD using pyvcd tokenizer and return a VCDDatabase."""
    scope_stack: list[str] = []
    id_to_tracked: dict[str, list[str]] = {}
    all_signal_names: set[str] = set()
    transitions: dict[str, list[tuple[int, str]]] = {}
    current_time = 0

    with open(vcd_path, 'rb') as f:
        for token in tokenize(f):
            kind = token.kind

            if kind == TokenKind.SCOPE:
                scope_stack.append(token.data.ident)

            elif kind == TokenKind.UPSCOPE:
                if scope_stack:
                    scope_stack.pop()

            elif kind == TokenKind.VAR:
                var = token.data
                hier_name = '.'.join(scope_stack + [var.reference])
                all_signal_names.add(hier_name)

                # Track this signal?
                if signals is None or hier_name in signals:
                    if var.id_code not in id_to_tracked:
                        id_to_tracked[var.id_code] = []
                    id_to_tracked[var.id_code].append(hier_name)
                    transitions[hier_name] = []

            elif kind == TokenKind.CHANGE_TIME:
                current_time = token.data

            elif kind == TokenKind.CHANGE_SCALAR:
                sc = token.data
                names = id_to_tracked.get(sc.id_code)
                if names:
                    val = sc.value.lower()
                    for name in names:
                        transitions[name].append((current_time, val))

            elif kind == TokenKind.CHANGE_VECTOR:
                vc = token.data
                names = id_to_tracked.get(vc.id_code)
                if names:
                    val = _normalize_vector_value(vc.value)
                    for name in names:
                        transitions[name].append((current_time, val))

    return VCDDatabase(transitions, all_signal_names)


def _normalize_vector_value(value) -> str:
    """Normalize a pyvcd vector value to a lowercase binary string."""
    if isinstance(value, int):
        # pyvcd returns int when no x/z bits present
        return bin(value)[2:]  # e.g. 0 -> '0', 5 -> '101'
    return str(value).lower()
