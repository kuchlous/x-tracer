"""Tests for the X-Tracer core algorithm against golden testcases."""

import json
import re
from pathlib import Path

import pytest

from src.netlist import parse_netlist, parse_netlist_fast, NetlistGraph, Gate, Pin
from src.vcd import load_vcd, VCDDatabase
from src.gates import GateModel
from src.tracer import trace_x, collect_leaves, XCause

CASES_DIR = Path(__file__).resolve().parent / "cases" / "synthetic"


def _parse_sig_bit(sig_str: str) -> tuple[str, int]:
    """Parse 'tb.dut.foo[3]' -> ('tb.dut.foo', 3). Scalars default to bit 0."""
    m = re.match(r'^(.+)\[(\d+)\]$', sig_str)
    if m:
        return m.group(1), int(m.group(2))
    return sig_str, 0


def _leaf_sig_keys(node: XCause) -> set[str]:
    """Collect signal keys from all leaves."""
    leaves = collect_leaves(node)
    return {leaf.signal for leaf in leaves}


def _load_case(case_dir: Path):
    """Load netlist, VCD, and manifest for a test case."""
    manifest = json.loads((case_dir / "manifest.json").read_text())
    netlist = parse_netlist([case_dir / "netlist.v", case_dir / "tb.v"])
    vcd = load_vcd(case_dir / "sim.vcd")
    gate_model = GateModel()
    return netlist, vcd, gate_model, manifest


def _run_case(case_dir: Path) -> tuple[XCause, dict]:
    """Run trace on a case and return (result, manifest)."""
    netlist, vcd, gate_model, manifest = _load_case(case_dir)
    query_sig, query_bit = _parse_sig_bit(manifest["query"]["signal"])
    query_time = manifest["query"]["time"]
    result = trace_x(netlist, vcd, gate_model, query_sig, query_bit, query_time)
    return result, manifest


def _verify_injection_target(result: XCause, manifest: dict) -> bool:
    """Check if the injection target appears in the cause tree leaves.

    Accepts both wire paths (tb.dut.q0) and port paths (tb.dut.ff0.Q)
    as equivalent, since the tracer may report either form.
    """
    inj_target = manifest["expected"]["injection_target"]
    inj_sig, inj_bit = _parse_sig_bit(inj_target)
    inj_key = f"{inj_sig}[{inj_bit}]"
    leaf_keys = _leaf_sig_keys(result)
    if inj_key in leaf_keys:
        return True
    # Port-path alias: if target is inst.PORT, check if any leaf's gate
    # has an output port matching. Also check if the wire driven by the
    # target instance appears in leaves.
    leaves = collect_leaves(result)
    for leaf in leaves:
        if leaf.gate is not None:
            # Check if leaf's gate instance + output port matches
            for port_name, pin in leaf.gate.outputs.items():
                port_path = f"{leaf.gate.instance_path}.{port_name}[{inj_bit}]"
                if port_path == inj_key:
                    return True
            # Check if the injection target's instance matches
            inst_path = inj_sig.rsplit('.', 1)[0] if '.' in inj_sig else ''
            if leaf.gate.instance_path == inst_path:
                return True
    return False


def _case_has_netlist_coverage(case_dir: Path) -> bool:
    """Check if the parser can extract meaningful connectivity for this case."""
    netlist = parse_netlist([case_dir / "netlist.v", case_dir / "tb.v"])
    return len(netlist.get_all_signals()) > 0


# --- Individual targeted tests ---

class TestSingleGate:
    def test_and_gate_x_on_input(self):
        case_dir = CASES_DIR / "gates" / "synth_s1_and_2in_xmask01_0"
        result, manifest = _run_case(case_dir)
        assert result.cause_type == "primary_input"
        assert _verify_injection_target(result, manifest)

    def test_and_gate_x_propagation(self):
        case_dir = CASES_DIR / "gates" / "synth_s1_and_2in_xmask10_0"
        result, manifest = _run_case(case_dir)
        assert _verify_injection_target(result, manifest)


class TestChainCases:
    def test_bus_encoder(self):
        case_dir = CASES_DIR / "structural" / "bus_encoder_w4"
        result, manifest = _run_case(case_dir)
        assert _verify_injection_target(result, manifest)

    def test_reconverge(self):
        case_dir = CASES_DIR / "structural" / "reconverge_d2"
        result, manifest = _run_case(case_dir)
        assert _verify_injection_target(result, manifest)


class TestMultibit:
    def test_bit_slice_select(self):
        case_dir = CASES_DIR / "multibit" / "bit_slice_w16_b0_select"
        result, manifest = _run_case(case_dir)
        assert _verify_injection_target(result, manifest)

    def test_bit_slice_part_select(self):
        case_dir = CASES_DIR / "multibit" / "bit_slice_w16_b0_part_select"
        result, manifest = _run_case(case_dir)
        assert _verify_injection_target(result, manifest)

    def test_partial_bus_and(self):
        case_dir = CASES_DIR / "multibit" / "partial_bus_and_w4"
        result, manifest = _run_case(case_dir)
        assert _verify_injection_target(result, manifest)

    def test_partial_bus_or(self):
        case_dir = CASES_DIR / "multibit" / "partial_bus_or_w4"
        result, manifest = _run_case(case_dir)
        assert _verify_injection_target(result, manifest)


class TestEdgeCases:
    def test_max_depth_cutoff(self):
        case_dir = CASES_DIR / "structural" / "reconverge_d2"
        netlist, vcd, gate_model, manifest = _load_case(case_dir)
        query_sig, query_bit = _parse_sig_bit(manifest["query"]["signal"])
        query_time = manifest["query"]["time"]
        result = trace_x(netlist, vcd, gate_model, query_sig, query_bit,
                         query_time, max_depth=1)
        leaves = collect_leaves(result)
        types = {leaf.cause_type for leaf in leaves}
        assert "max_depth" in types or "primary_input" in types

    def test_signal_not_x_raises(self):
        case_dir = CASES_DIR / "gates" / "synth_s1_and_2in_xmask01_0"
        netlist, vcd, gate_model, manifest = _load_case(case_dir)
        with pytest.raises(ValueError, match="not 'x'"):
            trace_x(netlist, vcd, gate_model, "tb.dut.a", 0, 30000)


# --- Bulk tests ---

class TestBulk:
    @pytest.mark.parametrize("case_name", [
        d.name for d in sorted((CASES_DIR / "gates").iterdir())
        if (d / "manifest.json").exists()
    ] if (CASES_DIR / "gates").exists() else [])
    def test_gates_bulk(self, case_name):
        case_dir = CASES_DIR / "gates" / case_name
        result, manifest = _run_case(case_dir)
        assert _verify_injection_target(result, manifest), (
            f"Injection target {manifest['expected']['injection_target']} "
            f"not in leaves: {_leaf_sig_keys(result)}"
        )

    @pytest.mark.parametrize("case_name", [
        d.name for d in sorted((CASES_DIR / "multibit").iterdir())
        if (d / "manifest.json").exists()
    ] if (CASES_DIR / "multibit").exists() else [])
    def test_multibit_bulk(self, case_name):
        case_dir = CASES_DIR / "multibit" / case_name
        result, manifest = _run_case(case_dir)
        assert _verify_injection_target(result, manifest), (
            f"Injection target {manifest['expected']['injection_target']} "
            f"not in leaves: {_leaf_sig_keys(result)}"
        )

    @pytest.mark.parametrize("case_name", [
        d.name for d in sorted((CASES_DIR / "structural").iterdir())
        if (d / "manifest.json").exists()
    ] if (CASES_DIR / "structural").exists() else [])
    def test_structural_gate_level(self, case_name):
        case_dir = CASES_DIR / "structural" / case_name
        result, manifest = _run_case(case_dir)
        assert _verify_injection_target(result, manifest), (
            f"Injection target {manifest['expected']['injection_target']} "
            f"not in leaves: {_leaf_sig_keys(result)}"
        )


# --- Stress tests ---

STRESS_DIR = Path(__file__).resolve().parent / "cases" / "stress"
STRESS_EDGE_DIR = Path(__file__).resolve().parent / "cases" / "stress_edge"


class TestStress:
    def test_lfsr_grid_trace_all_leaves_primary_input(self):
        """Stress: 2x2x2x2x8 LFSR grid -- all leaves must be primary_input
        with signal tb.dut.inject_data[0], and no max_depth leaves."""
        case_dir = STRESS_DIR
        manifest = json.loads((case_dir / "manifest.json").read_text())

        netlist = parse_netlist_fast(
            [case_dir / "netlist.v", case_dir / "tb.v"],
            top_module="tb",
        )
        vcd = load_vcd(case_dir / "sim.vcd")
        gate_model = GateModel()

        query_sig, query_bit = _parse_sig_bit(manifest["query"]["signal"])
        query_time = manifest["query"]["time"]
        result = trace_x(
            netlist, vcd, gate_model,
            query_sig, query_bit, query_time,
            max_depth=500,
        )

        leaves = collect_leaves(result)
        assert len(leaves) > 0, "Trace returned no leaves"

        # Every leaf must be primary_input (no max_depth cutoffs)
        leaf_types = {leaf.cause_type for leaf in leaves}
        assert leaf_types == {"primary_input"}, (
            f"Expected all leaves to be primary_input, got: {leaf_types}"
        )

        # Every leaf must point to the injection target
        expected_sig = manifest["expected"]["injection_target"]
        exp_sig, exp_bit = _parse_sig_bit(expected_sig)
        exp_key = f"{exp_sig}[{exp_bit}]"
        leaf_sigs = {leaf.signal for leaf in leaves}
        assert leaf_sigs == {exp_key}, (
            f"Expected all leaves to be {exp_key}, got: {leaf_sigs}"
        )

    # --- Stress edge cases (positional Verilog primitives -> parse_netlist) ---

    def _load_stress_edge(self, name):
        """Helper: load a stress_edge case using parse_netlist (pyslang)."""
        case_dir = STRESS_EDGE_DIR / name
        netlist = parse_netlist(
            [case_dir / "netlist.v", case_dir / "tb.v"],
            top_module="tb",
        )
        vcd = load_vcd(case_dir / "sim.vcd")
        gate_model = GateModel()
        query_time = vcd.first_x_time("tb.dut.final_out", 0)
        result = trace_x(
            netlist, vcd, gate_model,
            "tb.dut.final_out", 0, query_time,
            max_depth=500,
        )
        leaves = collect_leaves(result)
        return leaves

    def test_deep_pipeline_uninit_ff(self):
        """Stress edge: 104-stage deep pipeline traces to ff_q_0[0] uninit_ff."""
        leaves = self._load_stress_edge("deep_pipeline")
        assert len(leaves) == 1, f"Expected 1 leaf, got {len(leaves)}"
        assert leaves[0].cause_type == "uninit_ff"
        assert leaves[0].signal == "tb.dut.ff_q_0[0]"

    def test_wide_fanout_all_32_leaves_single_source(self):
        """Stress edge: 32-way fanout reconverges -- all 32 leaves at src_q[0]."""
        leaves = self._load_stress_edge("wide_fanout")
        assert len(leaves) == 32, f"Expected 32 leaves, got {len(leaves)}"
        leaf_types = {leaf.cause_type for leaf in leaves}
        assert leaf_types == {"uninit_ff"}, (
            f"Expected all uninit_ff, got: {leaf_types}"
        )
        leaf_sigs = {leaf.signal for leaf in leaves}
        assert leaf_sigs == {"tb.dut.src_q[0]"}, (
            f"Expected all leaves at src_q[0], got: {leaf_sigs}"
        )

    def test_clock_crossing_traces_to_domain_a(self):
        """Stress edge: CDC -- traces across clock boundary to a_q0[0] uninit_ff."""
        leaves = self._load_stress_edge("clock_crossing")
        assert len(leaves) == 1, f"Expected 1 leaf, got {len(leaves)}"
        assert leaves[0].cause_type == "uninit_ff"
        assert leaves[0].signal == "tb.dut.a_q0[0]"

    def test_tristate_bus_identifies_driver(self):
        """Stress edge: tri-state bus -- d2_q[0] uninit_ff leaf found
        (x_injection leaves on bus are expected and ignored)."""
        leaves = self._load_stress_edge("tristate_bus")
        uninit_leaves = [l for l in leaves if l.cause_type == "uninit_ff"]
        assert len(uninit_leaves) == 1, (
            f"Expected 1 uninit_ff leaf, got {len(uninit_leaves)}"
        )
        assert uninit_leaves[0].signal == "tb.dut.d2_q[0]"
        # The remaining leaves are x_injection on the bus (expected)
        other_leaves = [l for l in leaves if l.cause_type != "uninit_ff"]
        for leaf in other_leaves:
            assert leaf.cause_type == "x_injection"

    def test_nested_clock_gate_two_ff_leaves(self):
        """Stress edge: nested ICG -- qa[0] and qb[0] are uninit_ff leaves."""
        leaves = self._load_stress_edge("nested_clock_gate")
        assert len(leaves) == 2, f"Expected 2 leaves, got {len(leaves)}"
        leaf_types = {leaf.cause_type for leaf in leaves}
        assert leaf_types == {"uninit_ff"}, (
            f"Expected all uninit_ff, got: {leaf_types}"
        )
        leaf_sigs = {leaf.signal for leaf in leaves}
        assert leaf_sigs == {"tb.dut.qa[0]", "tb.dut.qb[0]"}, (
            f"Expected qa[0] and qb[0], got: {leaf_sigs}"
        )
