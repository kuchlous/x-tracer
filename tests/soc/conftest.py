import pytest
from pathlib import Path

NETLIST_FILES = [
    Path('/Backend_share/pd_dv_1p1/Dec_26_Flat_SDF/rjn_soc_top.Fill_uniquify.v'),
    Path('/Backend_share/pd_dv_1p1/Dec_26_Flat_SDF/DynamIQ_Cluster_A55_1.Fill_uniquify.v'),
]

VCD_PREFIX = 'rjn_top.u_rjn_soc_top'
NETLIST_TOP = 'rjn_soc_top'


@pytest.fixture(scope="session")
def soc_netlist():
    """Parse real SoC netlist (3.3M gates). ~160s, shared across all SoC tests."""
    for f in NETLIST_FILES:
        if not f.exists():
            pytest.skip(f"SoC netlist not available: {f}")
    from src.netlist.fast_parser import parse_netlist_fast
    return parse_netlist_fast(NETLIST_FILES)


@pytest.fixture(scope="session")
def gate_model():
    from src.gates import GateModel
    return GateModel()


def make_vcd_db(transitions, timescale_fs=1):
    """Create VCDDatabase from dict of signal->[(time,val)] transitions."""
    from src.vcd.database import VCDDatabase
    signals = set(transitions.keys())
    return VCDDatabase(transitions, signals, timescale_fs=timescale_fs)


def make_prefix_vcd(vcd_db):
    """Wrap VCDDatabase with PrefixMappedVCD for SoC path translation."""
    from src.vcd.database import PrefixMappedVCD
    return PrefixMappedVCD(vcd_db, VCD_PREFIX, NETLIST_TOP)
