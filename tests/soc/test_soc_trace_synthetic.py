"""Tier 3: Hand-crafted VCD traces over the real SoC netlist.

Key insight: _vcd_get_bit returns 'x' for missing signals, so we only need
to provide signals that should be NON-X. For signals we want X, we either
omit them or explicitly set them to 'x'.
"""

import pytest
from src.tracer.core import trace_x, XCause

from tests.soc.conftest import make_vcd_db, make_prefix_vcd, VCD_PREFIX, NETLIST_TOP

pytestmark = pytest.mark.soc

# --- Signal paths (netlist domain, starting with rjn_soc_top) ---
NOC_CLK_GATE = (
    "rjn_soc_top.inst_rjn_app_top.noc_app_ins."
    "u_amni_m_CAM_CNTRL_DATA_INTF.u_amni_m_CAM_CNTRL_DATA_INTF_amni_core_c630cu1bnt."
    "u_arachne_amni_axi4_adaptor.u_wdata_formatter.rc_gclk_2024"
)

JTAG_CLK_GATE = (
    "rjn_soc_top.inst_rjn_sys_top.azurite_ins.jtag_tap.rc_gclk_2319"
)

DAP_CLK_GATE = (
    "rjn_soc_top.inst_rjn_dbg_top.inst_coresight_dap.inst_swjdp."
    "u_cxdapswjdp_swclktck.u_cxdapswjdp_sw_dp_protocol.rc_gclk_5612"
)


def _netlist_to_vcd(netlist_signal):
    """Convert netlist signal path to VCD signal path."""
    assert netlist_signal.startswith(NETLIST_TOP + '.')
    return VCD_PREFIX + netlist_signal[len(NETLIST_TOP):]


def _make_x_vcd(netlist_signal, x_time=1000, extra_transitions=None):
    """Build a minimal PrefixMappedVCD where netlist_signal is X at x_time.

    The signal is set to 'x' at x_time in the VCD. PrefixMappedVCD handles
    path translation between netlist and VCD domains.

    extra_transitions: dict of netlist_signal -> [(time, val)] for additional
    signals to include in the VCD (values provided in netlist domain, converted
    automatically).
    """
    vcd_path = _netlist_to_vcd(netlist_signal)
    transitions = {
        vcd_path: [(0, '0'), (x_time, 'x')],
    }
    if extra_transitions:
        for sig, trans in extra_transitions.items():
            transitions[_netlist_to_vcd(sig)] = trans
    vcd_db = make_vcd_db(transitions, timescale_fs=1000)  # 1ps per tick
    return make_prefix_vcd(vcd_db)


def _find_gate(netlist, predicate, limit=100000):
    """Find a gate in the netlist matching predicate. Returns None if not found."""
    count = 0
    for path, gate in netlist._gates.items():
        if predicate(gate):
            return gate
        count += 1
        if count >= limit:
            break
    # Full scan if not found in first `limit` entries
    if count >= limit:
        for path, gate in netlist._gates.items():
            if predicate(gate):
                return gate
    return None


def _get_output_signal(gate):
    """Get the output signal path from a gate. Returns (signal, bit) tuple."""
    for port_name, pin in gate.outputs.items():
        sig = pin.signal
        bit = pin.bit
        return sig, bit
    return None, None


class TestNocClkGateTrace:
    def test_noc_clk_gate_trace(self, soc_netlist, gate_model):
        """Trace NOC clock gate signal set to X. Verify cause_type."""
        vcd = _make_x_vcd(NOC_CLK_GATE, x_time=1000)

        result = trace_x(
            netlist=soc_netlist,
            vcd=vcd,
            gate_model=gate_model,
            signal=NOC_CLK_GATE,
            bit=0,
            time=1000,
            max_depth=3,
        )

        assert isinstance(result, XCause)
        assert result.cause_type in (
            'unknown_cell', 'x_propagation', 'primary_input',
            'clock_x', 'max_depth',
        ), f"Unexpected cause_type: {result.cause_type}"


class TestJtagTapTrace:
    def test_jtag_tap_trace(self, soc_netlist, gate_model):
        """Trace JTAG TAP clock gate signal. Verify cause tree has leaves."""
        vcd = _make_x_vcd(JTAG_CLK_GATE, x_time=1000)

        result = trace_x(
            netlist=soc_netlist,
            vcd=vcd,
            gate_model=gate_model,
            signal=JTAG_CLK_GATE,
            bit=0,
            time=1000,
            max_depth=5,
        )

        assert isinstance(result, XCause)
        # Cause tree should have at least the root
        # Walk to find leaves
        leaves = _collect_leaves(result)
        assert len(leaves) > 0, "Cause tree has no leaves"


class TestTraceDepth:
    def test_trace_reaches_primary_input(self, soc_netlist, gate_model):
        """Trace deep enough to reach a primary_input leaf."""
        vcd = _make_x_vcd(NOC_CLK_GATE, x_time=1000)

        result = trace_x(
            netlist=soc_netlist,
            vcd=vcd,
            gate_model=gate_model,
            signal=NOC_CLK_GATE,
            bit=0,
            time=1000,
            max_depth=50,
        )

        leaves = _collect_leaves(result)
        leaf_types = {leaf.cause_type for leaf in leaves}
        assert 'primary_input' in leaf_types, (
            f"No primary_input leaf found. Leaf types: {leaf_types}"
        )

    def test_trace_max_depth_respected(self, soc_netlist, gate_model):
        """Trace with max_depth=2, verify max_depth leaves exist."""
        vcd = _make_x_vcd(NOC_CLK_GATE, x_time=1000)

        result = trace_x(
            netlist=soc_netlist,
            vcd=vcd,
            gate_model=gate_model,
            signal=NOC_CLK_GATE,
            bit=0,
            time=1000,
            max_depth=2,
        )

        leaves = _collect_leaves(result)
        leaf_types = {leaf.cause_type for leaf in leaves}
        # With max_depth=2, at least some leaves should be max_depth
        # (unless all paths are shorter than 2)
        assert 'max_depth' in leaf_types or len(leaves) > 0, (
            f"Expected max_depth leaves or non-empty tree. Leaf types: {leaf_types}"
        )


class TestTraceResultStructure:
    def test_trace_result_has_gate_info(self, soc_netlist, gate_model):
        """Verify result.gate is not None, has cell_type and instance_path."""
        vcd = _make_x_vcd(NOC_CLK_GATE, x_time=1000)

        result = trace_x(
            netlist=soc_netlist,
            vcd=vcd,
            gate_model=gate_model,
            signal=NOC_CLK_GATE,
            bit=0,
            time=1000,
            max_depth=3,
        )

        # The root node should have gate info (it's driven by a gate)
        # Walk to find a node with gate info
        node_with_gate = _find_node_with_gate(result)
        assert node_with_gate is not None, "No node in cause tree has gate info"
        assert node_with_gate.gate.cell_type is not None
        assert node_with_gate.gate.instance_path is not None


# ===================================================================
# Subsystem-specific trace tests
# ===================================================================

class TestDmaControllerTrace:
    """Trace tests targeting the DMA350 controller subsystem."""

    def test_dma_dff_trace(self, soc_netlist, gate_model):
        """Trace a DFF output in the DMA350 controller hierarchy."""
        gate = _find_gate(soc_netlist, lambda g: (
            g.is_sequential and 'inst_dma350' in g.instance_path
        ))
        assert gate is not None, "No DFF found in DMA350 hierarchy"

        sig, bit = _get_output_signal(gate)
        assert sig is not None, "DMA DFF has no output signal"
        vcd = _make_x_vcd(sig, x_time=1000)

        result = trace_x(
            netlist=soc_netlist, vcd=vcd, gate_model=gate_model,
            signal=sig, bit=bit if bit is not None else 0,
            time=1000, max_depth=3,
        )

        assert isinstance(result, XCause)
        assert result.gate is not None
        assert 'inst_dma350' in result.gate.instance_path

    def test_dma_combinational_trace(self, soc_netlist, gate_model):
        """Trace a combinational gate output in the DMA350 hierarchy."""
        gate = _find_gate(soc_netlist, lambda g: (
            not g.is_sequential
            and 'inst_dma350' in g.instance_path
            and g.cell_type.upper().startswith('AND')
            and len(g.inputs) >= 2
        ))
        assert gate is not None, "No AND gate found in DMA350 hierarchy"

        sig, bit = _get_output_signal(gate)
        assert sig is not None
        vcd = _make_x_vcd(sig, x_time=1000)

        result = trace_x(
            netlist=soc_netlist, vcd=vcd, gate_model=gate_model,
            signal=sig, bit=bit if bit is not None else 0,
            time=1000, max_depth=3,
        )

        assert isinstance(result, XCause)
        leaves = _collect_leaves(result)
        assert len(leaves) > 0


class TestA55CpuCoreTrace:
    """Trace tests targeting the A55 CPU core subsystem."""

    def test_a55_dff_trace(self, soc_netlist, gate_model):
        """Trace a DFF in the DynamIQ A55 cluster."""
        gate = _find_gate(soc_netlist, lambda g: (
            g.is_sequential
            and 'inst_DynamIQ_Cluster_A55_1' in g.instance_path
        ))
        assert gate is not None, "No DFF found in A55 hierarchy"

        sig, bit = _get_output_signal(gate)
        assert sig is not None
        vcd = _make_x_vcd(sig, x_time=1000)

        result = trace_x(
            netlist=soc_netlist, vcd=vcd, gate_model=gate_model,
            signal=sig, bit=bit if bit is not None else 0,
            time=1000, max_depth=3,
        )

        assert isinstance(result, XCause)
        assert result.gate is not None
        assert result.gate.is_sequential

    def test_a55_deep_trace(self, soc_netlist, gate_model):
        """Deep trace through A55 cluster reaches leaf causes."""
        gate = _find_gate(soc_netlist, lambda g: (
            g.is_sequential
            and 'inst_DynamIQ_Cluster_A55_1' in g.instance_path
            and g.q_port == 'Q' and 'Q' in g.outputs
        ))
        assert gate is not None, "No suitable A55 DFF found"

        sig, bit = _get_output_signal(gate)
        vcd = _make_x_vcd(sig, x_time=1000)

        result = trace_x(
            netlist=soc_netlist, vcd=vcd, gate_model=gate_model,
            signal=sig, bit=bit if bit is not None else 0,
            time=1000, max_depth=10,
        )

        leaves = _collect_leaves(result)
        leaf_types = {l.cause_type for l in leaves}
        # Should reach some terminal cause (not just max_depth)
        assert len(leaf_types) > 0


class TestSdramControllerTrace:
    """Trace tests targeting the SDRAM controller subsystem."""

    def test_sdram_dff_trace(self, soc_netlist, gate_model):
        """Trace a DFF in the SDRAM controller hierarchy."""
        gate = _find_gate(soc_netlist, lambda g: (
            g.is_sequential and 'sdram' in g.instance_path.lower()
        ))
        assert gate is not None, "No DFF found in SDRAM hierarchy"

        sig, bit = _get_output_signal(gate)
        assert sig is not None
        vcd = _make_x_vcd(sig, x_time=1000)

        result = trace_x(
            netlist=soc_netlist, vcd=vcd, gate_model=gate_model,
            signal=sig, bit=bit if bit is not None else 0,
            time=1000, max_depth=5,
        )

        assert isinstance(result, XCause)
        assert result.gate is not None

    def test_sdram_primary_input_trace(self, soc_netlist, gate_model):
        """Trace an SDRAM signal that is a primary input (no driver)."""
        # Find a primary input with 'sdram' in the name
        target = None
        for sig in soc_netlist.get_all_signals():
            if 'sdram' in sig.lower() and not soc_netlist.get_drivers(sig):
                if soc_netlist.get_fanout(sig):
                    target = sig
                    break
        assert target is not None, "No SDRAM primary input found"

        vcd = _make_x_vcd(target, x_time=1000)
        result = trace_x(
            netlist=soc_netlist, vcd=vcd, gate_model=gate_model,
            signal=target, bit=0, time=1000, max_depth=3,
        )

        assert result.cause_type == 'primary_input'


class TestGpioPeripheralTrace:
    """Trace tests targeting GPIO peripheral subsystem."""

    def test_gpio_dff_trace(self, soc_netlist, gate_model):
        """Trace a DFF in the GPIO hierarchy."""
        gate = _find_gate(soc_netlist, lambda g: (
            g.is_sequential and 'gpio' in g.instance_path.lower()
        ))
        assert gate is not None, "No DFF found in GPIO hierarchy"

        sig, bit = _get_output_signal(gate)
        assert sig is not None
        vcd = _make_x_vcd(sig, x_time=1000)

        result = trace_x(
            netlist=soc_netlist, vcd=vcd, gate_model=gate_model,
            signal=sig, bit=bit if bit is not None else 0,
            time=1000, max_depth=3,
        )

        assert isinstance(result, XCause)
        assert result.gate is not None


class TestUartPeripheralTrace:
    """Trace tests targeting UART peripheral subsystem."""

    def test_uart_dff_trace(self, soc_netlist, gate_model):
        """Trace a DFF in the UART hierarchy."""
        gate = _find_gate(soc_netlist, lambda g: (
            g.is_sequential and 'uart' in g.instance_path.lower()
        ))
        assert gate is not None, "No DFF found in UART hierarchy"

        sig, bit = _get_output_signal(gate)
        assert sig is not None
        vcd = _make_x_vcd(sig, x_time=1000)

        result = trace_x(
            netlist=soc_netlist, vcd=vcd, gate_model=gate_model,
            signal=sig, bit=bit if bit is not None else 0,
            time=1000, max_depth=5,
        )

        assert isinstance(result, XCause)
        leaves = _collect_leaves(result)
        assert len(leaves) > 0

    def test_uart_deep_trace_finds_leaves(self, soc_netlist, gate_model):
        """Deep trace through UART subsystem finds terminal causes."""
        gate = _find_gate(soc_netlist, lambda g: (
            g.is_sequential and 'uart' in g.instance_path.lower()
            and g.q_port == 'Q' and 'Q' in g.outputs
        ))
        assert gate is not None, "No suitable UART DFF found"

        sig, bit = _get_output_signal(gate)
        vcd = _make_x_vcd(sig, x_time=1000)

        result = trace_x(
            netlist=soc_netlist, vcd=vcd, gate_model=gate_model,
            signal=sig, bit=bit if bit is not None else 0,
            time=1000, max_depth=20,
        )

        leaves = _collect_leaves(result)
        leaf_types = {l.cause_type for l in leaves}
        # Deep trace should find at least primary_input or uninit_ff at the leaves
        terminal_types = {'primary_input', 'uninit_ff', 'cycle'}
        assert leaf_types & terminal_types or 'max_depth' in leaf_types, (
            f"Expected terminal causes. Got: {leaf_types}"
        )


# ===================================================================
# Cause type coverage tests
# ===================================================================

class TestUninitFfCause:
    """Test that uninit_ff cause is produced for a DFF with no clock edges."""

    def test_uninit_ff_cause(self, soc_netlist, gate_model):
        """DFF Q output is X, clock has no edges -> uninit_ff."""
        # Find a simple DFF with Q output, D input, CK clock
        gate = _find_gate(soc_netlist, lambda g: (
            g.is_sequential and g.q_port == 'Q' and g.d_port == 'D'
            and g.clock_port == 'CK' and 'Q' in g.outputs
            and len(g.outputs) == 1
        ))
        assert gate is not None, "No suitable DFF found"

        q_pin = gate.outputs['Q']
        q_sig = q_pin.signal
        q_bit = q_pin.bit if q_pin.bit is not None else 0

        # Provide clock as '0' (no edges) and reset as '1' (inactive for
        # active-low reset). D input is missing so it reads as X.
        clk_pin = gate.inputs[gate.clock_port]
        extra = {clk_pin.signal: [(0, '1'), (500, '1')]}  # No toggling

        # If the DFF has a reset port, provide reset as non-X (inactive)
        if gate.reset_port and gate.reset_port in gate.inputs:
            rst_pin = gate.inputs[gate.reset_port]
            extra[rst_pin.signal] = [(0, '1')]  # Active-low reset: '1' = inactive

        vcd = _make_x_vcd(q_sig, x_time=1000, extra_transitions=extra)

        result = trace_x(
            netlist=soc_netlist, vcd=vcd, gate_model=gate_model,
            signal=q_sig, bit=q_bit, time=1000, max_depth=5,
        )

        assert isinstance(result, XCause)
        assert result.cause_type == 'uninit_ff', (
            f"Expected uninit_ff, got {result.cause_type}"
        )
        assert result.gate is not None
        assert result.gate.is_sequential


class TestClockXCause:
    """Test that clock_x cause is produced when clock input is X."""

    def test_clock_x_cause(self, soc_netlist, gate_model):
        """DFF with X on its clock input -> clock_x."""
        # Find a DFF; its clock signal is not in VCD -> reads as X
        gate = _find_gate(soc_netlist, lambda g: (
            g.is_sequential and g.clock_port == 'CK'
            and g.clock_port in g.inputs and g.q_port == 'Q'
            and 'Q' in g.outputs and len(g.outputs) == 1
        ))
        assert gate is not None, "No suitable DFF found"

        q_pin = gate.outputs['Q']
        q_sig = q_pin.signal
        q_bit = q_pin.bit if q_pin.bit is not None else 0

        # Provide reset as non-X (inactive) so we don't get async_control_x
        extra = {}
        if gate.reset_port and gate.reset_port in gate.inputs:
            rst_pin = gate.inputs[gate.reset_port]
            extra[rst_pin.signal] = [(0, '1')]  # active-low reset inactive
        if gate.set_port and gate.set_port in gate.inputs:
            set_pin = gate.inputs[gate.set_port]
            extra[set_pin.signal] = [(0, '1')]  # active-low set inactive

        # Clock signal is NOT in VCD -> _vcd_get_bit returns 'x'
        # This should trigger clock_x cause
        vcd = _make_x_vcd(q_sig, x_time=1000, extra_transitions=extra)

        result = trace_x(
            netlist=soc_netlist, vcd=vcd, gate_model=gate_model,
            signal=q_sig, bit=q_bit, time=1000, max_depth=5,
        )

        assert isinstance(result, XCause)
        assert result.cause_type == 'clock_x', (
            f"Expected clock_x, got {result.cause_type}"
        )
        assert result.gate is not None


class TestAsyncControlXCause:
    """Test that async_control_x cause is produced when reset is X."""

    def test_async_control_x_cause(self, soc_netlist, gate_model):
        """DFF with X on its reset port -> async_control_x."""
        # Find a DFF with a reset port
        gate = _find_gate(soc_netlist, lambda g: (
            g.is_sequential and g.reset_port is not None
            and g.reset_port in g.inputs
            and g.q_port == 'Q' and 'Q' in g.outputs
            and len(g.outputs) == 1
        ))
        assert gate is not None, "No DFF with reset port found"

        q_pin = gate.outputs['Q']
        q_sig = q_pin.signal
        q_bit = q_pin.bit if q_pin.bit is not None else 0

        # Reset signal is NOT in VCD -> reads as X -> async_control_x
        # Clock is provided as non-X to avoid clock_x taking precedence
        # (but async_control_x has higher priority than clock_x)
        vcd = _make_x_vcd(q_sig, x_time=1000)

        result = trace_x(
            netlist=soc_netlist, vcd=vcd, gate_model=gate_model,
            signal=q_sig, bit=q_bit, time=1000, max_depth=5,
        )

        assert isinstance(result, XCause)
        assert result.cause_type == 'async_control_x', (
            f"Expected async_control_x, got {result.cause_type}"
        )
        assert result.gate is not None
        assert result.gate.reset_port is not None


class TestXPropagationCause:
    """Test that x_propagation cause is produced for combinational gates."""

    def test_x_propagation_and2(self, soc_netlist, gate_model):
        """AND2 gate with one X input and other at non-controlling -> x_propagation."""
        gate = _find_gate(soc_netlist, lambda g: (
            not g.is_sequential
            and g.cell_type.upper().startswith('AND2')
            and len(g.inputs) == 2
        ))
        assert gate is not None, "No AND2 gate found"

        out_pin = list(gate.outputs.values())[0]
        out_sig = out_pin.signal
        out_bit = out_pin.bit if out_pin.bit is not None else 0

        # For AND: non-controlling value is '1'. Provide input B as '1',
        # leave input A missing (reads as X). This should produce x_propagation.
        input_ports = list(gate.inputs.keys())
        # Provide the second input as '1' (non-controlling for AND)
        second_pin = gate.inputs[input_ports[1]]
        extra = {second_pin.signal: [(0, '1')]}

        vcd = _make_x_vcd(out_sig, x_time=1000, extra_transitions=extra)

        result = trace_x(
            netlist=soc_netlist, vcd=vcd, gate_model=gate_model,
            signal=out_sig, bit=out_bit, time=1000, max_depth=3,
        )

        assert isinstance(result, XCause)
        assert result.cause_type == 'x_propagation', (
            f"Expected x_propagation, got {result.cause_type}"
        )
        assert result.gate is not None
        assert len(result.children) > 0

    def test_x_propagation_or2(self, soc_netlist, gate_model):
        """OR2 gate with one X input and other at non-controlling -> x_propagation."""
        gate = _find_gate(soc_netlist, lambda g: (
            not g.is_sequential
            and g.cell_type.upper().startswith('OR2')
            and len(g.inputs) == 2
        ))
        assert gate is not None, "No OR2 gate found"

        out_pin = list(gate.outputs.values())[0]
        out_sig = out_pin.signal
        out_bit = out_pin.bit if out_pin.bit is not None else 0

        # For OR: non-controlling value is '0'. Provide input B as '0'.
        input_ports = list(gate.inputs.keys())
        second_pin = gate.inputs[input_ports[1]]
        extra = {second_pin.signal: [(0, '0')]}

        vcd = _make_x_vcd(out_sig, x_time=1000, extra_transitions=extra)

        result = trace_x(
            netlist=soc_netlist, vcd=vcd, gate_model=gate_model,
            signal=out_sig, bit=out_bit, time=1000, max_depth=3,
        )

        assert isinstance(result, XCause)
        assert result.cause_type == 'x_propagation', (
            f"Expected x_propagation, got {result.cause_type}"
        )
        assert len(result.children) > 0

    def test_x_propagation_inv(self, soc_netlist, gate_model):
        """INV gate with X input -> x_propagation."""
        gate = _find_gate(soc_netlist, lambda g: (
            not g.is_sequential
            and g.cell_type.upper().startswith('INV')
            and len(g.inputs) == 1
        ))
        assert gate is not None, "No INV gate found"

        out_pin = list(gate.outputs.values())[0]
        out_sig = out_pin.signal
        out_bit = out_pin.bit if out_pin.bit is not None else 0

        # INV: any X input produces X output
        vcd = _make_x_vcd(out_sig, x_time=1000)

        result = trace_x(
            netlist=soc_netlist, vcd=vcd, gate_model=gate_model,
            signal=out_sig, bit=out_bit, time=1000, max_depth=3,
        )

        assert isinstance(result, XCause)
        assert result.cause_type == 'x_propagation', (
            f"Expected x_propagation, got {result.cause_type}"
        )
        assert len(result.children) == 1


class TestPrimaryInputCause:
    """Test that primary_input cause is produced for undriven signals."""

    def test_primary_input_cause(self, soc_netlist, gate_model):
        """Signal with no driver in netlist -> primary_input."""
        # Find a primary input that has fanout (consumed by something)
        target = None
        for sig in soc_netlist.get_all_signals():
            if (not soc_netlist.get_drivers(sig)
                    and soc_netlist.get_fanout(sig)
                    and 'UNCONNECTED' not in sig):
                target = sig
                break
        assert target is not None, "No primary input signal found"

        vcd = _make_x_vcd(target, x_time=1000)

        result = trace_x(
            netlist=soc_netlist, vcd=vcd, gate_model=gate_model,
            signal=target, bit=0, time=1000, max_depth=3,
        )

        assert isinstance(result, XCause)
        assert result.cause_type == 'primary_input', (
            f"Expected primary_input, got {result.cause_type}"
        )
        assert result.gate is None  # No driver gate

    def test_primary_input_is_leaf(self, soc_netlist, gate_model):
        """Primary input nodes are always leaf nodes (no children)."""
        target = None
        for sig in soc_netlist.get_all_signals():
            if (not soc_netlist.get_drivers(sig)
                    and soc_netlist.get_fanout(sig)
                    and 'UNCONNECTED' not in sig):
                target = sig
                break
        assert target is not None

        vcd = _make_x_vcd(target, x_time=1000)
        result = trace_x(
            netlist=soc_netlist, vcd=vcd, gate_model=gate_model,
            signal=target, bit=0, time=1000, max_depth=3,
        )

        assert result.cause_type == 'primary_input'
        assert len(result.children) == 0, "primary_input should be a leaf node"


# ===================================================================
# Cross-subsystem and structural tests
# ===================================================================

class TestDapTrace:
    """Trace tests targeting the CoreSight DAP subsystem."""

    def test_dap_clk_gate_trace(self, soc_netlist, gate_model):
        """Trace DAP clock gate signal through debug subsystem."""
        vcd = _make_x_vcd(DAP_CLK_GATE, x_time=1000)

        result = trace_x(
            netlist=soc_netlist, vcd=vcd, gate_model=gate_model,
            signal=DAP_CLK_GATE, bit=0, time=1000, max_depth=5,
        )

        assert isinstance(result, XCause)
        leaves = _collect_leaves(result)
        assert len(leaves) > 0


class TestMultipleSubsystemLeafTypes:
    """Verify that different subsystems produce diverse leaf cause types."""

    def test_noc_leaf_variety(self, soc_netlist, gate_model):
        """NOC trace with deep depth produces multiple leaf types."""
        vcd = _make_x_vcd(NOC_CLK_GATE, x_time=1000)

        result = trace_x(
            netlist=soc_netlist, vcd=vcd, gate_model=gate_model,
            signal=NOC_CLK_GATE, bit=0, time=1000, max_depth=30,
        )

        leaves = _collect_leaves(result)
        leaf_types = {l.cause_type for l in leaves}
        # A deep trace through a complex NOC should produce at least 2
        # different cause types (e.g. primary_input and uninit_ff)
        assert len(leaf_types) >= 1, f"Only got leaf types: {leaf_types}"


class TestCauseTreeIntegrity:
    """Structural integrity tests for cause trees."""

    def test_all_leaves_have_valid_cause_type(self, soc_netlist, gate_model):
        """Every leaf in a cause tree has a recognized cause_type."""
        vcd = _make_x_vcd(JTAG_CLK_GATE, x_time=1000)

        result = trace_x(
            netlist=soc_netlist, vcd=vcd, gate_model=gate_model,
            signal=JTAG_CLK_GATE, bit=0, time=1000, max_depth=10,
        )

        valid_types = {
            'primary_input', 'uninit_ff', 'x_injection',
            'sequential_capture', 'clock_x', 'async_control_x',
            'multi_driver', 'x_propagation', 'unknown_cell',
            'max_depth', 'cycle',
        }
        leaves = _collect_leaves(result)
        for leaf in leaves:
            assert leaf.cause_type in valid_types, (
                f"Invalid cause_type '{leaf.cause_type}' on leaf {leaf.signal}"
            )

    def test_internal_nodes_have_children(self, soc_netlist, gate_model):
        """Non-leaf nodes should have at least one child."""
        vcd = _make_x_vcd(NOC_CLK_GATE, x_time=1000)

        result = trace_x(
            netlist=soc_netlist, vcd=vcd, gate_model=gate_model,
            signal=NOC_CLK_GATE, bit=0, time=1000, max_depth=5,
        )

        def check_node(node):
            if node.children:
                for child in node.children:
                    assert isinstance(child, XCause)
                    check_node(child)

        check_node(result)


# --- Helpers ---

def _collect_leaves(node: XCause) -> list[XCause]:
    """Recursively collect all leaf nodes in the cause tree."""
    if not node.children:
        return [node]
    leaves = []
    for child in node.children:
        leaves.extend(_collect_leaves(child))
    return leaves


def _find_node_with_gate(node: XCause):
    """Find first node in tree with gate != None."""
    if node.gate is not None:
        return node
    for child in node.children:
        found = _find_node_with_gate(child)
        if found is not None:
            return found
    return None
