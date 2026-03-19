"""Tests for the netlist parser module."""

import tempfile
from pathlib import Path

import pytest

from src.netlist import Gate, Pin, NetlistGraph, parse_netlist


def _parse_verilog(code: str) -> NetlistGraph:
    """Helper: write Verilog to a temp file and parse it."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".v", delete=False) as f:
        f.write(code)
        f.flush()
        return parse_netlist([Path(f.name)])


class TestSimpleAnd:
    """Test a single AND gate."""

    VERILOG = """\
module top(input a, input b, output y);
  and u1(y, a, b);
endmodule
"""

    @pytest.fixture
    def graph(self):
        return _parse_verilog(self.VERILOG)

    def test_gate_exists(self, graph):
        gate = graph.get_gate("top.u1")
        assert gate is not None
        assert gate.cell_type == "and"
        assert gate.instance_path == "top.u1"

    def test_gate_inputs(self, graph):
        gate = graph.get_gate("top.u1")
        assert "A" in gate.inputs
        assert "B" in gate.inputs
        assert gate.inputs["A"].signal == "top.a"
        assert gate.inputs["B"].signal == "top.b"

    def test_gate_output(self, graph):
        gate = graph.get_gate("top.u1")
        assert "Y" in gate.outputs
        assert gate.outputs["Y"].signal == "top.y"

    def test_get_drivers(self, graph):
        drivers = graph.get_drivers("top.y")
        assert len(drivers) == 1
        assert drivers[0].instance_path == "top.u1"

    def test_get_fanout(self, graph):
        fanout = graph.get_fanout("top.a")
        assert len(fanout) == 1
        assert fanout[0].instance_path == "top.u1"

    def test_not_sequential(self, graph):
        gate = graph.get_gate("top.u1")
        assert gate.is_sequential is False


class TestGateChain:
    """Test a chain: AND -> OR -> NOT."""

    VERILOG = """\
module top(input a, input b, input c, output y);
  wire n1, n2;
  and u1(n1, a, b);
  or  u2(n2, n1, c);
  not u3(y, n2);
endmodule
"""

    @pytest.fixture
    def graph(self):
        return _parse_verilog(self.VERILOG)

    def test_chain_gates(self, graph):
        assert graph.get_gate("top.u1") is not None
        assert graph.get_gate("top.u2") is not None
        assert graph.get_gate("top.u3") is not None

    def test_chain_connectivity(self, graph):
        # n1 is driven by u1, consumed by u2
        drivers_n1 = graph.get_drivers("top.n1")
        assert len(drivers_n1) == 1
        assert drivers_n1[0].cell_type == "and"

        fanout_n1 = graph.get_fanout("top.n1")
        assert len(fanout_n1) == 1
        assert fanout_n1[0].cell_type == "or"

    def test_input_cone(self, graph):
        cone = graph.get_input_cone("top.y")
        # y <- n2 <- n1, c <- a, b
        assert "top.y" in cone
        assert "top.n2" in cone
        assert "top.n1" in cone
        assert "top.a" in cone
        assert "top.b" in cone
        assert "top.c" in cone

    def test_all_signals(self, graph):
        sigs = graph.get_all_signals()
        for s in ["top.a", "top.b", "top.c", "top.n1", "top.n2", "top.y"]:
            assert s in sigs


class TestDffWithReset:
    """Test a DFF module instance with reset."""

    VERILOG = """\
module my_dff(input D, input CLK, input RST, output Q);
endmodule

module top(input d, input clk, input rst, output q);
  my_dff ff1(.D(d), .CLK(clk), .RST(rst), .Q(q));
endmodule
"""

    @pytest.fixture
    def graph(self):
        return _parse_verilog(self.VERILOG)

    def test_dff_exists(self, graph):
        gate = graph.get_gate("top.ff1")
        assert gate is not None
        assert gate.cell_type == "my_dff"

    def test_dff_is_sequential(self, graph):
        gate = graph.get_gate("top.ff1")
        assert gate.is_sequential is True

    def test_dff_port_roles(self, graph):
        gate = graph.get_gate("top.ff1")
        assert gate.clock_port == "CLK"
        assert gate.d_port == "D"
        assert gate.q_port == "Q"
        assert gate.reset_port == "RST"

    def test_dff_connections(self, graph):
        gate = graph.get_gate("top.ff1")
        assert gate.inputs["D"].signal == "top.d"
        assert gate.inputs["CLK"].signal == "top.clk"
        assert gate.inputs["RST"].signal == "top.rst"
        assert gate.outputs["Q"].signal == "top.q"


class TestMultiDriver:
    """Test multi-driver net with two bufif1 gates."""

    VERILOG = """\
module top(input a, input b, input en1, input en2, output y);
  bufif1 u1(y, a, en1);
  bufif1 u2(y, b, en2);
endmodule
"""

    @pytest.fixture
    def graph(self):
        return _parse_verilog(self.VERILOG)

    def test_multi_driver(self, graph):
        drivers = graph.get_drivers("top.y")
        assert len(drivers) == 2
        types = {d.cell_type for d in drivers}
        assert types == {"bufif1"}


class TestContinuousAssign:
    """Test continuous assign statements."""

    VERILOG = """\
module top(input a, output y);
  wire n;
  assign n = a;
  assign y = n;
endmodule
"""

    @pytest.fixture
    def graph(self):
        return _parse_verilog(self.VERILOG)

    def test_assign_gates(self, graph):
        # n is driven by an assign from a
        drivers_n = graph.get_drivers("top.n")
        assert len(drivers_n) == 1
        assert drivers_n[0].cell_type == "assign"
        assert drivers_n[0].inputs["A"].signal == "top.a"
        assert drivers_n[0].outputs["Y"].signal == "top.n"

    def test_assign_chain(self, graph):
        drivers_y = graph.get_drivers("top.y")
        assert len(drivers_y) == 1
        assert drivers_y[0].cell_type == "assign"

    def test_input_cone(self, graph):
        cone = graph.get_input_cone("top.y")
        assert "top.y" in cone
        assert "top.n" in cone
        assert "top.a" in cone


class TestBitSelect:
    """Test bit-level connections."""

    VERILOG = """\
module top(input [1:0] a, output [1:0] y);
  and u0(y[0], a[0], a[1]);
  or  u1(y[1], a[0], a[1]);
endmodule
"""

    @pytest.fixture
    def graph(self):
        return _parse_verilog(self.VERILOG)

    def test_bit_select_output(self, graph):
        gate = graph.get_gate("top.u0")
        assert gate is not None
        assert gate.outputs["Y"].signal == "top.y"
        assert gate.outputs["Y"].bit == 0

    def test_bit_select_inputs(self, graph):
        gate = graph.get_gate("top.u0")
        assert gate.inputs["A"].signal == "top.a"
        assert gate.inputs["A"].bit == 0
        assert gate.inputs["B"].signal == "top.a"
        assert gate.inputs["B"].bit == 1

    def test_bit_level_drivers(self, graph):
        drivers = graph.get_drivers("top.y[0]")
        assert len(drivers) == 1
        assert drivers[0].cell_type == "and"

        drivers = graph.get_drivers("top.y[1]")
        assert len(drivers) == 1
        assert drivers[0].cell_type == "or"


class TestSky130Dff:
    """Test Sky130-style DFF cell name detection."""

    VERILOG = """\
module sky130_fd_sc_hd__dfxtp_1(input D, input CLK, output Q);
endmodule

module top(input d, input clk, output q);
  sky130_fd_sc_hd__dfxtp_1 ff1(.D(d), .CLK(clk), .Q(q));
endmodule
"""

    @pytest.fixture
    def graph(self):
        return _parse_verilog(self.VERILOG)

    def test_sky130_sequential(self, graph):
        gate = graph.get_gate("top.ff1")
        assert gate is not None
        assert gate.is_sequential is True
        assert gate.clock_port == "CLK"
        assert gate.d_port == "D"
        assert gate.q_port == "Q"


class TestNandNorXor:
    """Test various Verilog primitives."""

    VERILOG = """\
module top(input a, input b, output y1, output y2, output y3);
  nand u1(y1, a, b);
  nor  u2(y2, a, b);
  xor  u3(y3, a, b);
endmodule
"""

    @pytest.fixture
    def graph(self):
        return _parse_verilog(self.VERILOG)

    def test_primitives(self, graph):
        assert graph.get_gate("top.u1").cell_type == "nand"
        assert graph.get_gate("top.u2").cell_type == "nor"
        assert graph.get_gate("top.u3").cell_type == "xor"
