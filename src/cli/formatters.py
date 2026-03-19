"""Output formatters for X-Tracer cause trees: text, json, dot."""

from __future__ import annotations

import json
from typing import Any

from src.tracer.core import XCause


def format_text(node: XCause, indent: int = 0) -> str:
    """Format cause tree as human-readable indented text."""
    lines: list[str] = []
    _format_text_recursive(node, indent, lines)
    return "\n".join(lines)


def _format_text_recursive(node: XCause, indent: int, lines: list[str]) -> None:
    prefix = " " * indent
    gate_info = ""
    if node.gate is not None:
        gate_info = f" (gate={node.gate.cell_type}, inst={node.gate.instance_path})"
    lines.append(f"{prefix}[{node.cause_type}] {node.signal} @ t={node.time}{gate_info}")
    for child in node.children:
        _format_text_recursive(child, indent + 2, lines)


def _node_to_dict(node: XCause) -> dict[str, Any]:
    """Convert XCause node to a JSON-serializable dict."""
    d: dict[str, Any] = {
        "signal": node.signal,
        "time": node.time,
        "cause_type": node.cause_type,
    }
    if node.gate is not None:
        d["gate"] = {
            "cell_type": node.gate.cell_type,
            "instance_path": node.gate.instance_path,
        }
    if node.children:
        d["children"] = [_node_to_dict(c) for c in node.children]
    else:
        d["children"] = []
    return d


def format_json(node: XCause) -> str:
    """Format cause tree as JSON."""
    return json.dumps(_node_to_dict(node), indent=2)


def format_dot(node: XCause) -> str:
    """Format cause tree as Graphviz DOT."""
    lines: list[str] = ["digraph xcause {", "  rankdir=TB;"]
    node_ids: dict[int, str] = {}
    counter = [0]

    def get_id(n: XCause) -> str:
        oid = id(n)
        if oid not in node_ids:
            node_ids[oid] = f"n{counter[0]}"
            counter[0] += 1
        return node_ids[oid]

    def visit(n: XCause) -> None:
        nid = get_id(n)
        label = f"{n.cause_type}\\n{n.signal}\\nt={n.time}"
        lines.append(f'  {nid} [label="{label}"];')
        for child in n.children:
            cid = get_id(child)
            lines.append(f"  {nid} -> {cid};")
            visit(child)

    visit(node)
    lines.append("}")
    return "\n".join(lines)
