#!/usr/bin/env python3
"""Entry point for X-Tracer CLI.

Usage: python3 x_tracer.py --netlist net.v --vcd sim.vcd --signal tb.dut.y[0] --time 30000
"""

import sys
from pathlib import Path

# Ensure the project root is on sys.path
_root = Path(__file__).resolve().parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from src.cli.main import cli

if __name__ == "__main__":
    cli()
