"""Tests for the fast regex-based netlist parser."""

import tempfile
import os

import pytest

from src.netlist.fast_parser import parse_netlist_fast


def _write_netlist(content: str) -> str:
    """Write netlist content to a temp file and return its path."""
    fd, path = tempfile.mkstemp(suffix='.v', dir=os.environ.get('TMPDIR', '/tmp'))
    with os.fdopen(fd, 'w') as f:
        f.write(content)
    return path


class TestFastParserBasic:
    """Basic netlist with simple module instantiations."""

    def test_single_gate(self):
        path = _write_netlist("""
module top (A, B, Y);
  input A, B;
  output Y;
  wire n1;
  AND2 u0 (.A(A), .B(B), .Y(n1));
endmodule
""")
        try:
            graph = parse_netlist_fast([path])
            gate = graph.get_gate('top.u0')
            assert gate is not None
            assert gate.cell_type == 'AND2'
            assert 'A' in gate.inputs
            assert 'B' in gate.inputs
            assert 'Y' in gate.outputs
        finally:
            os.unlink(path)

    def test_multiple_gates(self):
        path = _write_netlist("""
module top (A, B, C, Y);
  input A, B, C;
  output Y;
  wire n1, n2;
  AND2 u0 (.A(A), .B(B), .Y(n1));
  OR2 u1 (.A(n1), .B(C), .Y(n2));
  INV u2 (.A(n2), .Y(Y));
endmodule
""")
        try:
            graph = parse_netlist_fast([path])
            assert graph.get_gate('top.u0') is not None
            assert graph.get_gate('top.u1') is not None
            assert graph.get_gate('top.u2') is not None
            assert graph.get_gate('top.u0').cell_type == 'AND2'
            assert graph.get_gate('top.u1').cell_type == 'OR2'
            assert graph.get_gate('top.u2').cell_type == 'INV'
        finally:
            os.unlink(path)

    def test_signal_connectivity(self):
        path = _write_netlist("""
module top (A, B, Y);
  input A, B;
  output Y;
  wire n1;
  AND2 u0 (.A(A), .B(B), .Y(n1));
  INV u1 (.A(n1), .Y(Y));
endmodule
""")
        try:
            graph = parse_netlist_fast([path])
            # n1 is driven by u0
            drivers = graph.get_drivers('top.n1')
            assert len(drivers) == 1
            assert drivers[0].instance_path == 'top.u0'
            # n1 feeds into u1
            fanout = graph.get_fanout('top.n1')
            assert len(fanout) == 1
            assert fanout[0].instance_path == 'top.u1'
        finally:
            os.unlink(path)


class TestFastParserEscapedIdentifiers:
    """Test parsing of escaped identifiers (\\name )."""

    def test_escaped_instance_name(self):
        path = _write_netlist("""
module top (A, B, Y);
  input A, B;
  output Y;
  AND2 \\u0_inst (.A(A), .B(B), .Y(Y));
endmodule
""")
        try:
            graph = parse_netlist_fast([path])
            gate = graph.get_gate('top.u0_inst')
            assert gate is not None
            assert gate.cell_type == 'AND2'
        finally:
            os.unlink(path)

    def test_escaped_signal_name(self):
        path = _write_netlist("""
module top (Y);
  output Y;
  wire \\net/abc ;
  INV u0 (.A(\\net/abc ), .Y(Y));
endmodule
""")
        try:
            graph = parse_netlist_fast([path])
            gate = graph.get_gate('top.u0')
            assert gate is not None
            assert 'A' in gate.inputs
            # Escaped signal should have backslash stripped and be prefixed with module
            pin = gate.inputs['A']
            assert 'net/abc' in pin.signal
        finally:
            os.unlink(path)


class TestFastParserMultiLine:
    """Test parsing of multi-line cell instantiations."""

    def test_multiline_instance(self):
        path = _write_netlist("""
module top (A, B, C, Y);
  input A, B, C;
  output Y;
  AOI21 u0 (.A1(A),
     .A2(B),
     .B1(C),
     .ZN(Y));
endmodule
""")
        try:
            graph = parse_netlist_fast([path])
            gate = graph.get_gate('top.u0')
            assert gate is not None
            assert gate.cell_type == 'AOI21'
            assert 'A1' in gate.inputs
            assert 'A2' in gate.inputs
            assert 'B1' in gate.inputs
        finally:
            os.unlink(path)

    def test_multiline_many_ports(self):
        path = _write_netlist("""
module top (A, B, C, D, Y);
  input A, B, C, D;
  output Y;
  OAI22 u0 (.A1(A),
     .A2(B),
     .B1(C),
     .B2(D),
     .ZN(Y));
endmodule
""")
        try:
            graph = parse_netlist_fast([path])
            gate = graph.get_gate('top.u0')
            assert gate is not None
            assert gate.cell_type == 'OAI22'
            assert len(gate.inputs) == 4
        finally:
            os.unlink(path)


class TestFastParserPowerGround:
    """Test that VDD/VSS power/ground ports are filtered out."""

    def test_pg_ports_filtered(self):
        path = _write_netlist("""
module top (A, B, Y);
  input A, B;
  output Y;
  AND2 u0 (.A(A), .B(B), .Y(Y), .VDD(VDD), .VSS(VSS));
endmodule
""")
        try:
            graph = parse_netlist_fast([path])
            gate = graph.get_gate('top.u0')
            assert gate is not None
            # VDD and VSS should not appear in inputs or outputs
            all_ports = set(gate.inputs.keys()) | set(gate.outputs.keys())
            assert 'VDD' not in all_ports
            assert 'VSS' not in all_ports
        finally:
            os.unlink(path)

    def test_vnw_vpw_filtered(self):
        path = _write_netlist("""
module top (A, Y);
  input A;
  output Y;
  INV u0 (.A(A), .Y(Y), .VNW(VDD), .VPW(VSS));
endmodule
""")
        try:
            graph = parse_netlist_fast([path])
            gate = graph.get_gate('top.u0')
            assert gate is not None
            all_ports = set(gate.inputs.keys()) | set(gate.outputs.keys())
            assert 'VNW' not in all_ports
            assert 'VPW' not in all_ports
        finally:
            os.unlink(path)


class TestFastParserSequentialDetection:
    """Test sequential cell (DFF) detection with CLK/D/Q/RST ports."""

    def test_dff_sequential_detection(self):
        path = _write_netlist("""
module top (CLK, D, Q, RST);
  input CLK, D, RST;
  output Q;
  DFFR u_ff (.CLK(CLK), .D(D), .Q(Q), .RST(RST));
endmodule
""")
        try:
            graph = parse_netlist_fast([path])
            gate = graph.get_gate('top.u_ff')
            assert gate is not None
            assert gate.is_sequential is True
            assert gate.clock_port == 'CLK'
            assert gate.d_port == 'D'
            assert gate.q_port == 'Q'
            assert gate.reset_port == 'RST'
        finally:
            os.unlink(path)

    def test_dff_with_set(self):
        path = _write_netlist("""
module top (CK, D, Q, SET);
  input CK, D, SET;
  output Q;
  DFFSET u_ff (.CK(CK), .D(D), .Q(Q), .SET(SET));
endmodule
""")
        try:
            graph = parse_netlist_fast([path])
            gate = graph.get_gate('top.u_ff')
            assert gate is not None
            assert gate.is_sequential is True
            assert gate.clock_port == 'CK'
            assert gate.d_port == 'D'
            assert gate.q_port == 'Q'
            assert gate.set_port == 'SET'
        finally:
            os.unlink(path)

    def test_non_sequential_not_flagged(self):
        path = _write_netlist("""
module top (A, B, Y);
  input A, B;
  output Y;
  AND2 u0 (.A(A), .B(B), .Y(Y));
endmodule
""")
        try:
            graph = parse_netlist_fast([path])
            gate = graph.get_gate('top.u0')
            assert gate is not None
            assert gate.is_sequential is False
        finally:
            os.unlink(path)


class TestFastParserHierarchy:
    """Test sub-module instantiation and hierarchy remapping."""

    def test_submodule_remapping(self):
        path = _write_netlist("""
module sub_mod (A, B, Y);
  input A, B;
  output Y;
  AND2 u0 (.A(A), .B(B), .Y(Y));
endmodule

module top (X, Z, OUT);
  input X, Z;
  output OUT;
  sub_mod inst_a (.A(X), .B(Z), .Y(OUT));
endmodule
""")
        try:
            graph = parse_netlist_fast([path], top_module='top')
            # The gate inside sub_mod should be remapped from
            # sub_mod.u0 to top.inst_a.u0
            gate = graph.get_gate('top.inst_a.u0')
            assert gate is not None
            assert gate.cell_type == 'AND2'
        finally:
            os.unlink(path)

    def test_hierarchy_auto_detect_top(self):
        path = _write_netlist("""
module leaf (A, Y);
  input A;
  output Y;
  INV u0 (.A(A), .Y(Y));
endmodule

module wrapper (IN, OUT);
  input IN;
  output OUT;
  leaf inst_leaf (.A(IN), .Y(OUT));
endmodule
""")
        try:
            # Auto-detect top: wrapper is never instantiated so it is the top
            graph = parse_netlist_fast([path])
            gate = graph.get_gate('wrapper.inst_leaf.u0')
            assert gate is not None
            assert gate.cell_type == 'INV'
        finally:
            os.unlink(path)


class TestFastParserAssign:
    """Test parsing of assign statements."""

    def test_simple_assign(self):
        path = _write_netlist("""
module top (A, Y);
  input A;
  output Y;
  assign Y = A;
endmodule
""")
        try:
            graph = parse_netlist_fast([path])
            # assign creates a gate with cell_type 'assign'
            # The instance path is __assign__<signal>
            drivers = graph.get_drivers('top.Y')
            assert len(drivers) >= 1
            assign_gate = drivers[0]
            assert assign_gate.cell_type == 'assign'
            assert 'A' in assign_gate.inputs
            assert 'Y' in assign_gate.outputs
        finally:
            os.unlink(path)

    def test_assign_with_bus(self):
        path = _write_netlist("""
module top (A, Y);
  input A;
  output [0:0] Y;
  assign Y[0] = A;
endmodule
""")
        try:
            graph = parse_netlist_fast([path])
            # Should have parsed the assign
            gates = [g for g in graph._gates.values() if g.cell_type == 'assign']
            assert len(gates) >= 1
        finally:
            os.unlink(path)
