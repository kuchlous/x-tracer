#!/usr/bin/env python3
"""
Testcase validation pipeline for the X-Tracer corpus.

Runs Layers 1-4 and Layer 6 against a testcase directory.
Requires: manifest.json, netlist.v, tb.v, tb_no_inject.v, sim.vcd

Usage:
    python3 validate.py <testcase_dir>
    python3 validate.py tests/cases/synthetic/gates/and_x_prop
"""

import json
import re
import subprocess
import sys
from pathlib import Path


# ── VCD parser ────────────────────────────────────────────────────────────────

class VCDParser:
    """
    Minimal VCD parser that builds a signal database from a VCD file.

    Handles:
    - $scope/$upscope to construct full hierarchical signal paths
    - $var declarations mapping short codes to (path, width)
    - Scalar value changes: x! 0" 1#
    - Vector value changes: b0x ! b1010 "
    - Multiple $scope levels (e.g. tb → tb.dut)
    """

    def __init__(self, vcd_path: Path):
        self.path = vcd_path
        # code -> list of (full_path, width)
        # A code can appear in multiple scopes; we keep all.
        self.code_to_signals: dict[str, list[tuple[str, int]]] = {}
        # full_path -> list of (time_ps, value_str) sorted by time
        self.transitions: dict[str, list[tuple[int, str]]] = {}
        self._parse()

    def _parse(self):
        scope_stack: list[str] = []
        current_time = 0

        with open(self.path) as f:
            content = f.read()

        # Strip block comments ($keyword ... $end) from header for var parsing
        # but we need to keep value changes, so we parse line-by-line with state.
        in_def = True   # True until $enddefinitions $end
        tokens = iter(re.split(r'\s+', content))

        for tok in tokens:
            if not tok:
                continue

            if tok == '$scope':
                _kind = next(tokens)   # module / task / etc.
                name  = next(tokens)
                _end  = next(tokens)   # $end
                scope_stack.append(name)

            elif tok == '$upscope':
                _end = next(tokens)    # $end
                if scope_stack:
                    scope_stack.pop()

            elif tok == '$var':
                kind  = next(tokens)   # wire / reg / integer …
                width = int(next(tokens))
                code  = next(tokens)
                sname = next(tokens)   # signal name (may be followed by [M:N])
                # consume everything up to $end (e.g. "[3:0]", "$end")
                rest = []
                t = next(tokens)
                while t != '$end':
                    rest.append(t)
                    t = next(tokens)
                full_path = '.'.join(scope_stack + [sname])
                self.code_to_signals.setdefault(code, [])
                self.code_to_signals[code].append((full_path, width))

            elif tok == '$enddefinitions':
                next(tokens)  # $end
                in_def = False

            elif not in_def:
                if tok.startswith('#'):
                    current_time = int(tok[1:])

                elif tok.startswith('b') or tok.startswith('B'):
                    # Vector: bXXX <code>
                    val_str = tok[1:]        # binary string (may contain x/z)
                    code    = next(tokens)
                    for path, width in self.code_to_signals.get(code, []):
                        # Pad/truncate to width
                        padded = val_str.zfill(width)[-width:]
                        self.transitions.setdefault(path, [])
                        self.transitions[path].append((current_time, padded))

                elif len(tok) >= 2 and tok[0] in '01xzXZ' and tok[1:]:
                    # Scalar: <value><code>
                    val  = tok[0].lower()
                    code = tok[1:]
                    for path, width in self.code_to_signals.get(code, []):
                        self.transitions.setdefault(path, [])
                        self.transitions[path].append((current_time, val))

    def get_value(self, signal_path: str, time_ps: int) -> str | None:
        """Return the value of signal at or just before time_ps. None if unknown."""
        trans = self.transitions.get(signal_path)
        if not trans:
            return None
        val = None
        for t, v in trans:
            if t <= time_ps:
                val = v
            else:
                break
        return val

    def get_bit(self, signal_path: str, bit: int, time_ps: int) -> str | None:
        """Return value of bit `bit` of signal at time_ps. Bit 0 = LSB."""
        val = self.get_value(signal_path, time_ps)
        if val is None:
            return None
        if len(val) == 1:
            # scalar
            return val
        # binary string, MSB first
        idx = len(val) - 1 - bit
        if idx < 0 or idx >= len(val):
            return None
        return val[idx]

    def first_x_time(self, signal_path: str, bit: int | None,
                     after: int = 0) -> int | None:
        """Return earliest time >= after at which bit is 'x'. None if never."""
        trans = self.transitions.get(signal_path, [])
        for t, v in trans:
            if t < after:
                continue
            if bit is None or len(v) == 1:
                if v.lower() == 'x':
                    return t
            else:
                idx = len(v) - 1 - bit
                if 0 <= idx < len(v) and v[idx].lower() == 'x':
                    return t
        return None

    def any_unknown_before(self, time_ps: int) -> list[tuple[str, int, str]]:
        """Return list of (signal, time, value) for any X/Z before time_ps."""
        violations = []
        for path, trans in self.transitions.items():
            for t, v in trans:
                if t >= time_ps:
                    break
                if any(c in 'xXzZ' for c in v):
                    violations.append((path, t, v))
        return violations


# ── signal path parsing ───────────────────────────────────────────────────────

def parse_sig_bit(sig_bit: str) -> tuple[str, int | None]:
    """
    Parse "tb.dut.a[0]" → ("tb.dut.a", 0)
    Parse "tb.dut.a"    → ("tb.dut.a", None)  (scalar, use bit=None)
    """
    m = re.match(r'^(.+)\[(\d+)\]$', sig_bit)
    if m:
        return m.group(1), int(m.group(2))
    return sig_bit, None


# ── validation layers ─────────────────────────────────────────────────────────

PASS = True
FAIL = False


def layer1_compile(netlist: Path, tb: Path, work_dir: Path) -> tuple[bool, str]:
    """Layer 1: iverilog syntax and elaboration."""
    out_vvp = work_dir / '_validate_l1.vvp'
    result = subprocess.run(
        ['iverilog', '-o', str(out_vvp), str(tb), str(netlist)],
        capture_output=True, text=True,
    )
    out_vvp.unlink(missing_ok=True)
    if result.returncode != 0:
        return FAIL, f"iverilog failed:\n{result.stderr.strip()}"
    return PASS, "iverilog OK"


def layer2_clean_env(vcd: VCDParser, injection_time: int) -> tuple[bool, str]:
    """Layer 2: no X or Z in VCD before injection_time."""
    violations = vcd.any_unknown_before(injection_time)
    if violations:
        lines = [f"  {sig} = {val!r} at t={t}" for sig, t, val in violations[:10]]
        return FAIL, "X/Z found before injection:\n" + "\n".join(lines)
    return PASS, f"No X/Z before t={injection_time}"


def layer3_query_is_x(vcd: VCDParser, query_sig_bit: str,
                       query_time: int) -> tuple[bool, str]:
    """Layer 3: query signal is X at query_time."""
    sig, bit = parse_sig_bit(query_sig_bit)
    val = vcd.get_bit(sig, bit, query_time) if bit is not None else vcd.get_value(sig, query_time)
    if val is None:
        return FAIL, f"Signal {query_sig_bit!r} not found in VCD"
    if val.lower() != 'x':
        return FAIL, f"Query {query_sig_bit!r} = {val!r} at t={query_time} (expected x)"
    return PASS, f"Query {query_sig_bit!r} = x at t={query_time}"


def layer4_injection_took_effect(vcd: VCDParser, injection_target: str,
                                  injection_time: int) -> tuple[bool, str]:
    """Layer 4: injection target is X at injection_time."""
    sig, bit = parse_sig_bit(injection_target)
    # Check at injection_time or shortly after (within 1ps for combinational)
    for check_t in [injection_time, injection_time + 1]:
        val = vcd.get_bit(sig, bit, check_t) if bit is not None else vcd.get_value(sig, check_t)
        if val is not None and val.lower() == 'x':
            return PASS, f"Injection target {injection_target!r} = x at t={check_t}"
    val = vcd.get_bit(sig, bit, injection_time) if bit is not None else vcd.get_value(sig, injection_time)
    return FAIL, f"Injection target {injection_target!r} = {val!r} at t={injection_time} (expected x)"


def layer5_single_injection(tb: Path) -> tuple[bool, str]:
    """Layer 5: testbench injects X on exactly one signal bit.

    Scans tb.v for force/assign-to-x and $deposit-to-x statements.
    Each unique signal[bit] or scalar signal counts as one injection point.
    Fails if more than one distinct injection point is found.
    """
    src = tb.read_text()

    # Match: force <path> = 1'bx  OR  force <path>[N] = 1'bx
    force_re  = re.compile(
        r'\bforce\s+([\w.\[\]]+)\s*=\s*1\'b[xX]', re.IGNORECASE)
    # Match: $deposit(<path>, 1'bx)  OR  $deposit(<path>[N], 1'bx)
    deposit_re = re.compile(
        r'\$deposit\s*\(\s*([\w.\[\]]+)\s*,\s*1\'b[xX]\s*\)', re.IGNORECASE)

    targets = set()
    for m in force_re.finditer(src):
        targets.add(m.group(1))
    for m in deposit_re.finditer(src):
        targets.add(m.group(1))

    if len(targets) == 0:
        return FAIL, "No X injection found in testbench"
    if len(targets) > 1:
        return FAIL, f"Multiple injection points ({len(targets)}): {sorted(targets)}"
    return PASS, f"Single injection point: {next(iter(targets))}"


def layer6_counterfactual(netlist: Path, tb_no_inject: Path, work_dir: Path,
                           query_sig_bit: str, query_time: int,
                           injection_time: int) -> tuple[bool, str]:
    """Layer 6: run without injection; query signal must NOT be X.

    Uses sim_no_inject.vcd if it already exists (produced by the generating
    agent). If not, recompiles tb_no_inject.v and reruns the simulation.
    """
    # Prefer pre-existing no-inject VCD (avoids recompile)
    prebuilt = work_dir / 'sim_no_inject.vcd'
    if prebuilt.exists():
        vcd_noinj = VCDParser(prebuilt)
        sig, bit = parse_sig_bit(query_sig_bit)
        val = vcd_noinj.get_bit(sig, bit, query_time) if bit is not None \
              else vcd_noinj.get_value(sig, query_time)
        if val is not None and val.lower() == 'x':
            return FAIL, f"Query {query_sig_bit!r} is X even without injection — secondary X source"
        return PASS, f"Query {query_sig_bit!r} = {val!r} without injection (not X)"

    # Fallback: compile and run tb_no_inject.v, capturing VCD into a temp file
    vvp      = work_dir / '_validate_l6.vvp'
    vcd_path = work_dir / '_validate_l6.vcd'
    patched_tb = work_dir / '_tb_l6_patched.v'

    tb_src = tb_no_inject.read_text()
    # Replace any $dumpfile path with our temp path
    patched = re.sub(r'\$dumpfile\s*\(\s*"[^"]*"\s*\)',
                     f'$dumpfile("{vcd_path}")', tb_src)
    patched_tb.write_text(patched)

    try:
        r1 = subprocess.run(
            ['iverilog', '-o', str(vvp), str(patched_tb), str(netlist)],
            capture_output=True, text=True,
        )
        if r1.returncode != 0:
            return FAIL, f"Layer 6 compile failed:\n{r1.stderr.strip()}"

        r2 = subprocess.run(['vvp', str(vvp)], capture_output=True, text=True,
                             cwd=str(work_dir))
        if r2.returncode != 0:
            return FAIL, f"Layer 6 simulation failed:\n{r2.stderr.strip()}"

        if not vcd_path.exists():
            return FAIL, "Layer 6 VCD not produced"

        vcd_noinj = VCDParser(vcd_path)
        sig, bit = parse_sig_bit(query_sig_bit)
        val = vcd_noinj.get_bit(sig, bit, query_time) if bit is not None \
              else vcd_noinj.get_value(sig, query_time)

        if val is not None and val.lower() == 'x':
            return FAIL, f"Query {query_sig_bit!r} is X even without injection — secondary X source"
        return PASS, f"Query {query_sig_bit!r} = {val!r} without injection (not X)"

    finally:
        for p in [vvp, vcd_path, patched_tb]:
            p.unlink(missing_ok=True)


# ── main ──────────────────────────────────────────────────────────────────────

def validate(testcase_dir: Path) -> bool:
    manifest_path = testcase_dir / 'manifest.json'
    if not manifest_path.exists():
        print(f"ERROR: no manifest.json in {testcase_dir}")
        return False

    m = json.loads(manifest_path.read_text())
    netlist      = testcase_dir / m['netlist']['file']
    tb           = testcase_dir / m['testbench']
    tb_no_inject = testcase_dir / 'tb_no_inject.v'
    vcd_path     = testcase_dir / m['vcd']

    inj       = m['x_injection']
    exp       = m['expected']
    inj_time  = inj['time']
    inj_target = exp['injection_target']
    q_sig_bit  = exp['query_signal']
    q_time     = exp['query_time']

    print(f"\n{'='*60}")
    print(f"Validating: {testcase_dir.name}")
    print(f"{'='*60}")

    all_pass = True

    # Layer 1
    ok, msg = layer1_compile(netlist, tb, testcase_dir)
    print(f"  Layer 1 (compile):      {'PASS' if ok else 'FAIL'} — {msg}")
    all_pass &= ok

    if not vcd_path.exists():
        print(f"  ERROR: sim.vcd not found — run simulation first")
        return False

    vcd = VCDParser(vcd_path)

    # Layer 2
    ok, msg = layer2_clean_env(vcd, inj_time)
    print(f"  Layer 2 (clean env):    {'PASS' if ok else 'FAIL'} — {msg}")
    all_pass &= ok

    # Layer 3
    ok, msg = layer3_query_is_x(vcd, q_sig_bit, q_time)
    print(f"  Layer 3 (query is X):   {'PASS' if ok else 'FAIL'} — {msg}")
    all_pass &= ok

    # Layer 4
    ok, msg = layer4_injection_took_effect(vcd, inj_target, inj_time)
    print(f"  Layer 4 (injection X):  {'PASS' if ok else 'FAIL'} — {msg}")
    all_pass &= ok

    # Layer 5
    ok, msg = layer5_single_injection(tb)
    print(f"  Layer 5 (single inj):   {'PASS' if ok else 'FAIL'} — {msg}")
    all_pass &= ok

    # Layer 6
    if tb_no_inject.exists():
        ok, msg = layer6_counterfactual(
            netlist, tb_no_inject, testcase_dir, q_sig_bit, q_time, inj_time)
        print(f"  Layer 6 (counterfact):  {'PASS' if ok else 'FAIL'} — {msg}")
        all_pass &= ok
    else:
        print(f"  Layer 6 (counterfact):  SKIP — tb_no_inject.v not found")

    print(f"\n  Result: {'ALL PASS' if all_pass else 'FAILED'}")
    return all_pass


if __name__ == '__main__':
    if len(sys.argv) < 2:
        # Run all testcases
        base = Path(__file__).parent / 'cases'
        dirs = sorted(p for p in base.rglob('manifest.json'))
        results = []
        for manifest in dirs:
            results.append(validate(manifest.parent))
        passed = sum(results)
        total  = len(results)
        print(f"\n{'='*60}")
        print(f"Total: {passed}/{total} passed")
        sys.exit(0 if passed == total else 1)
    else:
        ok = validate(Path(sys.argv[1]))
        sys.exit(0 if ok else 1)
