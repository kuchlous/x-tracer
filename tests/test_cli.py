"""Integration tests for the X-Tracer CLI."""

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
CASES_DIR = _PROJECT_ROOT / "tests" / "cases" / "synthetic"
X_TRACER = [sys.executable, str(_PROJECT_ROOT / "x_tracer.py")]


def _run_cli(*args, expect_rc=0) -> subprocess.CompletedProcess:
    """Run the CLI and return the result."""
    result = subprocess.run(
        X_TRACER + list(args),
        capture_output=True, text=True,
        cwd=str(_PROJECT_ROOT),
    )
    if expect_rc is not None:
        assert result.returncode == expect_rc, (
            f"Expected rc={expect_rc}, got {result.returncode}\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return result


def _case_args(case_dir: Path, manifest: dict, fmt: str = "text") -> list[str]:
    """Build CLI arguments from a test case manifest."""
    query = manifest["query"]
    return [
        "--netlist", str(case_dir / "netlist.v"),
        "--netlist", str(case_dir / "tb.v"),
        "--vcd", str(case_dir / "sim.vcd"),
        "--signal", query["signal"],
        "--time", str(query["time"]),
        "--format", fmt,
    ]


def _load_manifest(case_dir: Path) -> dict:
    return json.loads((case_dir / "manifest.json").read_text())


# --- Test 1: text format on simple gate case ---

class TestTextFormat:
    def test_simple_gate_text(self):
        case_dir = CASES_DIR / "gates" / "synth_s1_not_1in_xmask1_na"
        manifest = _load_manifest(case_dir)
        result = _run_cli(*_case_args(case_dir, manifest, "text"))
        assert "[" in result.stdout  # has cause_type brackets
        assert "tb.dut" in result.stdout
        assert "t=" in result.stdout


# --- Test 2: json format ---

class TestJsonFormat:
    def test_json_output(self):
        case_dir = CASES_DIR / "gates" / "synth_s1_not_1in_xmask1_na"
        manifest = _load_manifest(case_dir)
        result = _run_cli(*_case_args(case_dir, manifest, "json"))
        data = json.loads(result.stdout)
        assert "signal" in data
        assert "time" in data
        assert "cause_type" in data
        assert "children" in data

    def test_json_has_correct_query(self):
        case_dir = CASES_DIR / "gates" / "synth_s1_and_2in_xmask10_0"
        manifest = _load_manifest(case_dir)
        result = _run_cli(*_case_args(case_dir, manifest, "json"))
        data = json.loads(result.stdout)
        assert data["time"] == manifest["query"]["time"]


# --- Test 3: dot format ---

class TestDotFormat:
    def test_dot_output(self):
        case_dir = CASES_DIR / "gates" / "synth_s1_not_1in_xmask1_na"
        manifest = _load_manifest(case_dir)
        result = _run_cli(*_case_args(case_dir, manifest, "dot"))
        assert "digraph" in result.stdout
        assert "->" in result.stdout or "n0" in result.stdout


# --- Test 4: signal not X ---

class TestErrorCases:
    def test_signal_not_x(self):
        case_dir = CASES_DIR / "gates" / "synth_s1_and_2in_xmask01_0"
        manifest = _load_manifest(case_dir)
        # Query at time 0, when signal should not be X
        result = _run_cli(
            "--netlist", str(case_dir / "netlist.v"),
            "--netlist", str(case_dir / "tb.v"),
            "--vcd", str(case_dir / "sim.vcd"),
            "--signal", manifest["query"]["signal"],
            "--time", "0",
            expect_rc=1,
        )
        assert "not X" in result.stderr or "value=" in result.stderr

    # --- Test 5: signal not found ---
    def test_signal_not_found(self):
        case_dir = CASES_DIR / "gates" / "synth_s1_not_1in_xmask1_na"
        manifest = _load_manifest(case_dir)
        result = _run_cli(
            "--netlist", str(case_dir / "netlist.v"),
            "--netlist", str(case_dir / "tb.v"),
            "--vcd", str(case_dir / "sim.vcd"),
            "--signal", "nonexistent.signal",
            "--time", "30000",
            expect_rc=1,
        )
        assert "not found" in result.stderr


# --- Test 6: multiple netlist files ---

class TestMultipleNetlists:
    def test_two_netlist_files(self):
        case_dir = CASES_DIR / "gates" / "synth_s1_not_1in_xmask1_na"
        manifest = _load_manifest(case_dir)
        # Pass both netlist.v and tb.v as separate --netlist args
        result = _run_cli(*_case_args(case_dir, manifest, "text"))
        assert result.returncode == 0
        assert "tb.dut" in result.stdout


# --- Test 7: structural case (reconverge or bus_encoder) ---

class TestStructural:
    def test_bus_encoder(self):
        case_dir = CASES_DIR / "structural" / "bus_encoder_w4"
        manifest = _load_manifest(case_dir)
        result = _run_cli(*_case_args(case_dir, manifest, "text"))
        inj_target = manifest["expected"]["injection_target"]
        assert inj_target in result.stdout

    def test_reconverge(self):
        case_dir = CASES_DIR / "structural" / "reconverge_d2"
        manifest = _load_manifest(case_dir)
        result = _run_cli(*_case_args(case_dir, manifest, "json"))
        data = json.loads(result.stdout)
        assert data["cause_type"] in (
            "x_propagation", "primary_input", "x_injection",
            "unknown_cell",
        )


# --- Test 8: multibit case (bit_slice) ---

class TestMultibit:
    def test_bit_slice(self):
        case_dir = CASES_DIR / "multibit" / "bit_slice_w16_b0_select"
        manifest = _load_manifest(case_dir)
        result = _run_cli(*_case_args(case_dir, manifest, "text"))
        assert result.returncode == 0


# --- Test 9: bulk test across categories ---

def _collect_bulk_cases():
    """Collect 10+ cases across all categories."""
    cases = []
    # Gates (first 5)
    gates_dir = CASES_DIR / "gates"
    if gates_dir.exists():
        for d in sorted(gates_dir.iterdir())[:5]:
            cases.append(d)
    # Structural (3)
    struct_dir = CASES_DIR / "structural"
    if struct_dir.exists():
        for name in ["bus_encoder_w4", "reconverge_d2", "reconverge_d4"]:
            d = struct_dir / name
            if d.exists():
                cases.append(d)
    # Multibit (3 parseable ones)
    multi_dir = CASES_DIR / "multibit"
    if multi_dir.exists():
        for name in ["bit_slice_w16_b0_select", "partial_bus_and_w4", "partial_bus_or_w4"]:
            d = multi_dir / name
            if d.exists():
                cases.append(d)
    return cases


_BULK_CASES = _collect_bulk_cases()


class TestBulk:
    @pytest.mark.parametrize("case_dir", _BULK_CASES,
                             ids=[c.name for c in _BULK_CASES])
    def test_cli_exit_0_and_injection_in_output(self, case_dir):
        manifest = _load_manifest(case_dir)
        result = _run_cli(*_case_args(case_dir, manifest, "text"))
        inj_target = manifest["expected"]["injection_target"]
        # Parse expected injection signal
        m = re.match(r'^(.+)\[(\d+)\]$', inj_target)
        if m:
            inj_sig = m.group(1)
        else:
            inj_sig = inj_target
        assert inj_sig in result.stdout, (
            f"Injection target signal '{inj_sig}' not found in output:\n{result.stdout}"
        )
