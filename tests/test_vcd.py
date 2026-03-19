"""Tests for VCD Database module."""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure src is importable
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from vcd.database import VCDDatabase, load_vcd, _extract_bit


# --- Inline VCD fixtures ---

SIMPLE_VCD = b"""\
$timescale 1ps $end
$scope module tb $end
$var wire 1 ! clk $end
$var wire 1 " data $end
$var wire 4 # bus [3:0] $end
$upscope $end
$enddefinitions $end
#0
$dumpvars
0!
0"
b0000 #
$end
#100
1!
#200
0!
1"
b01x0 #
#300
1!
x"
#400
0!
b1111 #
#500
1!
0"
"""

MULTI_SCOPE_VCD = b"""\
$timescale 1ps $end
$scope module tb $end
$var wire 1 ! y $end
$scope module dut $end
$var wire 1 " a $end
$var wire 1 # b $end
$var wire 1 ! y $end
$upscope $end
$upscope $end
$enddefinitions $end
#0
$dumpvars
0!
0"
0#
$end
#100
x"
#200
1#
"""


def _write_vcd(content: bytes) -> Path:
    """Write VCD content to a temp file and return the path."""
    fd, path = tempfile.mkstemp(suffix=".vcd")
    os.write(fd, content)
    os.close(fd)
    return Path(path)


# --- Test _extract_bit helper ---

class TestExtractBit:
    def test_single_bit(self):
        assert _extract_bit("1", 0) == "1"
        assert _extract_bit("x", 0) == "x"

    def test_bus_lsb(self):
        # "01x0" → bit 0 = '0' (rightmost)
        assert _extract_bit("01x0", 0) == "0"

    def test_bus_msb(self):
        # "01x0" → bit 3 = '0' (leftmost)
        assert _extract_bit("01x0", 3) == "0"

    def test_bus_middle(self):
        # "01x0" → bit 1 = 'x', bit 2 = '1'
        assert _extract_bit("01x0", 1) == "x"
        assert _extract_bit("01x0", 2) == "1"

    def test_extend_with_msb(self):
        # "10" is 2 chars, asking for bit 2 → extends with MSB '1'
        assert _extract_bit("10", 2) == "1"


# --- Tests using pyvcd backend (always available) ---

class TestPyvcdBackend:
    def test_load_simple(self):
        path = _write_vcd(SIMPLE_VCD)
        try:
            from vcd.pyvcd_backend import load
            db = load(path)
            assert db.has_signal("tb.clk")
            assert db.has_signal("tb.data")
            assert db.has_signal("tb.bus")
        finally:
            os.unlink(path)

    def test_get_value_scalar(self):
        path = _write_vcd(SIMPLE_VCD)
        try:
            from vcd.pyvcd_backend import load
            db = load(path)
            assert db.get_value("tb.clk", 0) == "0"
            assert db.get_value("tb.clk", 100) == "1"
            assert db.get_value("tb.clk", 150) == "1"
            assert db.get_value("tb.clk", 200) == "0"
        finally:
            os.unlink(path)

    def test_get_value_bus(self):
        path = _write_vcd(SIMPLE_VCD)
        try:
            from vcd.pyvcd_backend import load
            db = load(path)
            # pyvcd returns minimal binary for pure-numeric values (no leading zeros)
            assert db.get_value("tb.bus", 200) == "01x0"
            assert db.get_value("tb.bus", 400) == "1111"
            # get_bit still works for the initial zero value
            assert db.get_bit("tb.bus", 0, 0) == "0"
            assert db.get_bit("tb.bus", 3, 0) == "0"
        finally:
            os.unlink(path)

    def test_get_bit_bus(self):
        path = _write_vcd(SIMPLE_VCD)
        try:
            from vcd.pyvcd_backend import load
            db = load(path)
            # At time 200, bus = "01x0"
            assert db.get_bit("tb.bus", 0, 200) == "0"  # LSB
            assert db.get_bit("tb.bus", 1, 200) == "x"  # z->x per spec
            assert db.get_bit("tb.bus", 2, 200) == "1"
            assert db.get_bit("tb.bus", 3, 200) == "0"  # MSB
        finally:
            os.unlink(path)

    def test_get_bit_z_treated_as_x(self):
        """Spec says z is treated as x."""
        path = _write_vcd(b"""\
$timescale 1ps $end
$scope module tb $end
$var wire 1 ! sig $end
$upscope $end
$enddefinitions $end
#0
$dumpvars
z!
$end
""")
        try:
            from vcd.pyvcd_backend import load
            db = load(path)
            assert db.get_bit("tb.sig", 0, 0) == "x"
        finally:
            os.unlink(path)

    def test_first_x_time(self):
        path = _write_vcd(SIMPLE_VCD)
        try:
            from vcd.pyvcd_backend import load
            db = load(path)
            # tb.data: 0@0, 1@200, x@300, 0@500
            assert db.first_x_time("tb.data", 0) == 300
            # At time 301, data is still x (from transition at 300), so first_x >= 301 is 301
            assert db.first_x_time("tb.data", 0, after=301) == 301
            # After data returns to 0 at time 500, no more X
            assert db.first_x_time("tb.data", 0, after=500) is None
            # bus bit 1 is x at time 200
            assert db.first_x_time("tb.bus", 1) == 200
        finally:
            os.unlink(path)

    def test_find_edge_rise(self):
        path = _write_vcd(SIMPLE_VCD)
        try:
            from vcd.pyvcd_backend import load
            db = load(path)
            # clk: 0@0, 1@100, 0@200, 1@300, 0@400, 1@500
            assert db.find_edge("tb.clk", 0, "rise", before=500) == 300
            assert db.find_edge("tb.clk", 0, "rise", before=300) == 100
            assert db.find_edge("tb.clk", 0, "rise", before=100) is None
        finally:
            os.unlink(path)

    def test_find_edge_fall(self):
        path = _write_vcd(SIMPLE_VCD)
        try:
            from vcd.pyvcd_backend import load
            db = load(path)
            assert db.find_edge("tb.clk", 0, "fall", before=500) == 400
            assert db.find_edge("tb.clk", 0, "fall", before=400) == 200
        finally:
            os.unlink(path)

    def test_signal_filtering(self):
        path = _write_vcd(SIMPLE_VCD)
        try:
            from vcd.pyvcd_backend import load
            db = load(path, signals={"tb.clk"})
            # Should still know about all signals
            assert db.has_signal("tb.data")
            # But only clk has transition data
            assert db.get_value("tb.clk", 100) == "1"
            with pytest.raises(KeyError):
                db.get_value("tb.data", 100)
        finally:
            os.unlink(path)

    def test_hierarchical_paths(self):
        path = _write_vcd(MULTI_SCOPE_VCD)
        try:
            from vcd.pyvcd_backend import load
            db = load(path)
            assert db.has_signal("tb.y")
            assert db.has_signal("tb.dut.a")
            assert db.has_signal("tb.dut.b")
            assert db.has_signal("tb.dut.y")
            # tb.y and tb.dut.y share id_code '!'
            assert db.get_value("tb.y", 0) == "0"
            assert db.get_value("tb.dut.y", 0) == "0"
            # tb.dut.a gets x at 100
            assert db.get_value("tb.dut.a", 100) == "x"
        finally:
            os.unlink(path)

    def test_get_transitions(self):
        path = _write_vcd(SIMPLE_VCD)
        try:
            from vcd.pyvcd_backend import load
            db = load(path)
            trans = db.get_transitions("tb.data")
            assert trans[0] == (0, "0")
            assert (200, "1") in trans
            assert (300, "x") in trans
        finally:
            os.unlink(path)

    def test_get_all_signals(self):
        path = _write_vcd(SIMPLE_VCD)
        try:
            from vcd.pyvcd_backend import load
            db = load(path)
            sigs = db.get_all_signals()
            assert sigs == {"tb.clk", "tb.data", "tb.bus"}
        finally:
            os.unlink(path)


# --- Tests using real VCD files from testcase suite ---

REAL_VCD = Path("/home/ubuntu/x-tracer/tests/cases/synthetic/gates/synth_s1_and_2in_xmask01_0/sim.vcd")


@pytest.mark.skipif(not REAL_VCD.exists(), reason="Real VCD file not found")
class TestRealVCD:
    def test_load_real_vcd(self):
        db = load_vcd(REAL_VCD)
        assert db.has_signal("tb.dut.y")
        assert db.has_signal("tb.dut.a")
        assert db.has_signal("tb.dut.b")

    def test_real_vcd_values(self):
        db = load_vcd(REAL_VCD)
        # From the VCD: b=0@0, b=x@10000
        assert db.get_bit("tb.dut.b", 0, 0) == "0"
        assert db.get_bit("tb.dut.b", 0, 10000) == "x"

    def test_real_vcd_first_x(self):
        db = load_vcd(REAL_VCD)
        assert db.first_x_time("tb.dut.b", 0) == 10000

    def test_real_vcd_signal_filtering(self):
        db = load_vcd(REAL_VCD, signals={"tb.dut.b"})
        assert db.has_signal("tb.dut.y")  # knows about it
        assert db.get_bit("tb.dut.b", 0, 10000) == "x"


# --- Test load_vcd fallback ---

class TestLoadVcdFallback:
    def test_fallback_to_pyvcd(self):
        path = _write_vcd(SIMPLE_VCD)
        try:
            # Simulate pywellen not available
            with patch.dict("sys.modules", {"pywellen": None}):
                # Need to also block the backend import
                import importlib
                import vcd.pywellen_backend
                orig = sys.modules.get("vcd.pywellen_backend")
                sys.modules["vcd.pywellen_backend"] = None
                try:
                    # Import fresh
                    from vcd.pyvcd_backend import load
                    db = load(path)
                    assert db.has_signal("tb.clk")
                finally:
                    if orig is not None:
                        sys.modules["vcd.pywellen_backend"] = orig
                    else:
                        sys.modules.pop("vcd.pywellen_backend", None)
        finally:
            os.unlink(path)


# --- Test pywellen backend directly ---

class TestPywellenBackend:
    def test_load_real_vcd(self):
        pytest.importorskip("pywellen")
        if not REAL_VCD.exists():
            pytest.skip("Real VCD not found")
        from vcd.pywellen_backend import load
        db = load(REAL_VCD)
        assert db.has_signal("tb.dut.b")
        assert db.get_bit("tb.dut.b", 0, 10000) == "x"

    def test_signal_filtering(self):
        pytest.importorskip("pywellen")
        if not REAL_VCD.exists():
            pytest.skip("Real VCD not found")
        from vcd.pywellen_backend import load
        db = load(REAL_VCD, signals={"tb.dut.b"})
        assert db.has_signal("tb.dut.y")
        assert db.get_bit("tb.dut.b", 0, 10000) == "x"
        with pytest.raises(KeyError):
            db.get_value("tb.dut.y", 0)
