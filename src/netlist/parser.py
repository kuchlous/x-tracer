"""Netlist parser using pyslang for the X-Tracer.

Parses gate-level Verilog into a NetlistGraph by walking the pyslang
elaborated design tree in a single pass.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pyslang

from .gate import Gate, Pin
from .graph import NetlistGraph, _pin_signal

logger = logging.getLogger(__name__)

# --- Sequential detection patterns ---

_SEQ_PATTERNS = [
    re.compile(r"dff", re.IGNORECASE),
    re.compile(r"flop", re.IGNORECASE),
    re.compile(r"latch", re.IGNORECASE),
    re.compile(r"dlat", re.IGNORECASE),
    # Sky130 DFF variants
    re.compile(r"dfxtp"),
    re.compile(r"dfrtp"),
    re.compile(r"dfsbp"),
    re.compile(r"dfbbp"),
    re.compile(r"dfstp"),
    # Sky130 latch variants
    re.compile(r"dlxtp"),
    re.compile(r"dlrtp"),
]

# Known port-role mappings for common cell libraries
_CLOCK_PORTS = {"CLK", "CK", "clk", "ck", "clock", "CLOCK", "CLK_N", "CKN"}
_D_PORTS = {"D", "d", "DIN", "din", "DATA", "data"}
_Q_PORTS = {"Q", "q", "QN", "qn", "DOUT", "dout", "Q_N"}
_RESET_PORTS = {"RST", "rst", "RESET", "reset", "RESET_B", "RST_B",
                "RESET_N", "RST_N", "RN", "CLR", "clr", "CDN"}
_SET_PORTS = {"SET", "set", "SET_B", "SET_N", "SN", "SDN", "PRE", "pre"}


def _is_sequential(cell_type: str) -> bool:
    """Check if a cell type is a sequential element."""
    for pat in _SEQ_PATTERNS:
        if pat.search(cell_type):
            return True
    return False


def _classify_ports(cell_type: str, port_names: list[str]) -> dict[str, str | None]:
    """Identify clock/d/q/reset/set ports by name matching.

    Returns dict with keys: clock_port, d_port, q_port, reset_port, set_port.
    Values are port names or None.
    """
    result: dict[str, str | None] = {
        "clock_port": None,
        "d_port": None,
        "q_port": None,
        "reset_port": None,
        "set_port": None,
    }
    for name in port_names:
        if name in _CLOCK_PORTS:
            result["clock_port"] = name
        elif name in _D_PORTS:
            result["d_port"] = name
        elif name in _Q_PORTS:
            result["q_port"] = name
        elif name in _RESET_PORTS:
            result["reset_port"] = name
        elif name in _SET_PORTS:
            result["set_port"] = name
    return result


def parse_netlist(
    verilog_files: list[Path] | list[str],
    top_module: str | None = None,
) -> NetlistGraph:
    """Parse Verilog files and return the connectivity graph.

    Args:
        verilog_files: Paths to Verilog source files.
        top_module: Name of the top module. If None, pyslang picks the default.

    Returns:
        A NetlistGraph with all gates and connectivity.
    """
    graph = NetlistGraph()

    trees = []
    for f in verilog_files:
        p = Path(f)
        tree = pyslang.SyntaxTree.fromFile(str(p))
        if tree is None:
            logger.warning("Failed to parse file: %s", p)
            continue
        trees.append(tree)

    if not trees:
        return graph

    comp = pyslang.Compilation()
    for tree in trees:
        comp.addSyntaxTree(tree)

    # Allow unknown module instantiations (cell libraries not provided)
    # pyslang treats them as errors; we handle them via syntax-level fallback
    for diag in comp.getAllDiagnostics():
        logger.debug("pyslang: %s", diag)

    root = comp.getRoot()

    for top_inst in root.topInstances:
        if top_module is not None and top_inst.name != top_module:
            continue
        _walk_instance(top_inst, graph)

    return graph


def _walk_instance(inst: pyslang.InstanceSymbol, graph: NetlistGraph) -> None:
    """Recursively walk an instance and its children, extracting gates."""
    body = inst.body

    def visitor(sym):
        if isinstance(sym, pyslang.PrimitiveInstanceSymbol):
            _handle_primitive(sym, graph)
            return pyslang.VisitAction.Skip

        if isinstance(sym, pyslang.InstanceSymbol):
            # Check if this is a leaf cell (no sub-instances / a black box)
            # or a hierarchical module we should descend into.
            child_body = sym.body
            has_sub = _has_structural_content(child_body)
            if has_sub:
                # Hierarchical module — recurse
                return pyslang.VisitAction.Advance
            else:
                # Leaf cell (standard cell / black box)
                _handle_cell_instance(sym, graph)
                return pyslang.VisitAction.Skip

        if isinstance(sym, pyslang.UninstantiatedDefSymbol):
            _handle_uninstantiated(sym, graph)
            return pyslang.VisitAction.Skip

        if isinstance(sym, pyslang.ContinuousAssignSymbol):
            _handle_continuous_assign(sym, graph)
            return pyslang.VisitAction.Advance

        return pyslang.VisitAction.Advance

    body.visit(visitor)


def _has_structural_content(body: pyslang.InstanceBodySymbol) -> bool:
    """Check if a module body contains sub-instances or primitives."""
    found = False

    def check(sym):
        nonlocal found
        if isinstance(sym, (pyslang.PrimitiveInstanceSymbol,
                            pyslang.InstanceSymbol,
                            pyslang.ContinuousAssignSymbol)):
            found = True
            return pyslang.VisitAction.Interrupt
        return pyslang.VisitAction.Advance

    body.visit(check)
    return found


def _handle_primitive(prim: pyslang.PrimitiveInstanceSymbol, graph: NetlistGraph) -> None:
    """Extract a Verilog primitive gate (and, or, not, buf, etc.)."""
    prim_type = prim.primitiveType.name  # "and", "or", "not", etc.
    inst_path = prim.hierarchicalPath

    conns = prim.portConnections
    # For Verilog primitives: first port is output, rest are inputs
    inputs: dict[str, Pin] = {}
    outputs: dict[str, Pin] = {}

    for i, conn in enumerate(conns):
        if i == 0:
            # Output port
            pin = _expr_to_pin(conn)
            if pin is not None:
                outputs["Y"] = pin
        else:
            # Input port
            port_name = chr(ord("A") + i - 1)  # A, B, C, ...
            pin = _expr_to_pin(conn)
            if pin is not None:
                inputs[port_name] = pin

    gate = Gate(
        cell_type=prim_type,
        instance_path=inst_path,
        inputs=inputs,
        outputs=outputs,
        is_sequential=False,
    )
    graph.add_gate(gate)


def _handle_cell_instance(inst: pyslang.InstanceSymbol, graph: NetlistGraph) -> None:
    """Extract a standard cell / black-box module instance."""
    cell_type = inst.body.definition.name
    inst_path = inst.hierarchicalPath

    inputs: dict[str, Pin] = {}
    outputs: dict[str, Pin] = {}
    port_names: list[str] = []

    for port in inst.body.portList:
        if not isinstance(port, pyslang.PortSymbol):
            continue
        port_names.append(port.name)
        pc = inst.getPortConnection(port)
        expr = pc.expression
        if expr is None:
            continue

        # Output ports come as AssignmentExpression (left = external signal)
        # Input ports come as direct expressions (NamedValue, ElementSelect, etc.)
        if port.direction == pyslang.ArgumentDirection.Out:
            if isinstance(expr, pyslang.AssignmentExpression):
                pin = _expr_to_pin(expr.left)
            else:
                pin = _expr_to_pin(expr)
            if pin is not None:
                outputs[port.name] = pin
        else:
            pin = _expr_to_pin(expr)
            if pin is not None:
                inputs[port.name] = pin

    seq = _is_sequential(cell_type)
    port_roles = _classify_ports(cell_type, port_names) if seq else {}

    gate = Gate(
        cell_type=cell_type,
        instance_path=inst_path,
        inputs=inputs,
        outputs=outputs,
        is_sequential=seq,
        clock_port=port_roles.get("clock_port"),
        d_port=port_roles.get("d_port"),
        q_port=port_roles.get("q_port"),
        reset_port=port_roles.get("reset_port"),
        set_port=port_roles.get("set_port"),
    )
    graph.add_gate(gate)


def _handle_uninstantiated(sym: pyslang.UninstantiatedDefSymbol, graph: NetlistGraph) -> None:
    """Handle a cell whose module definition is not available (library not provided).

    Uses portNames + portConnections to infer connectivity. Port direction is
    guessed from common naming conventions (Y/X/Z/Q → output, else input).
    """
    cell_type = sym.definitionName
    inst_path = sym.hierarchicalPath

    # Known output port names for standard cells
    _OUT_PORTS = {"Y", "X", "Z", "ZN", "Q", "QN", "Q_N", "CO", "COUT", "SUM", "S",
                  "SO", "HI", "LO"}

    inputs: dict[str, Pin] = {}
    outputs: dict[str, Pin] = {}
    port_names: list[str] = []

    for pname, pc in zip(sym.portNames, sym.portConnections):
        port_names.append(pname)
        expr = pc.expr
        pin = _expr_to_pin(expr)
        if pin is None:
            continue

        if pname in _OUT_PORTS:
            outputs[pname] = pin
        else:
            inputs[pname] = pin

    seq = _is_sequential(cell_type)
    port_roles = _classify_ports(cell_type, port_names) if seq else {}

    gate = Gate(
        cell_type=cell_type,
        instance_path=inst_path,
        inputs=inputs,
        outputs=outputs,
        is_sequential=seq,
        clock_port=port_roles.get("clock_port"),
        d_port=port_roles.get("d_port"),
        q_port=port_roles.get("q_port"),
        reset_port=port_roles.get("reset_port"),
        set_port=port_roles.get("set_port"),
    )
    graph.add_gate(gate)
    logger.info("Uninstantiated cell: %s %s (guessed %d inputs, %d outputs)",
                cell_type, inst_path, len(inputs), len(outputs))


def _handle_continuous_assign(sym: pyslang.ContinuousAssignSymbol, graph: NetlistGraph) -> None:
    """Handle `assign lhs = rhs;` by creating a pseudo-gate."""
    assign = sym.assignment
    left = assign.left
    right = assign.right

    lpin = _expr_to_pin(left)
    rpin = _expr_to_pin(right)

    if lpin is None or rpin is None:
        logger.debug("Skipping assign with non-simple expression: %s", sym.syntax)
        return

    # Generate a unique instance path for the assign
    lsig = _pin_signal(lpin)
    inst_path = f"__assign__{lsig}"

    gate = Gate(
        cell_type="assign",
        instance_path=inst_path,
        inputs={"A": rpin},
        outputs={"Y": lpin},
        is_sequential=False,
    )
    graph.add_gate(gate)


def _expr_to_pin(expr) -> Pin | None:
    """Convert a pyslang expression to a Pin, extracting signal path and bit index."""
    if expr is None:
        return None

    # AssignmentExpression: output port wiring — extract the left side
    if isinstance(expr, pyslang.AssignmentExpression):
        return _expr_to_pin(expr.left)

    # EmptyArgument: unconnected port
    if isinstance(expr, pyslang.EmptyArgumentExpression):
        return None

    # Conversion (implicit cast) — unwrap
    if isinstance(expr, pyslang.ConversionExpression):
        return _expr_to_pin(expr.operand)

    # Bit select: signal[index]
    if isinstance(expr, pyslang.ElementSelectExpression):
        val_ref = expr.value.getSymbolReference()
        if val_ref is None:
            return None
        sel = expr.selector
        if hasattr(sel, 'constant') and sel.constant is not None:
            bit = sel.constant.convertToInt()
            return Pin(signal=val_ref.hierarchicalPath, bit=bit)
        # Non-constant selector — use syntax as fallback
        return Pin(signal=val_ref.hierarchicalPath, bit=None)

    # Range select: signal[hi:lo] — we don't expand to per-bit here,
    # treat as the base signal with no bit index for simplicity
    if isinstance(expr, pyslang.RangeSelectExpression):
        val_ref = expr.value.getSymbolReference()
        if val_ref is None:
            return None
        return Pin(signal=val_ref.hierarchicalPath, bit=None)

    # Simple named value
    ref = expr.getSymbolReference()
    if ref is not None:
        return Pin(signal=ref.hierarchicalPath, bit=None)

    logger.debug("Cannot convert expression to Pin: %s (kind=%s)", expr.syntax, expr.kind)
    return None
