"""Extended tests for VCD features: header parsing, line parser, timescale, PrefixMappedVCD."""

import os
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure src is importable
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from vcd.database import VCDDatabase, PrefixMappedVCD, _TS_UNITS
from vcd.pyvcd_backend import parse_vcd_header, _load_line_parser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_vcd(content: bytes) -> Path:
    """Write VCD content to a temp file and return the path."""
    fd, path = tempfile.mkstemp(suffix=".vcd")
    os.write(fd, content)
    os.close(fd)
    return Path(path)


# ---------------------------------------------------------------------------
# VCD templates
# ---------------------------------------------------------------------------

def _make_timescale_vcd(timescale_str: str) -> bytes:
    """Return a minimal VCD with the given timescale directive."""
    return f"""\
$timescale {timescale_str} $end
$scope module tb $end
$var wire 1 ! clk $end
$var wire 1 " data $end
$upscope $end
$enddefinitions $end
#0
0!
0"
#100
1!
""".encode()


CADENCE_VCD = b"""\
$timescale 1ps $end
$scope module tb $end
$scope module dut $end
$var wire 1 ! app_gpio0_ctrl[ds0_topad] $end
$var wire 1 " app_gpio0_ctrl[oe_topad] $end
$var wire 1 # normal_sig $end
$upscope $end
$upscope $end
$enddefinitions $end
#0
$dumpvars
0!
0"
0#
$end
#50
1!
#100
x"
1#
"""

TEN_SIGNAL_VCD = b"""\
$timescale 1ps $end
$scope module tb $end
$var wire 1 A sig0 $end
$var wire 1 B sig1 $end
$var wire 1 C sig2 $end
$var wire 1 D sig3 $end
$var wire 1 E sig4 $end
$var wire 1 F sig5 $end
$var wire 1 G sig6 $end
$var wire 1 H sig7 $end
$var wire 1 I sig8 $end
$var wire 1 J sig9 $end
$upscope $end
$enddefinitions $end
#0
$dumpvars
0A
0B
0C
0D
0E
0F
0G
0H
0I
0J
$end
#100
1A
1B
1C
1D
1E
1F
1G
1H
1I
1J
"""

BINARY_VALUES_VCD = b"""\
$timescale 1ps $end
$scope module tb $end
$var wire 1 ! scalar $end
$var wire 4 " bus [3:0] $end
$upscope $end
$enddefinitions $end
#0
$dumpvars
0!
b0000 "
$end
#10
1!
b0110 "
#20
x!
b1x0z "
#30
z!
b1111 "
"""

HIERARCHICAL_VCD = b"""\
$timescale 1ps $end
$scope module tb $end
$scope module dut $end
$var wire 1 ! sig1 $end
$var wire 1 " sig2 $end
$var wire 4 # bus [3:0] $end
$upscope $end
$upscope $end
$enddefinitions $end
#0
$dumpvars
0!
1"
b0000 #
$end
#100
1!
0"
b1010 #
"""


# ===========================================================================
# 1. TestParseVCDHeader
# ===========================================================================

class TestParseVCDHeader:
    """Test parse_vcd_header returns correct signal names and timescale."""

    def test_basic_header(self):
        path = _write_vcd(_make_timescale_vcd("1ps"))
        try:
            signals, ts_fs = parse_vcd_header(path)
            assert "tb.clk" in signals
            assert "tb.data" in signals
            assert len(signals) == 2
            assert ts_fs == 1000  # 1ps = 1000 fs
        finally:
            os.unlink(path)

    def test_timescale_1fs(self):
        path = _write_vcd(_make_timescale_vcd("1fs"))
        try:
            signals, ts_fs = parse_vcd_header(path)
            assert ts_fs == 1
            assert "tb.clk" in signals
        finally:
            os.unlink(path)

    def test_timescale_1ps(self):
        path = _write_vcd(_make_timescale_vcd("1ps"))
        try:
            _, ts_fs = parse_vcd_header(path)
            assert ts_fs == 1000
        finally:
            os.unlink(path)

    def test_timescale_1ns(self):
        path = _write_vcd(_make_timescale_vcd("1ns"))
        try:
            _, ts_fs = parse_vcd_header(path)
            assert ts_fs == 1_000_000
        finally:
            os.unlink(path)

    def test_hierarchical_signals(self):
        path = _write_vcd(HIERARCHICAL_VCD)
        try:
            signals, ts_fs = parse_vcd_header(path)
            assert "tb.dut.sig1" in signals
            assert "tb.dut.sig2" in signals
            assert "tb.dut.bus" in signals
            assert ts_fs == 1000
        finally:
            os.unlink(path)


# ===========================================================================
# 2. TestLineParserCadenceNames
# ===========================================================================

class TestLineParserCadenceNames:
    """Test that the line parser handles Cadence-style non-numeric bracket names."""

    def test_cadence_signal_names_parsed(self):
        path = _write_vcd(CADENCE_VCD)
        try:
            db = _load_line_parser(path)
            sigs = db.get_all_signals()
            assert "tb.dut.app_gpio0_ctrl[ds0_topad]" in sigs
            assert "tb.dut.app_gpio0_ctrl[oe_topad]" in sigs
            assert "tb.dut.normal_sig" in sigs
        finally:
            os.unlink(path)

    def test_cadence_signal_values(self):
        path = _write_vcd(CADENCE_VCD)
        try:
            db = _load_line_parser(path)
            # ds0_topad: 0@0, 1@50
            assert db.get_value("tb.dut.app_gpio0_ctrl[ds0_topad]", 0) == "0"
            assert db.get_value("tb.dut.app_gpio0_ctrl[ds0_topad]", 50) == "1"
            # oe_topad: 0@0, x@100
            assert db.get_value("tb.dut.app_gpio0_ctrl[oe_topad]", 100) == "x"
        finally:
            os.unlink(path)

    def test_cadence_header_parsing(self):
        path = _write_vcd(CADENCE_VCD)
        try:
            signals, ts_fs = parse_vcd_header(path)
            assert "tb.dut.app_gpio0_ctrl[ds0_topad]" in signals
            assert "tb.dut.app_gpio0_ctrl[oe_topad]" in signals
            assert ts_fs == 1000
        finally:
            os.unlink(path)


# ===========================================================================
# 3. TestLineParserTimescale
# ===========================================================================

class TestLineParserTimescale:
    """Verify timescale_fs is correctly extracted by the line parser."""

    def test_1fs(self):
        path = _write_vcd(_make_timescale_vcd("1fs"))
        try:
            db = _load_line_parser(path)
            assert db.timescale_fs == 1
        finally:
            os.unlink(path)

    def test_10ps(self):
        path = _write_vcd(_make_timescale_vcd("10ps"))
        try:
            db = _load_line_parser(path)
            assert db.timescale_fs == 10_000  # 10 * 1000
        finally:
            os.unlink(path)

    def test_1ns(self):
        path = _write_vcd(_make_timescale_vcd("1ns"))
        try:
            db = _load_line_parser(path)
            assert db.timescale_fs == 1_000_000
        finally:
            os.unlink(path)

    def test_1us(self):
        path = _write_vcd(_make_timescale_vcd("1us"))
        try:
            db = _load_line_parser(path)
            assert db.timescale_fs == 1_000_000_000
        finally:
            os.unlink(path)

    def test_multiline_timescale(self):
        """Test timescale that spans multiple lines."""
        vcd = b"""\
$timescale
    1ns
$end
$scope module tb $end
$var wire 1 ! clk $end
$upscope $end
$enddefinitions $end
#0
0!
"""
        path = _write_vcd(vcd)
        try:
            db = _load_line_parser(path)
            assert db.timescale_fs == 1_000_000
        finally:
            os.unlink(path)


# ===========================================================================
# 4. TestTimescaleConversion
# ===========================================================================

class TestTimescaleConversion:
    """Test ps_to_vcd and vcd_to_ps on VCDDatabase."""

    def test_1fs_timescale_ps_to_vcd(self):
        """With 1fs timescale: 1ps = 1000 VCD units."""
        db = VCDDatabase({}, set(), timescale_fs=1)
        assert db.ps_to_vcd(1) == 1000

    def test_1fs_timescale_vcd_to_ps(self):
        """With 1fs timescale: 1000 VCD units = 1ps."""
        db = VCDDatabase({}, set(), timescale_fs=1)
        assert db.vcd_to_ps(1000) == 1

    def test_1ps_timescale_ps_to_vcd(self):
        """With 1ps timescale: 1ps = 1 VCD unit."""
        db = VCDDatabase({}, set(), timescale_fs=1000)
        assert db.ps_to_vcd(1) == 1

    def test_1ps_timescale_vcd_to_ps(self):
        """With 1ps timescale: 1 VCD unit = 1ps."""
        db = VCDDatabase({}, set(), timescale_fs=1000)
        assert db.vcd_to_ps(1) == 1

    def test_1ns_timescale_ps_to_vcd(self):
        """With 1ns timescale: 1ps = 0.001 VCD units, rounds to 0."""
        db = VCDDatabase({}, set(), timescale_fs=1_000_000)
        assert db.ps_to_vcd(1) == 0  # integer division: 1000 // 1000000 = 0

    def test_1ns_timescale_vcd_to_ps(self):
        """With 1ns timescale: 1 VCD unit = 1000ps."""
        db = VCDDatabase({}, set(), timescale_fs=1_000_000)
        assert db.vcd_to_ps(1) == 1000

    def test_1ns_timescale_larger_ps(self):
        """With 1ns timescale: 1000ps = 1 VCD unit."""
        db = VCDDatabase({}, set(), timescale_fs=1_000_000)
        assert db.ps_to_vcd(1000) == 1

    def test_roundtrip_1ps(self):
        """Round-trip conversion with 1ps timescale."""
        db = VCDDatabase({}, set(), timescale_fs=1000)
        for ps_val in [0, 1, 100, 999, 1000, 50000]:
            assert db.vcd_to_ps(db.ps_to_vcd(ps_val)) == ps_val


# ===========================================================================
# 5. TestPrefixMappedVCD
# ===========================================================================

class TestPrefixMappedVCD:
    """Test PrefixMappedVCD prefix translation."""

    def _make_db(self):
        """Create a VCDDatabase with tb.dut.* signals."""
        transitions = {
            "tb.dut.sig1": [(0, "0"), (100, "1")],
            "tb.dut.sig2": [(0, "1"), (100, "0")],
            "tb.dut.bus":  [(0, "0000"), (100, "1010")],
        }
        signals = {"tb.dut.sig1", "tb.dut.sig2", "tb.dut.bus"}
        return VCDDatabase(transitions, signals, timescale_fs=1000)

    def test_mapped_get_value(self):
        inner = self._make_db()
        mapped = PrefixMappedVCD(inner, "tb.dut", "my_top")
        # my_top.sig1 -> tb.dut.sig1
        assert mapped.get_value("my_top.sig1", 0) == "0"
        assert mapped.get_value("my_top.sig1", 100) == "1"

    def test_mapped_get_bit(self):
        inner = self._make_db()
        mapped = PrefixMappedVCD(inner, "tb.dut", "my_top")
        assert mapped.get_bit("my_top.bus", 0, 100) == "0"
        assert mapped.get_bit("my_top.bus", 1, 100) == "1"

    def test_mapped_get_transitions(self):
        inner = self._make_db()
        mapped = PrefixMappedVCD(inner, "tb.dut", "my_top")
        trans = mapped.get_transitions("my_top.sig2")
        assert trans == [(0, "1"), (100, "0")]

    def test_mapped_has_signal(self):
        inner = self._make_db()
        mapped = PrefixMappedVCD(inner, "tb.dut", "my_top")
        assert mapped.has_signal("my_top.sig1")
        assert not mapped.has_signal("my_top.nonexistent")

    def test_mapped_passthrough_vcd_path(self):
        """If signal already uses VCD prefix, it should pass through."""
        inner = self._make_db()
        mapped = PrefixMappedVCD(inner, "tb.dut", "my_top")
        assert mapped.get_value("tb.dut.sig1", 0) == "0"

    def test_mapped_get_all_signals_returns_original(self):
        """get_all_signals returns original VCD paths, not mapped ones."""
        inner = self._make_db()
        mapped = PrefixMappedVCD(inner, "tb.dut", "my_top")
        sigs = mapped.get_all_signals()
        assert "tb.dut.sig1" in sigs
        assert "my_top.sig1" not in sigs

    def test_mapped_timescale(self):
        inner = self._make_db()
        mapped = PrefixMappedVCD(inner, "tb.dut", "my_top")
        assert mapped.timescale_fs == 1000
        assert mapped.ps_to_vcd(1) == 1
        assert mapped.vcd_to_ps(1) == 1

    def test_mapped_first_x_time(self):
        transitions = {
            "tb.dut.xsig": [(0, "0"), (50, "x"), (200, "1")],
        }
        inner = VCDDatabase(transitions, {"tb.dut.xsig"})
        mapped = PrefixMappedVCD(inner, "tb.dut", "my_top")
        assert mapped.first_x_time("my_top.xsig", 0) == 50


# ===========================================================================
# 6. TestLineParserSignalFiltering
# ===========================================================================

class TestLineParserSignalFiltering:
    """Test signal filtering in the line parser."""

    def test_only_requested_signals_have_transitions(self):
        path = _write_vcd(TEN_SIGNAL_VCD)
        try:
            requested = {"tb.sig0", "tb.sig5"}
            db = _load_line_parser(path, signals=requested)

            # Only requested signals should have transitions
            trans0 = db.get_transitions("tb.sig0")
            assert len(trans0) > 0
            trans5 = db.get_transitions("tb.sig5")
            assert len(trans5) > 0

            # Other signals should raise KeyError (no transitions loaded)
            with pytest.raises(KeyError):
                db.get_transitions("tb.sig1")
            with pytest.raises(KeyError):
                db.get_transitions("tb.sig9")
        finally:
            os.unlink(path)

    def test_all_signals_still_discoverable(self):
        path = _write_vcd(TEN_SIGNAL_VCD)
        try:
            requested = {"tb.sig0", "tb.sig5"}
            db = _load_line_parser(path, signals=requested)

            all_sigs = db.get_all_signals()
            assert len(all_sigs) == 10
            for i in range(10):
                assert f"tb.sig{i}" in all_sigs
        finally:
            os.unlink(path)

    def test_has_signal_for_unloaded(self):
        path = _write_vcd(TEN_SIGNAL_VCD)
        try:
            requested = {"tb.sig0"}
            db = _load_line_parser(path, signals=requested)
            # has_signal checks signal set, not transitions
            assert db.has_signal("tb.sig3")
            assert db.has_signal("tb.sig0")
        finally:
            os.unlink(path)


# ===========================================================================
# 7. TestLineParserBinaryValues
# ===========================================================================

class TestLineParserBinaryValues:
    """Test scalar and vector value changes in the line parser."""

    def test_scalar_0_and_1(self):
        path = _write_vcd(BINARY_VALUES_VCD)
        try:
            db = _load_line_parser(path)
            assert db.get_value("tb.scalar", 0) == "0"
            assert db.get_value("tb.scalar", 10) == "1"
        finally:
            os.unlink(path)

    def test_scalar_x(self):
        path = _write_vcd(BINARY_VALUES_VCD)
        try:
            db = _load_line_parser(path)
            assert db.get_value("tb.scalar", 20) == "x"
        finally:
            os.unlink(path)

    def test_scalar_z(self):
        path = _write_vcd(BINARY_VALUES_VCD)
        try:
            db = _load_line_parser(path)
            assert db.get_value("tb.scalar", 30) == "z"
        finally:
            os.unlink(path)

    def test_vector_binary_value(self):
        path = _write_vcd(BINARY_VALUES_VCD)
        try:
            db = _load_line_parser(path)
            # At time 0: b0000
            assert db.get_value("tb.bus", 0) == "0000"
            # At time 10: b0110
            assert db.get_value("tb.bus", 10) == "0110"
        finally:
            os.unlink(path)

    def test_vector_with_x_and_z(self):
        path = _write_vcd(BINARY_VALUES_VCD)
        try:
            db = _load_line_parser(path)
            # At time 20: b1x0z
            assert db.get_value("tb.bus", 20) == "1x0z"
        finally:
            os.unlink(path)

    def test_vector_all_ones(self):
        path = _write_vcd(BINARY_VALUES_VCD)
        try:
            db = _load_line_parser(path)
            # At time 30: b1111
            assert db.get_value("tb.bus", 30) == "1111"
        finally:
            os.unlink(path)

    def test_get_bit_from_vector(self):
        path = _write_vcd(BINARY_VALUES_VCD)
        try:
            db = _load_line_parser(path)
            # At time 10, bus = "0110": bit0=0, bit1=1, bit2=1, bit3=0
            assert db.get_bit("tb.bus", 0, 10) == "0"
            assert db.get_bit("tb.bus", 1, 10) == "1"
            assert db.get_bit("tb.bus", 2, 10) == "1"
            assert db.get_bit("tb.bus", 3, 10) == "0"
        finally:
            os.unlink(path)

    def test_get_bit_xz_from_vector(self):
        path = _write_vcd(BINARY_VALUES_VCD)
        try:
            db = _load_line_parser(path)
            # At time 20, bus = "1x0z": bit0=z->x, bit1=0, bit2=x, bit3=1
            assert db.get_bit("tb.bus", 0, 20) == "x"  # z treated as x
            assert db.get_bit("tb.bus", 1, 20) == "0"
            assert db.get_bit("tb.bus", 2, 20) == "x"
            assert db.get_bit("tb.bus", 3, 20) == "1"
        finally:
            os.unlink(path)
