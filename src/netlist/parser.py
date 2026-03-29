"""Netlist parser using pyslang for the X-Tracer.

Parses gate-level Verilog into a NetlistGraph by walking the pyslang
elaborated design tree in a single pass.
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path

import pyslang

from .gate import Gate, Pin
from .graph import NetlistGraph, _pin_signal

logger = logging.getLogger(__name__)

# Progress logging interval (number of gates between log messages)
_PROGRESS_INTERVAL = 100_000

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


# Power/ground ports to skip (not functional connections)
_PG_PORTS = frozenset({"VDD", "VSS", "VNW", "VPW", "VDDPE", "VDDCE", "VSSE"})

# Patterns that identify TSMC leaf cells (no need to check for sub-instances)
_LEAF_CELL_PATTERNS = (
    re.compile(r"_A9PP\d+Z"),       # TSMC A9 process cells
    re.compile(r"_[A-Z]*\d+X\d*"),  # Common TSMC naming: ..._X1, ..._D2X1
)


def _is_leaf_cell_name(name: str) -> bool:
    """Fast check: does this module name look like a leaf standard cell?"""
    for pat in _LEAF_CELL_PATTERNS:
        if pat.search(name):
            return True
    return False


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
    overall_t0 = time.time()
    graph = NetlistGraph()

    # --- Phase 1: Parse syntax trees ---
    trees = []
    for f in verilog_files:
        p = Path(f)
        logger.info("Parsing file: %s (%.1f MB)", p, p.stat().st_size / (1024 * 1024))
        t0 = time.time()
        tree = pyslang.SyntaxTree.fromFile(str(p))
        elapsed = time.time() - t0
        if tree is None:
            logger.warning("Failed to parse file: %s", p)
            continue
        logger.info("  Parsed in %.1fs", elapsed)
        trees.append(tree)

    if not trees:
        return graph

    # --- Phase 2: Compile ---
    logger.info("Starting compilation...")
    t0 = time.time()
    comp = pyslang.Compilation()
    for tree in trees:
        comp.addSyntaxTree(tree)

    # Allow unknown module instantiations (cell libraries not provided)
    # pyslang treats them as errors; we handle them via syntax-level fallback
    diag_count = 0
    for diag in comp.getAllDiagnostics():
        logger.debug("pyslang: %s", diag)
        diag_count += 1
    logger.info("  Compilation done in %.1fs (%d diagnostics)", time.time() - t0, diag_count)

    root = comp.getRoot()

    # --- Phase 3: Walk and extract gates ---
    # Cache for _has_structural_content keyed by definition name
    structural_cache: dict[str, bool] = {}
    # Counter for progress logging
    gate_counter = [0]

    logger.info("Walking design hierarchy...")
    t0 = time.time()
    for top_inst in root.topInstances:
        if top_module is not None and top_inst.name != top_module:
            continue
        logger.info("  Walking top instance: %s", top_inst.name)
        _walk_instance(top_inst, graph, structural_cache, gate_counter)

    walk_elapsed = time.time() - t0
    total_elapsed = time.time() - overall_t0
    total_gates = len(graph._gates)
    total_signals = len(graph._all_signals)
    logger.info("Walk complete: %d gates, %d signals in %.1fs",
                total_gates, total_signals, walk_elapsed)
    logger.info("Total parse_netlist time: %.1fs", total_elapsed)

    return graph


def _walk_instance(
    inst: pyslang.InstanceSymbol,
    graph: NetlistGraph,
    structural_cache: dict[str, bool] | None = None,
    gate_counter: list[int] | None = None,
) -> None:
    """Recursively walk an instance and its children, extracting gates."""
    if structural_cache is None:
        structural_cache = {}
    if gate_counter is None:
        gate_counter = [0]

    body = inst.body

    def _log_progress() -> None:
        gate_counter[0] += 1
        if gate_counter[0] % _PROGRESS_INTERVAL == 0:
            logger.info("  ... processed %dK gates so far", gate_counter[0] // 1000)

    def visitor(sym):
        if isinstance(sym, pyslang.PrimitiveInstanceSymbol):
            _handle_primitive(sym, graph)
            _log_progress()
            return pyslang.VisitAction.Skip

        if isinstance(sym, pyslang.InstanceSymbol):
            # Check if this is a leaf cell (no sub-instances / a black box)
            # or a hierarchical module we should descend into.
            child_body = sym.body
            def_name = child_body.definition.name
            has_sub = _has_structural_content_cached(
                def_name, child_body, structural_cache
            )
            if has_sub:
                # Hierarchical module — recurse
                return pyslang.VisitAction.Advance
            else:
                # Leaf cell (standard cell / black box)
                _handle_cell_instance(sym, graph)
                _log_progress()
                return pyslang.VisitAction.Skip

        if isinstance(sym, pyslang.UninstantiatedDefSymbol):
            _handle_uninstantiated(sym, graph)
            _log_progress()
            return pyslang.VisitAction.Skip

        if isinstance(sym, pyslang.ContinuousAssignSymbol):
            _handle_continuous_assign(sym, graph)
            return pyslang.VisitAction.Advance

        return pyslang.VisitAction.Advance

    body.visit(visitor)


def _has_structural_content_cached(
    def_name: str,
    body: pyslang.InstanceBodySymbol,
    cache: dict[str, bool],
) -> bool:
    """Check if a module body contains sub-instances or primitives (cached).

    Results are cached by definition name so that repeated instances of the
    same cell type only pay the visit cost once.  Known leaf-cell name
    patterns are short-circuited without visiting at all.
    """
    if def_name in cache:
        return cache[def_name]

    # Fast path: if the name matches a known leaf-cell pattern, skip visiting
    if _is_leaf_cell_name(def_name):
        cache[def_name] = False
        return False

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
    cache[def_name] = found
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
        # Skip power/ground ports (VDD, VSS, VNW, VPW, etc.)
        if port.name in _PG_PORTS:
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
                  "SO", "HI", "LO", "ECK", "ck_out", "Q0", "Q1", "QN0", "QN1"}

    inputs: dict[str, Pin] = {}
    outputs: dict[str, Pin] = {}
    port_names: list[str] = []

    for pname, pc in zip(sym.portNames, sym.portConnections):
        if pname in _PG_PORTS:
            continue  # skip power/ground ports
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
    if lpin is None:
        logger.debug("Skipping assign with non-simple LHS: %s", sym.syntax)
        return

    # Try simple RHS first
    rpin = _expr_to_pin(right)

    if rpin is None:
        # Complex RHS: collect all leaf signal references
        cell_type, leaf_pins = _decompose_expr(right)
        if not leaf_pins:
            logger.debug("Skipping assign with no extractable inputs: %s", sym.syntax)
            return
        lsig = _pin_signal(lpin)
        inst_path = f"__assign__{lsig}"
        seen: dict[str, Pin] = {}
        for pin in leaf_pins:
            key = _pin_signal(pin)
            if key not in seen:
                seen[key] = pin
        inputs: dict[str, Pin] = {}
        for i, (key, pin) in enumerate(seen.items()):
            port_name = chr(ord("A") + i) if i < 26 else f"in{i}"
            inputs[port_name] = pin
        gate = Gate(
            cell_type=cell_type,
            instance_path=inst_path,
            inputs=inputs,
            outputs={"Y": lpin},
            is_sequential=False,
        )
        graph.add_gate(gate)
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


# Mapping from pyslang BinaryOperator to cell type names
_BINOP_TO_CELL = {
    'BinaryAnd': 'and',
    'BinaryOr': 'or',
    'BinaryXor': 'xor',
    'BinaryXnor': 'xnor',
}


def _decompose_expr(expr) -> tuple[str, list[Pin]]:
    """Recursively extract leaf Pins from a complex expression.

    Returns (cell_type, leaf_pins) where cell_type is an approximation of the
    top-level operation, and leaf_pins is a flat list of all signal references.
    For complex/mixed expressions, cell_type falls back to 'assign_expr'
    which the gate model treats conservatively (any X input -> X output).
    """
    if expr is None:
        return ('assign_expr', [])

    # Conversion — unwrap
    if isinstance(expr, pyslang.ConversionExpression):
        return _decompose_expr(expr.operand)

    # Simple leaf — delegate to _expr_to_pin
    pin = _expr_to_pin(expr)
    if pin is not None:
        return ('assign', [pin])

    # Binary expression (a op b)
    if isinstance(expr, pyslang.BinaryExpression):
        op_name = expr.op.name
        _, left_pins = _decompose_expr(expr.left)
        _, right_pins = _decompose_expr(expr.right)
        all_pins = left_pins + right_pins
        cell = _BINOP_TO_CELL.get(op_name, 'assign_expr')
        return (cell, all_pins)

    # Conditional / ternary (sel ? a : b)
    if isinstance(expr, pyslang.ConditionalExpression):
        all_pins: list[Pin] = []
        for cond in expr.conditions:
            _, cond_pins = _decompose_expr(cond.expr)
            all_pins.extend(cond_pins)
        _, true_pins = _decompose_expr(expr.left)
        _, false_pins = _decompose_expr(expr.right)
        all_pins.extend(true_pins)
        all_pins.extend(false_pins)
        return ('mux', all_pins)

    # Unary expression (e.g. !a, ~a)
    if isinstance(expr, pyslang.UnaryExpression):
        return _decompose_expr(expr.operand)

    logger.debug("Cannot decompose expression: %s (kind=%s)", expr.syntax, expr.kind)
    return ('assign_expr', [])


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
