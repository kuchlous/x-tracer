"""Click-based CLI for X-Tracer."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import click

from .formatters import format_text, format_json, format_dot
from src.vcd.database import _TS_UNITS


def _format_timescale(timescale_fs: int) -> str:
    """Convert timescale in femtoseconds to human-readable string."""
    for unit, fs_per in sorted(_TS_UNITS.items(), key=lambda x: x[1]):
        if timescale_fs % fs_per == 0:
            n = timescale_fs // fs_per
            if n <= 1000:
                return f"{n} {unit}"
    return f"{timescale_fs} fs"


def parse_signal(signal_str: str) -> tuple[str, int]:
    """Parse signal argument into (signal_path, bit_index).

    "tb.dut.result[3]" -> ("tb.dut.result", 3)
    "tb.dut.clk"       -> ("tb.dut.clk", 0)
    """
    m = re.match(r"^(.+)\[(\d+)\]$", signal_str)
    if m:
        return m.group(1), int(m.group(2))
    return signal_str, 0


@click.command()
@click.option("--netlist", "-n", multiple=True, required=True,
              type=click.Path(exists=True),
              help="Verilog netlist file(s)")
@click.option("--vcd", "-v", required=True,
              type=click.Path(exists=True),
              help="VCD file path")
@click.option("--signal", "-s", required=True,
              help='Query signal, e.g. "tb.dut.result[3]" or "tb.dut.clk"')
@click.option("--time", "-t", "query_time", required=True, type=int,
              help="Query time in picoseconds")
@click.option("--format", "-f", "output_format", default="text",
              type=click.Choice(["text", "json", "dot"]),
              help="Output format")
@click.option("--max-depth", default=100, type=int,
              help="Maximum trace depth")
@click.option("--top-module", default=None, type=str,
              help="Top module name (auto-detected if omitted)")
def cli(netlist, vcd, signal, query_time, output_format, max_depth, top_module):
    """X-Tracer: trace the root cause of X values in gate-level simulations."""
    # Parse signal
    sig_path, sig_bit = parse_signal(signal)

    # Parse netlist
    try:
        from src.netlist import parse_netlist
        netlist_files = [Path(f) for f in netlist]
        graph = parse_netlist(netlist_files, top_module=top_module)
    except Exception as e:
        click.echo(f"Error parsing netlist: {e}", err=True)
        sys.exit(1)

    # Load VCD
    try:
        from src.vcd import load_vcd
        vcd_db = load_vcd(Path(vcd))
    except Exception as e:
        click.echo(f"Error loading VCD: {e}", err=True)
        sys.exit(1)

    click.echo(f"VCD timescale: {_format_timescale(vcd_db.timescale_fs)}", err=True)

    # Convert user's picosecond time to VCD-native time units
    vcd_time = vcd_db.ps_to_vcd(query_time)
    click.echo(f"Query: {sig_path}[{sig_bit}] @ {query_time} ps (VCD time: {vcd_time})", err=True)

    # Check signal exists in VCD
    if not vcd_db.has_signal(sig_path):
        click.echo(f"Error: signal '{sig_path}' not found in VCD", err=True)
        sys.exit(1)

    # Check signal is X at query time
    val = vcd_db.get_bit(sig_path, sig_bit, vcd_time)
    if val != 'x':
        click.echo(
            f"Signal is not X at time {query_time} ps (value={val})",
            err=True,
        )
        sys.exit(1)

    # Run tracer
    from src.tracer import trace_x
    from src.gates import GateModel

    gate_model = GateModel()
    try:
        result = trace_x(graph, vcd_db, gate_model,
                         sig_path, sig_bit, vcd_time,
                         max_depth=max_depth)
    except Exception as e:
        click.echo(f"Error during trace: {e}", err=True)
        sys.exit(1)

    # Format output
    if output_format == "text":
        click.echo(format_text(result))
    elif output_format == "json":
        click.echo(format_json(result))
    elif output_format == "dot":
        click.echo(format_dot(result))


def main():
    cli()


if __name__ == "__main__":
    main()
