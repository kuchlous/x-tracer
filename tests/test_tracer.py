"""Tests for X-Tracer — all tests invoke the CLI (x_tracer.py) as a subprocess."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

CASES_DIR = Path(__file__).resolve().parent / "cases" / "synthetic"
STRESS_DIR = Path(__file__).resolve().parent / "cases" / "stress"
STRESS_EDGE_DIR = Path(__file__).resolve().parent / "cases" / "stress_edge"
LOG_DIR = Path(__file__).resolve().parent / "logs"
X_TRACER = Path(__file__).resolve().parent.parent / "x_tracer.py"


# ---------------------------------------------------------------------------
# Shared CLI helpers
# ---------------------------------------------------------------------------

def _run_cli(netlist_files, vcd_path, signal, time_ps, max_depth=100,
             extra_args=None, expect_fail=False):
    """Run x_tracer.py as a subprocess and return parsed JSON cause tree.

    Always logs command, stderr, and stdout to tests/logs/<test_name>.log.
    With pytest -v, prints the CLI command to stderr.
    """
    cmd = [sys.executable, str(X_TRACER)]
    for nf in netlist_files:
        cmd += ["-n", str(nf)]
    cmd += [
        "-v", str(vcd_path),
        "-s", signal,
        "-t", str(time_ps),
        "--max-depth", str(max_depth),
        "-f", "json",
    ]
    if extra_args:
        cmd += extra_args

    verbose = "-v" in sys.argv or "--verbose" in sys.argv
    if verbose:
        cmd_str = " \\\n    ".join(cmd)
        print(f"\n  Running:\n    {cmd_str}\n", file=sys.stderr)

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

    # Always log output
    LOG_DIR.mkdir(exist_ok=True)
    test_name = os.environ.get(
        "PYTEST_CURRENT_TEST", "unknown"
    ).split("::")[-1].split(" ")[0]
    log_path = LOG_DIR / f"{test_name}.log"
    log_content = f"=== COMMAND ===\n{' '.join(cmd)}\n\n"
    log_content += f"=== STDERR ===\n{result.stderr}\n\n"
    log_content += f"=== STDOUT ===\n{result.stdout}\n"
    log_path.write_text(log_content)
    if verbose:
        print(f"  Log written to: {log_path}", file=sys.stderr)

    if expect_fail:
        return result

    assert result.returncode == 0, (
        f"x_tracer.py failed (exit {result.returncode}):\n{result.stderr}"
    )

    tree = json.loads(result.stdout)
    return tree


def _collect_leaves(node):
    """Recursively collect leaf nodes from JSON cause tree."""
    if not node.get("children"):
        return [node]
    leaves = []
    for child in node["children"]:
        leaves.extend(_collect_leaves(child))
    return leaves


def _run_case(case_dir, max_depth=100, extra_args=None):
    """Run CLI on a test case directory and return (tree, leaves, manifest)."""
    manifest = json.loads((case_dir / "manifest.json").read_text())
    signal = manifest["query"]["signal"]
    time_ps = manifest["query"]["time"]
    netlist_files = [case_dir / "netlist.v", case_dir / "tb.v"]

    tree = _run_cli(netlist_files, case_dir / "sim.vcd", signal, time_ps,
                    max_depth=max_depth, extra_args=extra_args)
    leaves = _collect_leaves(tree)
    return tree, leaves, manifest


def _verify_injection_target(leaves, manifest):
    """Check if the injection target appears in the cause tree leaves.

    Accepts both wire paths (tb.dut.q0) and port paths (tb.dut.ff0.Q)
    as equivalent, since the tracer may report either form.
    """
    inj_target = manifest["expected"]["injection_target"]
    m = re.match(r'^(.+)\[(\d+)\]$', inj_target)
    if m:
        inj_sig, inj_bit = m.group(1), int(m.group(2))
    else:
        inj_sig, inj_bit = inj_target, 0
    inj_key = f"{inj_sig}[{inj_bit}]"

    leaf_signals = {l["signal"] for l in leaves}
    if inj_key in leaf_signals:
        return True

    # Port-path alias: check if injection target's instance matches a leaf's gate
    for leaf in leaves:
        gate = leaf.get("gate")
        if gate is not None:
            inst_path = gate.get("instance_path", "")
            # Check if the injection target's instance matches
            inj_inst = inj_sig.rsplit('.', 1)[0] if '.' in inj_sig else ''
            if inst_path == inj_inst:
                return True
            # Check instance.port pattern
            for suffix in ["Y", "Q", "Z", "ZN"]:
                if f"{inst_path}.{suffix}[{inj_bit}]" == inj_key:
                    return True
    return False


# ---------------------------------------------------------------------------
# Individual targeted tests
# ---------------------------------------------------------------------------

class TestSingleGate:
    def test_and_gate_x_on_input(self):
        case_dir = CASES_DIR / "gates" / "synth_s1_and_2in_xmask01_0"
        tree, leaves, manifest = _run_case(case_dir)
        assert tree["cause_type"] == "primary_input"
        assert _verify_injection_target(leaves, manifest)

    def test_and_gate_x_propagation(self):
        case_dir = CASES_DIR / "gates" / "synth_s1_and_2in_xmask10_0"
        tree, leaves, manifest = _run_case(case_dir)
        assert _verify_injection_target(leaves, manifest)


class TestChainCases:
    def test_bus_encoder(self):
        case_dir = CASES_DIR / "structural" / "bus_encoder_w4"
        tree, leaves, manifest = _run_case(case_dir)
        assert _verify_injection_target(leaves, manifest)

    def test_reconverge(self):
        case_dir = CASES_DIR / "structural" / "reconverge_d2"
        tree, leaves, manifest = _run_case(case_dir)
        assert _verify_injection_target(leaves, manifest)


class TestMultibit:
    def test_bit_slice_select(self):
        case_dir = CASES_DIR / "multibit" / "bit_slice_w16_b0_select"
        tree, leaves, manifest = _run_case(case_dir)
        assert _verify_injection_target(leaves, manifest)

    def test_bit_slice_part_select(self):
        case_dir = CASES_DIR / "multibit" / "bit_slice_w16_b0_part_select"
        tree, leaves, manifest = _run_case(case_dir)
        assert _verify_injection_target(leaves, manifest)

    def test_partial_bus_and(self):
        case_dir = CASES_DIR / "multibit" / "partial_bus_and_w4"
        tree, leaves, manifest = _run_case(case_dir)
        assert _verify_injection_target(leaves, manifest)

    def test_partial_bus_or(self):
        case_dir = CASES_DIR / "multibit" / "partial_bus_or_w4"
        tree, leaves, manifest = _run_case(case_dir)
        assert _verify_injection_target(leaves, manifest)


class TestEdgeCases:
    def test_max_depth_cutoff(self):
        case_dir = CASES_DIR / "structural" / "reconverge_d2"
        tree, leaves, manifest = _run_case(case_dir, max_depth=1)
        types = {l["cause_type"] for l in leaves}
        assert "max_depth" in types or "primary_input" in types

    def test_signal_not_x_fails(self):
        """CLI should exit non-zero when signal is not X."""
        case_dir = CASES_DIR / "gates" / "synth_s1_and_2in_xmask01_0"
        manifest = json.loads((case_dir / "manifest.json").read_text())
        result = _run_cli(
            [case_dir / "netlist.v", case_dir / "tb.v"],
            case_dir / "sim.vcd",
            "tb.dut.a[0]", 30000,
            expect_fail=True,
        )
        assert result.returncode != 0
        assert "not X" in result.stderr or "not 'x'" in result.stderr


# ---------------------------------------------------------------------------
# Bulk tests
# ---------------------------------------------------------------------------

class TestBulk:
    @pytest.mark.parametrize("case_name", [
        d.name for d in sorted((CASES_DIR / "gates").iterdir())
        if (d / "manifest.json").exists()
    ] if (CASES_DIR / "gates").exists() else [])
    def test_gates_bulk(self, case_name):
        case_dir = CASES_DIR / "gates" / case_name
        tree, leaves, manifest = _run_case(case_dir)
        assert _verify_injection_target(leaves, manifest), (
            f"Injection target {manifest['expected']['injection_target']} "
            f"not in leaves: {set(l['signal'] for l in leaves)}"
        )

    @pytest.mark.parametrize("case_name", [
        d.name for d in sorted((CASES_DIR / "multibit").iterdir())
        if (d / "manifest.json").exists()
    ] if (CASES_DIR / "multibit").exists() else [])
    def test_multibit_bulk(self, case_name):
        case_dir = CASES_DIR / "multibit" / case_name
        tree, leaves, manifest = _run_case(case_dir)
        assert _verify_injection_target(leaves, manifest), (
            f"Injection target {manifest['expected']['injection_target']} "
            f"not in leaves: {set(l['signal'] for l in leaves)}"
        )

    @pytest.mark.parametrize("case_name", [
        d.name for d in sorted((CASES_DIR / "structural").iterdir())
        if (d / "manifest.json").exists()
    ] if (CASES_DIR / "structural").exists() else [])
    def test_structural_gate_level(self, case_name):
        case_dir = CASES_DIR / "structural" / case_name
        tree, leaves, manifest = _run_case(case_dir)
        assert _verify_injection_target(leaves, manifest), (
            f"Injection target {manifest['expected']['injection_target']} "
            f"not in leaves: {set(l['signal'] for l in leaves)}"
        )


# ---------------------------------------------------------------------------
# Stress tests
# ---------------------------------------------------------------------------

class TestStress:
    def test_lfsr_grid_trace_all_leaves_primary_input(self):
        """Stress: 2x2x2x2x8 LFSR grid -- all leaves must be primary_input."""
        case_dir = STRESS_DIR
        if not (case_dir / "sim.vcd").exists():
            pytest.skip("sim.vcd not available — run xrun to generate")
        tree, leaves, manifest = _run_case(
            case_dir, max_depth=500, extra_args=["--fast-parser"],
        )
        assert len(leaves) > 0, "Trace returned no leaves"
        leaf_types = {l["cause_type"] for l in leaves}
        assert leaf_types == {"primary_input"}, (
            f"Expected all leaves to be primary_input, got: {leaf_types}"
        )
        inj_target = manifest["expected"]["injection_target"]
        m = re.match(r'^(.+)\[(\d+)\]$', inj_target)
        exp_key = f"{m.group(1)}[{m.group(2)}]" if m else f"{inj_target}[0]"
        leaf_sigs = {l["signal"] for l in leaves}
        assert leaf_sigs == {exp_key}, (
            f"Expected all leaves to be {exp_key}, got: {leaf_sigs}"
        )

    # --- Stress edge cases ---

    def _run_stress_edge(self, name, max_depth=500):
        """Run CLI on a stress_edge test case, return leaves."""
        case_dir = STRESS_EDGE_DIR / name
        manifest = json.loads((case_dir / "manifest.json").read_text())
        signal = manifest["query"]["signal"]
        time_ps = manifest["query"]["time"]
        tree = _run_cli(
            [case_dir / "netlist.v", case_dir / "tb.v"],
            case_dir / "sim.vcd",
            signal, time_ps,
            max_depth=max_depth,
        )
        return _collect_leaves(tree)

    def test_deep_pipeline_traces_to_ff0(self):
        """Stress edge: 104-stage deep pipeline — trace reaches ff_q_0."""
        leaves = self._run_stress_edge("deep_pipeline")
        assert len(leaves) == 1, f"Expected 1 leaf, got {len(leaves)}"
        assert leaves[0]["signal"] == "tb.dut.ff_q_0[0]", (
            f"Expected root cause at ff_q_0, got {leaves[0]['signal']}"
        )

    def test_wide_fanout_traces_to_source_dff(self):
        """Stress edge: 32-way fanout reconverges — traces to src_q."""
        leaves = self._run_stress_edge("wide_fanout")
        assert len(leaves) == 32, f"Expected 32 leaves, got {len(leaves)}"
        src_leaves = [l for l in leaves if "src_q" in l["signal"]]
        assert len(src_leaves) >= 24, (
            f"Expected >=24 leaves at src_q, got {len(src_leaves)}"
        )

    def test_clock_crossing_traces_to_a_q0(self):
        """Stress edge: CDC — traces across clock boundary to a_q0."""
        leaves = self._run_stress_edge("clock_crossing")
        assert len(leaves) == 1, f"Expected 1 leaf, got {len(leaves)}"
        assert leaves[0]["signal"] == "tb.dut.a_q0[0]", (
            f"Expected root cause at a_q0, got {leaves[0]['signal']}"
        )

    def test_tristate_bus_identifies_driver(self):
        """Stress edge: tri-state bus — trace reaches bus x_injection."""
        leaves = self._run_stress_edge("tristate_bus")
        assert len(leaves) >= 1
        leaf_types = {l["cause_type"] for l in leaves}
        assert "x_injection" in leaf_types or "uninit_ff" in leaf_types

    def test_nested_clock_gate_traces_to_primary_input(self):
        """Stress edge: nested ICG — traces to gated clock as primary_input."""
        leaves = self._run_stress_edge("nested_clock_gate")
        assert len(leaves) == 2, f"Expected 2 leaves, got {len(leaves)}"
        leaf_sigs = {l["signal"] for l in leaves}
        assert "tb.dut.gclk_l3[0]" in leaf_sigs or "tb.dut.qa[0]" in leaf_sigs

    def test_x_window_gap_traces_to_src_b_not_src_a(self):
        """Stress edge: X window gap — D goes X(src_a)->known->X(src_b).

        The temporal skip must trace to src_b (the current X window's cause),
        not src_a (the first-ever X on D).  Regression test for the
        find_x_start vs first_x_time correctness fix.
        """
        leaves = self._run_stress_edge("x_window_gap")
        assert len(leaves) == 1, f"Expected 1 leaf, got {len(leaves)}"
        assert leaves[0]["cause_type"] == "primary_input"
        assert leaves[0]["signal"] == "tb.dut.src_b[0]", (
            f"Expected root cause at src_b (current X window), "
            f"got {leaves[0]['signal']} — temporal skip may have jumped "
            f"to first-ever X instead of current X window"
        )


# ---------------------------------------------------------------------------
# SoC integration tests
# ---------------------------------------------------------------------------

SOC_NETLIST = Path("/Backend_share/pd_dv_1p1/Dec_26_Flat_SDF/rjn_soc_top.Fill_uniquify.v")
SOC_GPIO_VCD = Path("/data/work_area/alokk/x-tracer/proj/verif/run/run_log/rjn_a55_uart1_test1/rjn_a55_uart1_test.vcd")
SOC_RESET_VCD = Path("/data/work_area/alokk/x-tracer/proj/verif/run/run_log/reset_x_test2/reset_x.vcd")
SOC_VCD_PREFIX = "rjn_top.u_rjn_soc_top"
SOC_NETLIST_TOP = "rjn_soc_top"

soc_gpio_available = SOC_NETLIST.exists() and SOC_GPIO_VCD.exists()
soc_reset_available = SOC_NETLIST.exists() and SOC_RESET_VCD.exists()


def _soc_trace(vcd_path, query_signal, query_time_ps, max_depth=50):
    """Run x_tracer.py on the SoC netlist and return parsed leaf nodes."""
    tree = _run_cli(
        [SOC_NETLIST], vcd_path,
        f"{query_signal}[0]", query_time_ps,
        max_depth=max_depth,
        extra_args=[
            "--top-module", SOC_NETLIST_TOP,
            "--vcd-prefix", SOC_VCD_PREFIX,
            "--fast-parser",
        ],
    )
    return _collect_leaves(tree)


@pytest.mark.skipif(not soc_gpio_available, reason="SoC GPIO VCD not available")
@pytest.mark.slow
class TestSoCGPIOTrace:
    """Real SoC GPIO injection tests."""

    def test_gpio_sync_register_traces_to_primary_input(self):
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
    """Real SoC reset injection tests."""

    def test_reset_port_traces_to_primary_input(self):
        leaves = _soc_trace(
            SOC_RESET_VCD,
            "rjn_top.u_rjn_soc_top.EXTERNAL_RESET",
            55_000_000,
        )
        assert len(leaves) == 1
        assert leaves[0]["cause_type"] == "primary_input"
        assert "EXTERNAL_RESET" in leaves[0]["signal"]

    def test_reset_buffer_tree_traces_to_primary_input(self):
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
