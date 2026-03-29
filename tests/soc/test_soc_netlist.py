"""Tier 2: SoC netlist-only tests — validate parsing of a real 3.3M-gate netlist."""

import pytest

pytestmark = pytest.mark.soc

# --- Signals used across multiple tests ---
NOC_SIGNAL = (
    "rjn_soc_top.inst_rjn_app_top.noc_app_ins."
    "u_amni_m_CAM_CNTRL_DATA_INTF.u_amni_m_CAM_CNTRL_DATA_INTF_amni_core_c630cu1bnt."
    "u_arachne_amni_axi4_adaptor.u_wdata_formatter.rc_gclk_2024"
)

JTAG_SIGNAL = (
    "rjn_soc_top.inst_rjn_sys_top.azurite_ins.jtag_tap.rc_gclk_2319"
)

DAP_SIGNAL = (
    "rjn_soc_top.inst_rjn_dbg_top.inst_coresight_dap.inst_swjdp."
    "u_cxdapswjdp_swclktck.u_cxdapswjdp_sw_dp_protocol.rc_gclk_5612"
)


class TestNetlistScale:
    def test_netlist_gate_count(self, soc_netlist):
        """SoC netlist must have > 1M gates."""
        gate_count = len(soc_netlist._gates)
        assert gate_count > 1_000_000, f"Expected >1M gates, got {gate_count}"

    def test_netlist_signal_count(self, soc_netlist):
        """SoC netlist must have > 1M signals."""
        sig_count = len(soc_netlist.get_all_signals())
        assert sig_count > 1_000_000, f"Expected >1M signals, got {sig_count}"


class TestHierarchyExists:
    def test_noc_hierarchy_signal_exists(self, soc_netlist):
        """NOC clock gate signal must have drivers in the netlist."""
        drivers = soc_netlist.get_drivers(NOC_SIGNAL)
        assert len(drivers) > 0, f"No drivers for NOC signal: {NOC_SIGNAL}"

    def test_jtag_hierarchy_signal_exists(self, soc_netlist):
        """JTAG TAP clock gate signal must have drivers."""
        drivers = soc_netlist.get_drivers(JTAG_SIGNAL)
        assert len(drivers) > 0, f"No drivers for JTAG signal: {JTAG_SIGNAL}"

    def test_dap_hierarchy_signal_exists(self, soc_netlist):
        """DAP SWJ-DP clock gate signal must have drivers."""
        drivers = soc_netlist.get_drivers(DAP_SIGNAL)
        assert len(drivers) > 0, f"No drivers for DAP signal: {DAP_SIGNAL}"


class TestNetlistProperties:
    def test_deep_hierarchy_depth(self, soc_netlist):
        """Find at least one signal with 8+ hierarchy levels (dots)."""
        found = False
        for sig in soc_netlist.get_all_signals():
            if sig.count('.') >= 8:
                found = True
                break
        assert found, "No signal with 8+ dots found in netlist"

    def test_sequential_cell_detection(self, soc_netlist):
        """Find a DFF gate and verify is_sequential=True with clock_port set."""
        found_seq = None
        for gate in soc_netlist._gates.values():
            if gate.is_sequential and gate.clock_port is not None:
                found_seq = gate
                break
        assert found_seq is not None, "No sequential gate with clock_port found"
        assert found_seq.is_sequential is True
        assert found_seq.clock_port is not None

    def test_tsmc_cell_types_recognized(self, soc_netlist, gate_model):
        """Common TSMC cell types from the netlist should be recognized by gate_model."""
        # Collect a sample of cell types from the netlist
        cell_types = set()
        for gate in soc_netlist._gates.values():
            cell_types.add(gate.cell_type)
            if len(cell_types) >= 200:
                break

        # At least some should be recognized
        recognized = [ct for ct in cell_types if gate_model.is_known_cell(ct)]
        assert len(recognized) > 0, (
            f"No TSMC cells recognized out of {len(cell_types)} sampled: "
            f"{list(cell_types)[:10]}"
        )
