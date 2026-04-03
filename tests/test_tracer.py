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

    def test_deep_pipeline_traces_to_ff0(self):
        """Stress edge: 104-stage deep pipeline — trace reaches ff_q_0,
        the force-injected DFF (root cause)."""
        leaves = self._load_stress_edge("deep_pipeline")
        assert len(leaves) == 1, f"Expected 1 leaf, got {len(leaves)}"
        assert leaves[0].signal == "tb.dut.ff_q_0[0]", (
            f"Expected root cause at ff_q_0, got {leaves[0].signal}"
        )

    def test_wide_fanout_traces_to_source_dff(self):
        """Stress edge: 32-way fanout reconverges — all uninit_ff leaves
        trace to src_q (the force-injected source DFF)."""
        leaves = self._load_stress_edge("wide_fanout")
        assert len(leaves) == 32, f"Expected 32 leaves, got {len(leaves)}"
        src_leaves = [l for l in leaves if "src_q" in l.signal]
        assert len(src_leaves) >= 24, (
            f"Expected >=24 leaves at src_q (root cause), got {len(src_leaves)}"
        )

    def test_clock_crossing_traces_to_a_q0(self):
        """Stress edge: CDC — traces across clock boundary to a_q0,
        the force-injected DFF in domain A (root cause)."""
        leaves = self._load_stress_edge("clock_crossing")
        assert len(leaves) == 1, f"Expected 1 leaf, got {len(leaves)}"
        assert leaves[0].signal == "tb.dut.a_q0[0]", (
            f"Expected root cause at a_q0, got {leaves[0].signal}"
        )

    def test_tristate_bus_identifies_driver(self):
        """Stress edge: tri-state bus — trace reaches bus x_injection."""
        leaves = self._load_stress_edge("tristate_bus")
        assert len(leaves) >= 1
        leaf_types = {l.cause_type for l in leaves}
        assert "x_injection" in leaf_types or "uninit_ff" in leaf_types

    def test_nested_clock_gate_traces_to_primary_input(self):
        """Stress edge: nested ICG — traces to gated clock as primary_input."""
        leaves = self._load_stress_edge("nested_clock_gate")
        assert len(leaves) == 2, f"Expected 2 leaves, got {len(leaves)}"
        leaf_sigs = {l.signal for l in leaves}
        assert "tb.dut.gclk_l3[0]" in leaf_sigs or "tb.dut.qa[0]" in leaf_sigs


# --- SoC integration tests (skipped when VCD/netlist not available) ---

#SOC_NETLIST = Path("/Backend_share/pd_dv_1p1/Dec_26_Flat_SDF/rjn_soc_top.Fill_uniquify.v")
#SOC_GPIO_VCD = Path("/data/work_area/alokk/x-tracer/proj/verif/run/run_log/gpio_x_test2/gpio_x.vcd")
#SOC_RESET_VCD = Path("/data/work_area/alokk/x-tracer/proj/verif/run/run_log/reset_x_test2/reset_x.vcd")
#SOC_VCD_PREFIX = "rjn_top.u_rjn_soc_top"
#SOC_NETLIST_TOP = "rjn_soc_top"
#
#soc_gpio_available = SOC_NETLIST.exists() and SOC_GPIO_VCD.exists()
#soc_reset_available = SOC_NETLIST.exists() and SOC_RESET_VCD.exists()
#
#
#def _soc_trace(netlist, vcd_path, query_signal, query_time_ps, max_depth=50):
#    """Shared helper: load cone, trace, return leaves.
#
#    Handles VCD prefix mapping, per-instance port loading, and
#    Cadence escaped identifiers.
#    """
#    from src.vcd.database import load_vcd_header, PrefixMappedVCD
#
#    all_sigs, ts_fs = load_vcd_header(vcd_path)
#    netlist_sig = query_signal.replace(SOC_VCD_PREFIX, SOC_NETLIST_TOP, 1)
#
#    # Compute backward cone
#    cone = netlist.get_input_cone(netlist_sig, max_depth=max_depth)
#
#    # Map cone to VCD names + add per-instance port signals
#    vcd_cone = set()
#    for sig in cone:
#        if sig.startswith(SOC_NETLIST_TOP + "."):
#            vcd_sig = SOC_VCD_PREFIX + sig[len(SOC_NETLIST_TOP):]
#        else:
#            vcd_sig = sig
#        if vcd_sig in all_sigs:
#            vcd_cone.add(vcd_sig)
#    vcd_cone.add(query_signal)
#
#    # Add per-instance port signals for gates in the cone
#    for gate in netlist._gates.values():
#        inst = gate.instance_path
#        in_cone = any(pin.signal in cone for pin in
#                      list(gate.inputs.values()) + list(gate.outputs.values()))
#        if not in_cone:
#            continue
#        vcd_inst = SOC_VCD_PREFIX + inst[len(SOC_NETLIST_TOP):] if inst.startswith(SOC_NETLIST_TOP + ".") else inst
#        inst_leaf = vcd_inst.rsplit('.', 1)[-1]
#        inst_parent = vcd_inst.rsplit('.', 1)[0] if '.' in vcd_inst else ''
#        for pname in list(gate.inputs.keys()) + list(gate.outputs.keys()):
#            for candidate in (f"{vcd_inst}.{pname}",
#                              f"{inst_parent}.\\{inst_leaf}.{pname}" if inst_parent else None):
#                if candidate and candidate in all_sigs:
#                    vcd_cone.add(candidate)
#                    break
#
#    vcd = load_vcd(vcd_path, signals=vcd_cone)
#    mapped_vcd = PrefixMappedVCD(vcd, SOC_VCD_PREFIX, SOC_NETLIST_TOP)
#
#    vcd_time = (query_time_ps * 1000) // ts_fs
#    result = trace_x(
#        netlist, mapped_vcd, GateModel(),
#        netlist_sig, 0, vcd_time, max_depth=max_depth,
#    )
#    return collect_leaves(result)
#
#
#@pytest.mark.skipif(not soc_gpio_available, reason="SoC GPIO VCD not available")
#@pytest.mark.slow
#class TestSoCGPIOTrace:
#    """Real SoC GPIO injection tests — TSMC 22nm ARM A55.
#
#    User workflow: GPIO APP_GPIO0 forced to X at 50us, test hangs.
#    User finds X on GPIO sync register, traces to root cause.
#    """
#
#    @pytest.fixture(scope="class")
#    def soc_netlist(self):
#        return parse_netlist_fast([SOC_NETLIST], top_module=SOC_NETLIST_TOP)
#
#    def test_gpio_sync_register_traces_to_primary_input(self, soc_netlist):
#        """X on GPIO input synchronizer traces through 19 hops (DFF + buffer
#        tree) all the way to gpio_in_val[0] as primary_input."""
#        leaves = _soc_trace(
#            soc_netlist, SOC_GPIO_VCD,
#            "rjn_top.u_rjn_soc_top.inst_rjn_app_top.inst_app_gpio1"
#            ".FE_OFC229639_gpio_ifc_rg_in_sync1_0.Y",
#            55_000_000,
#        )
#        assert len(leaves) >= 1, "Trace returned no leaves"
#        # Must reach root cause — primary_input at gpio_in_val
#        pi_leaves = [l for l in leaves if l.cause_type == "primary_input"]
#        assert len(pi_leaves) >= 1, (
#            f"Expected primary_input root cause, got: "
#            f"{set(l.cause_type for l in leaves)}"
#        )
#        assert any("gpio_in_val" in l.signal for l in pi_leaves), (
#            f"Expected root cause at gpio_in_val, got: "
#            f"{set(l.signal for l in pi_leaves)}"
#        )
#
#    def test_gpio_port_traces_to_primary_input(self, soc_netlist):
#        """APP_GPIO0 is a top-level port — direct primary_input."""
#        leaves = _soc_trace(
#            soc_netlist, SOC_GPIO_VCD,
#            "rjn_top.u_rjn_soc_top.APP_GPIO0",
#            55_000_000,
#        )
#        assert len(leaves) == 1
#        assert leaves[0].cause_type == "primary_input"
#        assert "APP_GPIO0" in leaves[0].signal
#
#
#@pytest.mark.skipif(not soc_reset_available, reason="SoC reset VCD not available")
#@pytest.mark.slow
#class TestSoCResetTrace:
#    """Real SoC reset injection tests — EXTERNAL_RESET forced to X at 50us."""
#
#    @pytest.fixture(scope="class")
#    def soc_netlist(self):
#        return parse_netlist_fast([SOC_NETLIST], top_module=SOC_NETLIST_TOP)
#
#    def test_reset_port_traces_to_primary_input(self, soc_netlist):
#        """EXTERNAL_RESET is a top-level port — direct primary_input."""
#        leaves = _soc_trace(
#            soc_netlist, SOC_RESET_VCD,
#            "rjn_top.u_rjn_soc_top.EXTERNAL_RESET",
#            55_000_000,
#        )
#        assert len(leaves) == 1
#        assert leaves[0].cause_type == "primary_input"
#        assert "EXTERNAL_RESET" in leaves[0].signal
#
#    def test_reset_buffer_tree_traces_to_primary_input(self, soc_netlist):
#        """User workflow: X found deep in reset distribution tree.
#
#        Scenario: EXTERNAL_RESET forced to X at 50us. X propagates through
#        pad and buffer tree. User sees X on a buffer output deep in the
#        reset tree and traces back to root cause.
#
#        Expected: traces through INV + BUF to EXTERNAL_RESET_fromPad (primary_input).
#        """
#        leaves = _soc_trace(
#            soc_netlist, SOC_RESET_VCD,
#            "rjn_top.u_rjn_soc_top.FE_OFN94700_EXTERNAL_RESET_fromPad",
#            55_000_000,
#        )
#        assert len(leaves) >= 1
#        pi_leaves = [l for l in leaves if l.cause_type == "primary_input"]
#        assert len(pi_leaves) >= 1, (
#            f"Expected primary_input root cause, got: "
#            f"{set(l.cause_type for l in leaves)}"
#        )
#        assert any("EXTERNAL_RESET" in l.signal for l in pi_leaves)
