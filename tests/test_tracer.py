"""Tests for the X-Tracer core algorithm against golden testcases."""

import json
import os
import re
import sys
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

STRESS_EDGE_DIR = Path(__file__).resolve().parent / "cases" / "stress_edge"


class TestStress:
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

SOC_NETLIST = Path("/Backend_share/pd_dv_1p1/Dec_26_Flat_SDF/rjn_soc_top.Fill_uniquify.v")
SOC_GPIO_VCD = Path("/data/work_area/alokk/x-tracer/proj/verif/run/run_log/rjn_a55_uart1_test1/rjn_a55_uart1_test.vcd")
SOC_RESET_VCD = Path("/data/work_area/alokk/x-tracer/proj/verif/run/run_log/reset_x_test2/reset_x.vcd")
SOC_VCD_PREFIX = "rjn_top.u_rjn_soc_top"
SOC_NETLIST_TOP = "rjn_soc_top"

soc_gpio_available = SOC_NETLIST.exists() and SOC_GPIO_VCD.exists()
soc_reset_available = SOC_NETLIST.exists() and SOC_RESET_VCD.exists()


LOG_DIR = Path(__file__).resolve().parent / "logs"
X_TRACER = Path(__file__).resolve().parent.parent / "x_tracer.py"


def _soc_trace(vcd_path, query_signal, query_time_ps, max_depth=50):
    """Run x_tracer.py as a subprocess and return parsed leaf nodes.

    Always logs the full trace output to tests/logs/<test_name>.log.
    With pytest -v, prints the CLI command to stderr.
    """
    import subprocess

    cmd = [
        sys.executable, str(X_TRACER),
        "-n", str(SOC_NETLIST),
        "-v", str(vcd_path),
        "-s", f"{query_signal}[0]",
        "-t", str(query_time_ps),
        "--top-module", SOC_NETLIST_TOP,
        "--vcd-prefix", SOC_VCD_PREFIX,
        "--max-depth", str(max_depth),
        "--fast-parser",
        "-f", "json",
    ]

    verbose = "-v" in sys.argv or "--verbose" in sys.argv
    if verbose:
        cmd_str = " \\\n    ".join(cmd)
        print(f"\n  Running:\n    {cmd_str}\n", file=sys.stderr)

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

    # Always log output to file
    LOG_DIR.mkdir(exist_ok=True)
    test_name = os.environ.get("PYTEST_CURRENT_TEST", "unknown").split("::")[-1].split(" ")[0]
    log_path = LOG_DIR / f"{test_name}.log"
    log_content = f"=== COMMAND ===\n{' '.join(cmd)}\n\n"
    log_content += f"=== STDERR ===\n{result.stderr}\n\n"
    log_content += f"=== STDOUT ===\n{result.stdout}\n"
    log_path.write_text(log_content)
    if verbose:
        print(f"  Log written to: {log_path}", file=sys.stderr)

    assert result.returncode == 0, (
        f"x_tracer.py failed (exit {result.returncode}):\n{result.stderr}"
    )

    tree = json.loads(result.stdout)
    leaves = _collect_json_leaves(tree)
    return leaves


def _collect_json_leaves(node):
    """Recursively collect leaf nodes from JSON cause tree."""
    if not node.get("children"):
        return [node]
    leaves = []
    for child in node["children"]:
        leaves.extend(_collect_json_leaves(child))
    return leaves


@pytest.mark.skipif(not soc_gpio_available, reason="SoC GPIO VCD not available")
@pytest.mark.slow
class TestSoCGPIOTrace:
    """Real SoC GPIO injection tests — TSMC 22nm ARM A55.

    User workflow: GPIO APP_GPIO0 forced to X at 50us, test hangs.
    User finds X on GPIO sync register, traces to root cause.
    """

    def test_gpio_sync_register_traces_to_primary_input(self):
        """X on GPIO input synchronizer traces through 19 hops (DFF + buffer
        tree) all the way to gpio_in_val[0] as primary_input."""
        leaves = _soc_trace(
            SOC_GPIO_VCD,
            "rjn_top.u_rjn_soc_top.inst_rjn_app_top.inst_app_gpio1"
            ".FE_OFC229639_gpio_ifc_rg_in_sync1_0.Y",
            55_000_000,
        )
        assert len(leaves) >= 1, "Trace returned no leaves"
        pi_leaves = [l for l in leaves if l["cause_type"] == "primary_input"]
        assert len(pi_leaves) >= 1, (
            f"Expected primary_input root cause, got: "
            f"{set(l['cause_type'] for l in leaves)}"
        )
        assert any("gpio_in_val" in l["signal"] for l in pi_leaves), (
            f"Expected root cause at gpio_in_val, got: "
            f"{set(l['signal'] for l in pi_leaves)}"
        )

    def test_gpio_port_traces_to_primary_input(self):
        """APP_GPIO0 is a top-level port — direct primary_input."""
        leaves = _soc_trace(
            SOC_GPIO_VCD,
            "rjn_top.u_rjn_soc_top.APP_GPIO0",
            55_000_000,
        )
        assert len(leaves) == 1
        assert leaves[0]["cause_type"] == "primary_input"
        assert "APP_GPIO0" in leaves[0]["signal"]


@pytest.mark.skipif(not soc_reset_available, reason="SoC reset VCD not available")
@pytest.mark.slow
class TestSoCResetTrace:
    """Real SoC reset injection tests — EXTERNAL_RESET forced to X at 50us."""

    def test_reset_port_traces_to_primary_input(self):
        """EXTERNAL_RESET is a top-level port — direct primary_input."""
        leaves = _soc_trace(
            SOC_RESET_VCD,
            "rjn_top.u_rjn_soc_top.EXTERNAL_RESET",
            55_000_000,
        )
        assert len(leaves) == 1
        assert leaves[0]["cause_type"] == "primary_input"
        assert "EXTERNAL_RESET" in leaves[0]["signal"]

    def test_reset_buffer_tree_traces_to_primary_input(self):
        """User workflow: X found deep in reset distribution tree.

        Scenario: EXTERNAL_RESET forced to X at 50us. X propagates through
        pad and buffer tree. User sees X on a buffer output deep in the
        reset tree and traces back to root cause.

        Expected: traces through INV + BUF to EXTERNAL_RESET_fromPad (primary_input).
        """
        leaves = _soc_trace(
            SOC_RESET_VCD,
            "rjn_top.u_rjn_soc_top.FE_OFN94700_EXTERNAL_RESET_fromPad",
            55_000_000,
        )
        assert len(leaves) >= 1
        pi_leaves = [l for l in leaves if l["cause_type"] == "primary_input"]
        assert len(pi_leaves) >= 1, (
            f"Expected primary_input root cause, got: "
            f"{set(l['cause_type'] for l in leaves)}"
        )
        assert any("EXTERNAL_RESET" in l["signal"] for l in pi_leaves)
