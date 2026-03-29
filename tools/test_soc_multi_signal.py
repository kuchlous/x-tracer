#!/usr/bin/env python3
"""Test x-tracer on multiple X signals from the real SoC.

Parses the netlist once (~166s), then traces 3 different X signals at
different hierarchy levels, reporting success/failure for each.
"""

import sys
import time
import logging
from pathlib import Path

# Ensure project root is on sys.path
_root = Path(__file__).resolve().parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from src.netlist import parse_netlist_fast
from src.vcd.database import load_vcd, PrefixMappedVCD
from src.tracer.core import trace_x, collect_leaves
from src.gates import GateModel
from src.cli.formatters import format_text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ---- Configuration ----

VCD_PATH = Path("/data/work_area/alokk/x-tracer/proj/verif/run/run_log/rjn_a55_uart1_test2/rjn_a55_uart1_test.vcd")

NETLIST_FILES = [
    Path("/Backend_share/pd_dv_1p1/Dec_26_Flat_SDF/rjn_soc_top.Fill_uniquify.v"),
]

# Std cell libraries -- needed for cell definitions
STD_CELL_DIR = Path("/Backend_share/pd_dv_1p1/Dec_26_Flat_SDF/libs/std_cells_verilog")
for f in sorted(STD_CELL_DIR.glob("*.v")):
    NETLIST_FILES.append(f)

VCD_PREFIX = "rjn_top.u_rjn_soc_top"
NETLIST_TOP = "rjn_soc_top"

MAX_DEPTH = 5

# Signals to trace: (vcd_path, time_fs)
# The tracer works in VCD-native time units. Timescale is 1fs, so time_fs = VCD time.
SIGNALS = [
    {
        "name": "NOC AMNI wdata_formatter clock gate",
        "vcd_path": "rjn_top.u_rjn_soc_top.inst_rjn_app_top.noc_app_ins.u_amni_m_CAM_CNTRL_DATA_INTF.u_amni_m_CAM_CNTRL_DATA_INTF_amni_core_c630cu1bnt.u_arachne_amni_axi4_adaptor.u_wdata_formatter.rc_gclk_2024",
        "time_fs": 1005528000,
    },
    {
        "name": "JTAG TAP clock gate",
        "vcd_path": "rjn_top.u_rjn_soc_top.inst_rjn_sys_top.azurite_ins.jtag_tap.rc_gclk_2319",
        "time_fs": 1021145000,
    },
    {
        "name": "CoreSight DAP SWJ-DP clock gate",
        "vcd_path": "rjn_top.u_rjn_soc_top.inst_rjn_dbg_top.inst_coresight_dap.inst_swjdp.u_cxdapswjdp_swclktck.u_cxdapswjdp_sw_dp_protocol.rc_gclk_5612",
        "time_fs": 1021150000,
    },
]

LOG_FILE = Path(__file__).parent / "multi_signal_trace.log"


def vcd_to_netlist(vcd_path: str) -> str:
    """Convert VCD hierarchy path to netlist path."""
    prefix = VCD_PREFIX + "."
    if vcd_path.startswith(prefix):
        return NETLIST_TOP + "." + vcd_path[len(prefix):]
    return vcd_path


def main():
    results = []
    log_lines = []

    def emit(msg):
        print(msg)
        log_lines.append(msg)

    emit("=" * 80)
    emit("X-Tracer Multi-Signal Test")
    emit("=" * 80)

    # ---- Step 1: Parse netlist (once) ----
    emit(f"\n[1/3] Parsing netlist ({len(NETLIST_FILES)} files) ...")
    t0 = time.time()
    graph = parse_netlist_fast(NETLIST_FILES, top_module=NETLIST_TOP)
    t_parse = time.time() - t0
    emit(f"  Netlist parsed in {t_parse:.1f}s")
    emit(f"  Signals in netlist: {len(graph.get_all_signals()):,}")

    gate_model = GateModel()

    # ---- Step 2: Check drivers for each signal ----
    emit(f"\n[2/3] Checking signal drivers in netlist ...")
    for sig_info in SIGNALS:
        netlist_path = vcd_to_netlist(sig_info["vcd_path"])
        sig_info["netlist_path"] = netlist_path
        drivers = graph.get_drivers(netlist_path)
        emit(f"  {sig_info['name']}:")
        emit(f"    Netlist path: {netlist_path}")
        emit(f"    Drivers: {len(drivers)}")
        if drivers:
            for d in drivers:
                emit(f"      - {d.cell_type} @ {d.instance_path}")
        sig_info["has_drivers"] = len(drivers) > 0

    # ---- Step 3: Trace each signal ----
    emit(f"\n[3/3] Tracing X signals (max_depth={MAX_DEPTH}) ...")
    for i, sig_info in enumerate(SIGNALS):
        emit(f"\n--- Signal {i+1}/{len(SIGNALS)}: {sig_info['name']} ---")
        vcd_path = sig_info["vcd_path"]
        time_fs = sig_info["time_fs"]

        # Load only this signal from VCD
        emit(f"  Loading VCD for signal: {vcd_path} ...")
        t0 = time.time()
        try:
            vcd_db = load_vcd(VCD_PATH, signals={vcd_path})
            t_vcd = time.time() - t0
            emit(f"  VCD loaded in {t_vcd:.1f}s (timescale={vcd_db.timescale_fs} fs)")
        except Exception as e:
            emit(f"  ERROR loading VCD: {e}")
            results.append({"name": sig_info["name"], "status": "FAIL", "error": str(e)})
            continue

        # Wrap with prefix mapping
        mapped_vcd = PrefixMappedVCD(vcd_db, VCD_PREFIX, NETLIST_TOP)

        # The netlist path is what trace_x uses; PrefixMappedVCD translates it
        netlist_path = sig_info["netlist_path"]

        # Check signal is X at query time
        # VCD timescale is 1fs, so vcd_time = time_fs
        vcd_time = time_fs  # timescale is 1fs, so fs == VCD time units
        try:
            val = mapped_vcd.get_bit(netlist_path, 0, vcd_time)
            emit(f"  Value at t={time_fs} fs: {val}")
            if val != 'x':
                emit(f"  WARNING: Signal is not X at this time (val={val}), skipping trace")
                results.append({"name": sig_info["name"], "status": "SKIP", "error": f"Not X (val={val})"})
                continue
        except Exception as e:
            emit(f"  ERROR reading VCD value: {e}")
            results.append({"name": sig_info["name"], "status": "FAIL", "error": str(e)})
            continue

        # Run trace
        t0 = time.time()
        try:
            cause_tree = trace_x(graph, mapped_vcd, gate_model,
                                 netlist_path, 0, vcd_time,
                                 max_depth=MAX_DEPTH)
            t_trace = time.time() - t0
            emit(f"  Trace completed in {t_trace:.3f}s")

            # Format the cause tree
            tree_text = format_text(cause_tree)
            emit(f"\n  Cause tree:")
            for line in tree_text.split("\n"):
                emit(f"    {line}")

            # Collect leaves (root causes)
            leaves = collect_leaves(cause_tree)
            emit(f"\n  Root causes ({len(leaves)} leaves):")
            for leaf in leaves:
                gate_info = f" [{leaf.gate.cell_type}]" if leaf.gate else ""
                emit(f"    - [{leaf.cause_type}] {leaf.signal} @ t={leaf.time}{gate_info}")

            results.append({
                "name": sig_info["name"],
                "status": "OK",
                "trace_time": t_trace,
                "tree_depth": _tree_depth(cause_tree),
                "num_leaves": len(leaves),
                "leaf_types": list(set(l.cause_type for l in leaves)),
            })
        except Exception as e:
            t_trace = time.time() - t0
            emit(f"  ERROR during trace: {e}")
            import traceback
            emit(f"  {traceback.format_exc()}")
            results.append({"name": sig_info["name"], "status": "FAIL", "error": str(e)})

    # ---- Summary ----
    emit("\n" + "=" * 80)
    emit("SUMMARY")
    emit("=" * 80)
    for r in results:
        status = r["status"]
        name = r["name"]
        if status == "OK":
            emit(f"  [OK]   {name} -- depth={r['tree_depth']}, leaves={r['num_leaves']}, types={r['leaf_types']}")
        elif status == "SKIP":
            emit(f"  [SKIP] {name} -- {r['error']}")
        else:
            emit(f"  [FAIL] {name} -- {r.get('error', 'unknown')}")

    ok_count = sum(1 for r in results if r["status"] == "OK")
    emit(f"\n  {ok_count}/{len(SIGNALS)} signals traced successfully")

    # Save log
    LOG_FILE.write_text("\n".join(log_lines))
    emit(f"\nLog saved to: {LOG_FILE}")


def _tree_depth(node) -> int:
    if not node.children:
        return 1
    return 1 + max(_tree_depth(c) for c in node.children)


if __name__ == "__main__":
    main()
