"""Tests for the Gate X-Propagation Model (Module 3)."""

import pytest
from src.gates import GateModel


@pytest.fixture
def gm():
    return GateModel()


# ============================================================
# Tier 1: Verilog Primitives — forward()
# ============================================================

class TestAndForward:
    def test_and_00(self, gm):
        assert gm.forward('and', {'in0': '0', 'in1': '0'}) == '0'

    def test_and_01(self, gm):
        assert gm.forward('and', {'in0': '0', 'in1': '1'}) == '0'

    def test_and_11(self, gm):
        assert gm.forward('and', {'in0': '1', 'in1': '1'}) == '1'

    def test_and_x0(self, gm):
        """Controlling value 0 masks X."""
        assert gm.forward('and', {'in0': 'x', 'in1': '0'}) == '0'

    def test_and_0x(self, gm):
        assert gm.forward('and', {'in0': '0', 'in1': 'x'}) == '0'

    def test_and_x1(self, gm):
        assert gm.forward('and', {'in0': 'x', 'in1': '1'}) == 'x'

    def test_and_xx(self, gm):
        assert gm.forward('and', {'in0': 'x', 'in1': 'x'}) == 'x'

    def test_and_z1(self, gm):
        """z treated as x."""
        assert gm.forward('and', {'in0': 'z', 'in1': '1'}) == 'x'

    def test_and_z0(self, gm):
        assert gm.forward('and', {'in0': 'z', 'in1': '0'}) == '0'


class TestNandForward:
    def test_nand_11(self, gm):
        assert gm.forward('nand', {'in0': '1', 'in1': '1'}) == '0'

    def test_nand_x0(self, gm):
        assert gm.forward('nand', {'in0': 'x', 'in1': '0'}) == '1'

    def test_nand_x1(self, gm):
        assert gm.forward('nand', {'in0': 'x', 'in1': '1'}) == 'x'


class TestOrForward:
    def test_or_00(self, gm):
        assert gm.forward('or', {'in0': '0', 'in1': '0'}) == '0'

    def test_or_01(self, gm):
        assert gm.forward('or', {'in0': '0', 'in1': '1'}) == '1'

    def test_or_x1(self, gm):
        """Controlling value 1 masks X."""
        assert gm.forward('or', {'in0': 'x', 'in1': '1'}) == '1'

    def test_or_1x(self, gm):
        assert gm.forward('or', {'in0': '1', 'in1': 'x'}) == '1'

    def test_or_x0(self, gm):
        assert gm.forward('or', {'in0': 'x', 'in1': '0'}) == 'x'

    def test_or_xx(self, gm):
        assert gm.forward('or', {'in0': 'x', 'in1': 'x'}) == 'x'

    def test_or_z0(self, gm):
        assert gm.forward('or', {'in0': 'z', 'in1': '0'}) == 'x'


class TestNorForward:
    def test_nor_00(self, gm):
        assert gm.forward('nor', {'in0': '0', 'in1': '0'}) == '1'

    def test_nor_x1(self, gm):
        assert gm.forward('nor', {'in0': 'x', 'in1': '1'}) == '0'

    def test_nor_x0(self, gm):
        assert gm.forward('nor', {'in0': 'x', 'in1': '0'}) == 'x'


class TestXorForward:
    def test_xor_00(self, gm):
        assert gm.forward('xor', {'in0': '0', 'in1': '0'}) == '0'

    def test_xor_01(self, gm):
        assert gm.forward('xor', {'in0': '0', 'in1': '1'}) == '1'

    def test_xor_11(self, gm):
        assert gm.forward('xor', {'in0': '1', 'in1': '1'}) == '0'

    def test_xor_x0(self, gm):
        """XOR never masks X."""
        assert gm.forward('xor', {'in0': 'x', 'in1': '0'}) == 'x'

    def test_xor_x1(self, gm):
        assert gm.forward('xor', {'in0': 'x', 'in1': '1'}) == 'x'

    def test_xor_xx(self, gm):
        assert gm.forward('xor', {'in0': 'x', 'in1': 'x'}) == 'x'


class TestXnorForward:
    def test_xnor_00(self, gm):
        assert gm.forward('xnor', {'in0': '0', 'in1': '0'}) == '1'

    def test_xnor_01(self, gm):
        assert gm.forward('xnor', {'in0': '0', 'in1': '1'}) == '0'

    def test_xnor_x0(self, gm):
        assert gm.forward('xnor', {'in0': 'x', 'in1': '0'}) == 'x'


class TestNotBufForward:
    def test_not_0(self, gm):
        assert gm.forward('not', {'in0': '0'}) == '1'

    def test_not_1(self, gm):
        assert gm.forward('not', {'in0': '1'}) == '0'

    def test_not_x(self, gm):
        assert gm.forward('not', {'in0': 'x'}) == 'x'

    def test_not_z(self, gm):
        assert gm.forward('not', {'in0': 'z'}) == 'x'

    def test_buf_0(self, gm):
        assert gm.forward('buf', {'in0': '0'}) == '0'

    def test_buf_1(self, gm):
        assert gm.forward('buf', {'in0': '1'}) == '1'

    def test_buf_x(self, gm):
        assert gm.forward('buf', {'in0': 'x'}) == 'x'


class TestTristateForward:
    # bufif0: active when enable=0
    def test_bufif0_data0_en0(self, gm):
        assert gm.forward('bufif0', {'in0': '0', 'in1': '0'}) == '0'

    def test_bufif0_data1_en0(self, gm):
        assert gm.forward('bufif0', {'in0': '1', 'in1': '0'}) == '1'

    def test_bufif0_data0_en1(self, gm):
        assert gm.forward('bufif0', {'in0': '0', 'in1': '1'}) == 'z'

    def test_bufif0_datax_en0(self, gm):
        assert gm.forward('bufif0', {'in0': 'x', 'in1': '0'}) == 'x'

    def test_bufif0_data0_enx(self, gm):
        assert gm.forward('bufif0', {'in0': '0', 'in1': 'x'}) == 'x'

    # bufif1: active when enable=1
    def test_bufif1_data0_en1(self, gm):
        assert gm.forward('bufif1', {'in0': '0', 'in1': '1'}) == '0'

    def test_bufif1_data0_en0(self, gm):
        assert gm.forward('bufif1', {'in0': '0', 'in1': '0'}) == 'z'

    def test_bufif1_datax_en1(self, gm):
        assert gm.forward('bufif1', {'in0': 'x', 'in1': '1'}) == 'x'

    # notif0: active when enable=0, inverts data
    def test_notif0_data0_en0(self, gm):
        assert gm.forward('notif0', {'in0': '0', 'in1': '0'}) == '1'

    def test_notif0_data1_en0(self, gm):
        assert gm.forward('notif0', {'in0': '1', 'in1': '0'}) == '0'

    def test_notif0_data0_en1(self, gm):
        assert gm.forward('notif0', {'in0': '0', 'in1': '1'}) == 'z'

    # notif1: active when enable=1, inverts data
    def test_notif1_data0_en1(self, gm):
        assert gm.forward('notif1', {'in0': '0', 'in1': '1'}) == '1'

    def test_notif1_data1_en1(self, gm):
        assert gm.forward('notif1', {'in0': '1', 'in1': '1'}) == '0'


# ============================================================
# Tier 1: Verilog Primitives — backward_causes()
# ============================================================

class TestAndBackward:
    def test_and_x1(self, gm):
        assert gm.backward_causes('and', {'in0': 'x', 'in1': '1'}) == ['in0']

    def test_and_1x(self, gm):
        assert gm.backward_causes('and', {'in0': '1', 'in1': 'x'}) == ['in1']

    def test_and_xx(self, gm):
        result = gm.backward_causes('and', {'in0': 'x', 'in1': 'x'})
        assert sorted(result) == ['in0', 'in1']

    def test_and_x0_masked(self, gm):
        """0 is controlling value for AND — no X causes."""
        assert gm.backward_causes('and', {'in0': 'x', 'in1': '0'}) == []


class TestOrBackward:
    def test_or_x0(self, gm):
        assert gm.backward_causes('or', {'in0': 'x', 'in1': '0'}) == ['in0']

    def test_or_x1_masked(self, gm):
        """1 is controlling value for OR — no X causes."""
        assert gm.backward_causes('or', {'in0': 'x', 'in1': '1'}) == []

    def test_or_xx(self, gm):
        result = gm.backward_causes('or', {'in0': 'x', 'in1': 'x'})
        assert sorted(result) == ['in0', 'in1']


class TestNandBackward:
    def test_nand_x1(self, gm):
        assert gm.backward_causes('nand', {'in0': 'x', 'in1': '1'}) == ['in0']

    def test_nand_x0_masked(self, gm):
        assert gm.backward_causes('nand', {'in0': 'x', 'in1': '0'}) == []


class TestXorBackward:
    def test_xor_x0(self, gm):
        """XOR never masks — X with 0 still causal."""
        assert gm.backward_causes('xor', {'in0': 'x', 'in1': '0'}) == ['in0']

    def test_xor_x1(self, gm):
        assert gm.backward_causes('xor', {'in0': 'x', 'in1': '1'}) == ['in0']

    def test_xor_1x(self, gm):
        assert gm.backward_causes('xor', {'in0': '1', 'in1': 'x'}) == ['in1']


class TestNotBufBackward:
    def test_not_x(self, gm):
        assert gm.backward_causes('not', {'in0': 'x'}) == ['in0']

    def test_not_0(self, gm):
        assert gm.backward_causes('not', {'in0': '0'}) == []

    def test_buf_x(self, gm):
        assert gm.backward_causes('buf', {'in0': 'x'}) == ['in0']


class TestTristateBackward:
    def test_bufif0_datax_en0(self, gm):
        """Data is X, enable active — data is causal."""
        result = gm.backward_causes('bufif0', {'in0': 'x', 'in1': '0'})
        assert result == ['in0']

    def test_bufif0_data0_enx(self, gm):
        """Enable is X — enable is causal."""
        result = gm.backward_causes('bufif0', {'in0': '0', 'in1': 'x'})
        assert result == ['in1']

    def test_bufif0_datax_enx(self, gm):
        """Both X — both causal."""
        result = gm.backward_causes('bufif0', {'in0': 'x', 'in1': 'x'})
        assert sorted(result) == ['in0', 'in1']

    def test_bufif1_datax_en1(self, gm):
        result = gm.backward_causes('bufif1', {'in0': 'x', 'in1': '1'})
        assert result == ['in0']


# ============================================================
# Multi-input gates
# ============================================================

class TestMultiInput:
    def test_and3_forward(self, gm):
        assert gm.forward('and', {'in0': '1', 'in1': '1', 'in2': '1'}) == '1'
        assert gm.forward('and', {'in0': '1', 'in1': 'x', 'in2': '1'}) == 'x'
        assert gm.forward('and', {'in0': '1', 'in1': 'x', 'in2': '0'}) == '0'

    def test_or4_forward(self, gm):
        assert gm.forward('or', {'in0': '0', 'in1': '0', 'in2': '0', 'in3': '0'}) == '0'
        assert gm.forward('or', {'in0': '0', 'in1': 'x', 'in2': '0', 'in3': '1'}) == '1'

    def test_xnor3_forward(self, gm):
        assert gm.forward('xnor', {'in0': '0', 'in1': '0', 'in2': '0'}) == '1'
        assert gm.forward('xnor', {'in0': '1', 'in1': '1', 'in2': '0'}) == '1'
        assert gm.forward('xnor', {'in0': 'x', 'in1': '0', 'in2': '0'}) == 'x'

    def test_and3_backward(self, gm):
        result = gm.backward_causes('and', {'in0': 'x', 'in1': '1', 'in2': '1'})
        assert result == ['in0']

    def test_and3_backward_masked(self, gm):
        result = gm.backward_causes('and', {'in0': 'x', 'in1': '0', 'in2': '1'})
        assert result == []


# ============================================================
# Tier 2: Standard Cells
# ============================================================

class TestCellNameStripping:
    def test_sky130_nand2(self, gm):
        assert gm.is_known_cell('sky130_fd_sc_hd__nand2_1') is True

    def test_sky130_and2(self, gm):
        assert gm.is_known_cell('sky130_fd_sc_hd__and2_4') is True

    def test_sky130_inv(self, gm):
        assert gm.is_known_cell('sky130_fd_sc_hd__inv_2') is True

    def test_sky130_a21oi(self, gm):
        assert gm.is_known_cell('sky130_fd_sc_hd__a21oi_1') is True

    def test_sky130_dfxtp(self, gm):
        assert gm.is_known_cell('sky130_fd_sc_hd__dfxtp_1') is True

    def test_unknown(self, gm):
        assert gm.is_known_cell('totally_unknown_cell') is False


class TestStdCellForward:
    def test_nand2_std(self, gm):
        assert gm.forward('sky130_fd_sc_hd__nand2_1', {'A': '1', 'B': '1'}) == '0'
        assert gm.forward('sky130_fd_sc_hd__nand2_1', {'A': 'x', 'B': '0'}) == '1'

    def test_and2_std(self, gm):
        assert gm.forward('sky130_fd_sc_hd__and2_4', {'A': '1', 'B': '1'}) == '1'

    def test_inv_std(self, gm):
        assert gm.forward('sky130_fd_sc_hd__inv_2', {'A': '1'}) == '0'
        assert gm.forward('sky130_fd_sc_hd__inv_2', {'A': 'x'}) == 'x'

    def test_or3_std(self, gm):
        assert gm.forward('sky130_fd_sc_hd__or3_1', {'A': '0', 'B': '0', 'C': '0'}) == '0'
        assert gm.forward('sky130_fd_sc_hd__or3_1', {'A': '0', 'B': 'x', 'C': '1'}) == '1'


class TestStdCellBackward:
    def test_nand2_backward(self, gm):
        result = gm.backward_causes('sky130_fd_sc_hd__nand2_1', {'A': 'x', 'B': '1'})
        assert result == ['A']

    def test_and2_backward_masked(self, gm):
        result = gm.backward_causes('sky130_fd_sc_hd__and2_4', {'A': 'x', 'B': '0'})
        assert result == []


# ============================================================
# AOI / OAI cells
# ============================================================

class TestAOI:
    def test_a21oi_all_known(self, gm):
        # Y = ~((A1 & A2) | B1) = ~((1 & 1) | 0) = ~(1 | 0) = ~1 = 0
        assert gm.forward('a21oi', {'A1': '1', 'A2': '1', 'B1': '0'}) == '0'

    def test_a21oi_and_masked(self, gm):
        # Y = ~((0 & A2) | B1) = ~(0 | 0) = ~0 = 1 (A1=0 masks AND)
        assert gm.forward('a21oi', {'A1': '0', 'A2': 'x', 'B1': '0'}) == '1'

    def test_a21oi_x_propagates(self, gm):
        # A1=x, A2=1, B1=0: AND=x, OR=x|0=x, NOR=x → Y=x
        assert gm.forward('a21oi', {'A1': 'x', 'A2': '1', 'B1': '0'}) == 'x'

    def test_a21oi_backward(self, gm):
        # A1=x, A2=1, B1=0: AND result is x, OR result is x, causes = [A1]
        result = gm.backward_causes('a21oi', {'A1': 'x', 'A2': '1', 'B1': '0'})
        assert result == ['A1']

    def test_a21oi_backward_b1_x(self, gm):
        # A1=1, A2=1, B1=x: AND=1, OR=(1|x)=1, NOR=0 → output determined, no X causes
        result = gm.backward_causes('a21oi', {'A1': '1', 'A2': '1', 'B1': 'x'})
        assert result == []

    def test_a21oi_backward_both_x(self, gm):
        # A1=x, A2=1, B1=x: AND=x, OR=x, causes=[A1, B1]
        result = gm.backward_causes('a21oi', {'A1': 'x', 'A2': '1', 'B1': 'x'})
        assert sorted(result) == ['A1', 'B1']

    def test_a22oi_forward(self, gm):
        # Y = ~((A1 & A2) | (B1 & B2))
        assert gm.forward('a22oi', {'A1': '1', 'A2': '1', 'B1': '0', 'B2': '0'}) == '0'
        assert gm.forward('a22oi', {'A1': '0', 'A2': '0', 'B1': '0', 'B2': '0'}) == '1'


class TestOAI:
    def test_o21ai_forward(self, gm):
        # Y = ~((A1 | A2) & B1)
        # (1 | 0) & 1 = 1 & 1 = 1, ~1 = 0
        assert gm.forward('o21ai', {'A1': '1', 'A2': '0', 'B1': '1'}) == '0'
        # (0 | 0) & 1 = 0 & 1 = 0, ~0 = 1
        assert gm.forward('o21ai', {'A1': '0', 'A2': '0', 'B1': '1'}) == '1'

    def test_o21ai_x_masked(self, gm):
        # (x | 1) & B1 = 1 & B1 — OR controlling value 1 masks x in A1
        # Then AND with B1=0: 1 & 0 = 0, ~0 = 1
        assert gm.forward('o21ai', {'A1': 'x', 'A2': '1', 'B1': '0'}) == '1'

    def test_o21ai_backward(self, gm):
        # A1=x, A2=0, B1=1: OR=x, AND=(x & 1)=x, causes=[A1]
        result = gm.backward_causes('o21ai', {'A1': 'x', 'A2': '0', 'B1': '1'})
        assert result == ['A1']

    def test_o21ai_backward_b1x(self, gm):
        # A1=0, A2=0, B1=x: OR=0, AND=(0 & x)=0, ~0=1 → determined
        result = gm.backward_causes('o21ai', {'A1': '0', 'A2': '0', 'B1': 'x'})
        assert result == []


# ============================================================
# MUX
# ============================================================

class TestMux:
    def test_mux2_sel0_a0x(self, gm):
        assert gm.forward('mux2', {'A0': 'x', 'A1': '0', 'S': '0'}) == 'x'
        result = gm.backward_causes('mux2', {'A0': 'x', 'A1': '0', 'S': '0'})
        assert result == ['A0']

    def test_mux2_sel1_a1x(self, gm):
        assert gm.forward('mux2', {'A0': '0', 'A1': 'x', 'S': '1'}) == 'x'
        result = gm.backward_causes('mux2', {'A0': '0', 'A1': 'x', 'S': '1'})
        assert result == ['A1']

    def test_mux2_selx(self, gm):
        assert gm.forward('mux2', {'A0': '0', 'A1': '1', 'S': 'x'}) == 'x'
        result = gm.backward_causes('mux2', {'A0': '0', 'A1': '1', 'S': 'x'})
        assert result == ['S']

    def test_mux2_selx_both_same(self, gm):
        """If both data inputs are same known value, S=x doesn't matter."""
        assert gm.forward('mux2', {'A0': '1', 'A1': '1', 'S': 'x'}) == '1'

    def test_mux2_selx_datax(self, gm):
        result = gm.backward_causes('mux2', {'A0': 'x', 'A1': '0', 'S': 'x'})
        assert sorted(result) == ['A0', 'S']

    def test_mux2_sel0_a0ok(self, gm):
        """No X causes when selected input is known."""
        assert gm.forward('mux2', {'A0': '1', 'A1': 'x', 'S': '0'}) == '1'


# ============================================================
# Adders and Majority
# ============================================================

class TestAdders:
    def test_ha_forward(self, gm):
        assert gm.forward('ha', {'A': '0', 'B': '0'}) == '0'
        assert gm.forward('ha', {'A': '1', 'B': '0'}) == '1'
        assert gm.forward('ha', {'A': '1', 'B': '1'}) == '0'
        assert gm.forward('ha', {'A': 'x', 'B': '0'}) == 'x'

    def test_fa_forward(self, gm):
        assert gm.forward('fa', {'A': '0', 'B': '0', 'CIN': '0'}) == '0'
        assert gm.forward('fa', {'A': '1', 'B': '1', 'CIN': '1'}) == '1'
        assert gm.forward('fa', {'A': 'x', 'B': '0', 'CIN': '0'}) == 'x'

    def test_maj_forward(self, gm):
        assert gm.forward('maj3', {'A': '1', 'B': '1', 'C': '0'}) == '1'
        assert gm.forward('maj3', {'A': '0', 'B': '0', 'C': '1'}) == '0'
        assert gm.forward('maj3', {'A': '1', 'B': '1', 'C': '1'}) == '1'


# ============================================================
# Unknown Cell (Conservative Fallback)
# ============================================================

class TestUnknownCell:
    def test_unknown_forward_with_x(self, gm):
        assert gm.forward('totally_unknown', {'A': '0', 'B': 'x'}) == 'x'

    def test_unknown_forward_no_x(self, gm):
        assert gm.forward('totally_unknown', {'A': '0', 'B': '1'}) == '0'

    def test_unknown_backward(self, gm):
        """Conservative fallback: all X ports returned."""
        result = gm.backward_causes('totally_unknown', {'A': '0', 'B': 'x', 'C': 'x'})
        assert sorted(result) == ['B', 'C']

    def test_unknown_backward_no_x(self, gm):
        result = gm.backward_causes('totally_unknown', {'A': '0', 'B': '1'})
        assert result == []

    def test_unknown_is_known(self, gm):
        assert gm.is_known_cell('totally_unknown') is False


# ============================================================
# is_known_cell
# ============================================================

class TestIsKnownCell:
    def test_primitives(self, gm):
        for p in ['and', 'nand', 'or', 'nor', 'xor', 'xnor', 'not', 'buf',
                   'bufif0', 'bufif1', 'notif0', 'notif1']:
            assert gm.is_known_cell(p) is True, f'{p} should be known'

    def test_assign(self, gm):
        assert gm.is_known_cell('assign') is True

    def test_std_cells(self, gm):
        for c in ['and2', 'nand3', 'or4', 'inv', 'buf', 'mux2', 'a21oi', 'o21ai']:
            assert gm.is_known_cell(c) is True, f'{c} should be known'


# ============================================================
# z treated as x
# ============================================================

class TestZasX:
    def test_and_z(self, gm):
        """z is treated as x for AND."""
        assert gm.forward('and', {'in0': 'z', 'in1': '1'}) == 'x'

    def test_or_z(self, gm):
        assert gm.forward('or', {'in0': 'z', 'in1': '0'}) == 'x'

    def test_backward_z(self, gm):
        """z-valued input treated as X for backward_causes."""
        result = gm.backward_causes('and', {'in0': 'z', 'in1': '1'})
        assert result == ['in0']
