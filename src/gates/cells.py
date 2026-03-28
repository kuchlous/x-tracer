"""Standard cell family recognition and decomposition.

Handles Tier 2 cells: pattern-matches cell_type strings to identify
the base function, then evaluates using primitive operations.
"""

import re
from typing import Optional

from . import primitives as P

# Known PDK prefixes to strip (lowercase)
_PDK_PREFIXES = [
    'sky130_fd_sc_hd__',
    'sky130_fd_sc_hs__',
    'sky130_fd_sc_ms__',
    'sky130_fd_sc_ls__',
    'sky130_fd_sc_lp__',
    'sky130_fd_sc_hvl__',
    'gf180mcu_fd_sc_mcu7t5v0__',
    'gf180mcu_fd_sc_mcu9t5v0__',
    'asap7sc7p5t_',
    'nangate45_',
]

# Drive strength suffix pattern: _0, _1, _2, _4, _8, _16, etc.
_DRIVE_SUFFIX = re.compile(r'_\d+$')

# TSMC / ARM Artisan cell naming: CELLFUNC_XDRIVE_TECHSUFFIX
# Examples: AND2_X1M_A9PP140ZTH_C30, INV_X0P5B_A9PP140ZTH_C35
# The tech suffix matches: _A9PP140Z<vt>_C<corner>
# Also handles other TSMC families: A9PP140ZTL, A9PP140ZTS, A9PP140ZTUH
_TSMC_SUFFIX_RE = re.compile(r'_X[\dP]+[BM]_A\d+PP\d+Z\w+_C\d+$', re.IGNORECASE)

# Generic Artisan-style: strip drive strength + tech suffix
# Pattern: FUNC_X<drive><type>_<techid> where drive can be 0P5, 1, 1P4, 2, etc.
_ARTISAN_DRIVE_SUFFIX_RE = re.compile(r'_X[\dP]+[BM]$', re.IGNORECASE)


def strip_cell_name(cell_type: str) -> str:
    """Strip PDK prefix and drive strength suffix to get base function name.

    Handles two naming conventions:
    1. Prefix-based (Sky130, GF180, ASAP7): sky130_fd_sc_hd__and2_1 → and2
    2. Suffix-based (TSMC/Artisan): AND2_X1M_A9PP140ZTH_C30 → and2
    """
    name = cell_type.lower()

    # Try prefix-based stripping first (Sky130, etc.)
    for prefix in _PDK_PREFIXES:
        if name.startswith(prefix):
            name = name[len(prefix):]
            name = _DRIVE_SUFFIX.sub('', name)
            return name

    # Try TSMC/Artisan suffix-based stripping
    # First strip full tech suffix: _X<drive>_A<tech>_C<corner>
    stripped = _TSMC_SUFFIX_RE.sub('', name)
    if stripped != name:
        return stripped

    # Try stripping just the drive strength suffix: _X<drive><type>
    stripped = _ARTISAN_DRIVE_SUFFIX_RE.sub('', name)
    if stripped != name:
        return stripped

    # Fallback: just strip trailing _N drive strength
    name = _DRIVE_SUFFIX.sub('', name)
    return name


# --- AOI/OAI pattern: e.g. a21oi, a22oi, a211oi, o21ai, o22ai ---
_AOI_RE = re.compile(r'^a(\d+)o?i$')
_OAI_RE = re.compile(r'^o(\d+)a?i$')

# More specific patterns for AOI/OAI with explicit group sizes
_AOI_GROUPS_RE = re.compile(r'^a(\d+)oi$')
_OAI_GROUPS_RE = re.compile(r'^o(\d+)ai$')


def _parse_aoi_oai_groups(digits: str) -> list[int]:
    """Parse digit string into group sizes. '21' -> [2,1], '22' -> [2,2], '211' -> [2,1,1]."""
    return [int(d) for d in digits]


def _make_aoi_ports(groups: list[int]) -> list[list[str]]:
    """Generate port names for AOI/OAI cells.
    Groups [2,1] -> [['A1','A2'], ['B1']]
    Groups [2,2] -> [['A1','A2'], ['B1','B2']]
    Groups [2,1,1] -> [['A1','A2'], ['B1'], ['C1']]
    """
    labels = 'ABCDEFGH'
    result = []
    for i, size in enumerate(groups):
        group = [f'{labels[i]}{j+1}' for j in range(size)]
        result.append(group)
    return result


class CellInfo:
    """Describes a recognized standard cell."""

    def __init__(self, family: str, num_inputs: int = 0,
                 port_map: Optional[dict] = None,
                 groups: Optional[list[int]] = None):
        self.family = family
        self.num_inputs = num_inputs
        self.port_map = port_map or {}
        self.groups = groups  # for AOI/OAI


def identify_cell(cell_type: str) -> Optional[CellInfo]:
    """Identify the cell family from cell_type string. Returns None if unknown."""
    base = strip_cell_name(cell_type)

    # Inverter variants
    if base in ('inv', 'clkinv') or 'inv' in base and 'ao' not in base and 'oi' not in base:
        # But exclude aoi/oai patterns
        if not _AOI_GROUPS_RE.match(base) and not _OAI_GROUPS_RE.match(base):
            return CellInfo('inv')

    # Buffer variants (buf, bufh, clkbuf, but not bufif)
    if base in ('buf', 'bufh', 'clkbuf') or (base.startswith('buf') and 'bufif' not in base):
        return CellInfo('buf')

    # Basic gate families with input count
    for fam in ('and', 'nand', 'or', 'nor', 'xor', 'xnor'):
        m = re.match(rf'^{fam}(\d+)$', base)
        if m:
            return CellInfo(fam, num_inputs=int(m.group(1)))

    # AOI: a21oi, a22oi, a211oi, a31oi, aoi21, aoi22, aoi211, aoi31, etc.
    m = _AOI_GROUPS_RE.match(base)
    if m:
        groups = _parse_aoi_oai_groups(m.group(1))
        return CellInfo('aoi', groups=groups)
    # TSMC style: aoi21, aoi22, aoi211, aoi31, etc.
    m = re.match(r'^aoi(\d+)(?:[a-z].*)?$', base)
    if m:
        groups = _parse_aoi_oai_groups(m.group(1))
        return CellInfo('aoi', groups=groups)

    # OAI: o21ai, o22ai, o211ai, oai21, oai22, etc.
    m = _OAI_GROUPS_RE.match(base)
    if m:
        groups = _parse_aoi_oai_groups(m.group(1))
        return CellInfo('oai', groups=groups)
    # TSMC style: oai21, oai22, oai211, etc.
    m = re.match(r'^oai(\d+)(?:[a-z].*)?$', base)
    if m:
        groups = _parse_aoi_oai_groups(m.group(1))
        return CellInfo('oai', groups=groups)

    # AO (and-or, non-inverted): ao21, ao22, ao1b2, etc.
    m = re.match(r'^ao(\d+)(?:[a-z].*)?$', base)
    if m and 'aoi' not in base:
        groups = _parse_aoi_oai_groups(m.group(1))
        return CellInfo('ao', groups=groups)

    # OA (or-and, non-inverted): oa21, oa22, etc.
    m = re.match(r'^oa(\d+)(?:[a-z].*)?$', base)
    if m and 'oai' not in base:
        groups = _parse_aoi_oai_groups(m.group(1))
        return CellInfo('oa', groups=groups)

    # MUX
    if base in ('mux2', 'mux2i'):
        return CellInfo('mux2')
    if base == 'mux4':
        return CellInfo('mux4')

    # Half adder: ha, addh, addha
    if base in ('ha', 'halfadder', 'addh', 'addha'):
        return CellInfo('ha')

    # Full adder: fa, addf
    if base in ('fa', 'fulladder', 'addf'):
        return CellInfo('fa')

    # Majority gate
    if base in ('maj', 'maj3', 'majority'):
        return CellInfo('maj')

    # Tie cells (constant outputs)
    if base in ('tiehi', 'tielo', 'tieh', 'tiel'):
        return CellInfo('tie')

    # Clock gate cells: cgen, cgencin, etc.
    if base.startswith('cgen') or base.startswith('fricg'):
        return CellInfo('clock_gate')

    # Sequential cells (DFF variants)
    # Covers: dff*, dfx*, dfr*, dfs*, dfb*, sdf* (scan DFFs)
    if any(base.startswith(p) for p in ('dff', 'dfx', 'dfr', 'dfs', 'dfb', 'sdf')):
        return CellInfo('dff')

    # Latch variants
    if base.startswith('lat') or base.startswith('dlat'):
        return CellInfo('latch')

    # Fill/antenna/endcap cells — not functional
    if any(base.startswith(p) for p in ('fill', 'antenna', 'endcap', 'decap')):
        return CellInfo('filler')

    # Delay cells
    if base.startswith('dly'):
        return CellInfo('buf')

    return None


def _get_input_vals(inputs: dict[str, str], ports: list[str]) -> list[str]:
    """Get values for given port names from inputs dict."""
    return [P._norm(inputs.get(p, 'x')) for p in ports]


def forward_cell(info: CellInfo, inputs: dict[str, str]) -> str:
    """Compute output value for a recognized standard cell."""
    fam = info.family

    if fam == 'inv':
        val = inputs.get('A', inputs.get('in0', 'x'))
        return P.eval_not(val)

    if fam == 'buf':
        val = inputs.get('A', inputs.get('in0', 'x'))
        return P.eval_buf(val)

    if fam in ('and', 'nand', 'or', 'nor', 'xor', 'xnor'):
        n = info.num_inputs
        # Try standard cell port names A, B, C, D first, then in0, in1, ...
        port_names_std = list('ABCDEFGH')[:n]
        port_names_num = [f'in{i}' for i in range(n)]

        if port_names_std[0] in inputs:
            vals = [inputs.get(p, 'x') for p in port_names_std]
        else:
            vals = [inputs.get(p, 'x') for p in port_names_num]

        func = {
            'and': P.eval_and, 'nand': P.eval_nand,
            'or': P.eval_or, 'nor': P.eval_nor,
            'xor': P.eval_xor, 'xnor': P.eval_xnor,
        }[fam]
        return func(vals)

    if fam == 'aoi':
        # AOI: Y = ~(group0_AND | group1_AND | ...)
        port_groups = _make_aoi_ports(info.groups)
        or_inputs = []
        for group in port_groups:
            vals = [P._norm(inputs.get(p, 'x')) for p in group]
            or_inputs.append(P.eval_and(vals))
        return P.eval_nor(or_inputs)

    if fam == 'oai':
        # OAI: Y = ~(group0_OR & group1_OR & ...)
        port_groups = _make_aoi_ports(info.groups)
        and_inputs = []
        for group in port_groups:
            vals = [P._norm(inputs.get(p, 'x')) for p in group]
            and_inputs.append(P.eval_or(vals))
        return P.eval_nand(and_inputs)

    if fam == 'mux2':
        # X = S ? A1 : A0
        s = P._norm(inputs.get('S', 'x'))
        a0 = P._norm(inputs.get('A0', 'x'))
        a1 = P._norm(inputs.get('A1', 'x'))
        if s == '0':
            return a0
        if s == '1':
            return a1
        # s is x: if both data inputs are the same known value, output is that value
        if a0 == a1 and a0 != 'x':
            return a0
        return 'x'

    if fam == 'mux4':
        s0 = P._norm(inputs.get('S0', 'x'))
        s1 = P._norm(inputs.get('S1', 'x'))
        a = [P._norm(inputs.get(f'A{i}', 'x')) for i in range(4)]
        if s1 == 'x' or s0 == 'x':
            # Check if all relevant inputs are the same
            if s1 == '0':
                candidates = [a[0], a[1]] if s0 == 'x' else [a[0] if s0 == '0' else a[1]]
            elif s1 == '1':
                candidates = [a[2], a[3]] if s0 == 'x' else [a[2] if s0 == '0' else a[3]]
            else:
                candidates = a
            if all(c == candidates[0] and c != 'x' for c in candidates):
                return candidates[0]
            return 'x'
        idx = int(s1) * 2 + int(s0)
        return a[idx]

    if fam == 'ha':
        a = P._norm(inputs.get('A', 'x'))
        b = P._norm(inputs.get('B', 'x'))
        # Returns tuple-like but we return SUM by default.
        # The caller should specify which output port. For forward(),
        # we need to know which output. We'll return 'x' if any input is X
        # for simplicity — the tracer maps to specific output ports.
        # Actually, forward() returns a single value. For multi-output cells,
        # the Gate object has specific output port. We return X conservatively
        # if any input is X for the SUM output. The tracer will handle this.
        sum_val = P.eval_xor([a, b])
        return sum_val  # SUM output (most common query)

    if fam == 'fa':
        a = P._norm(inputs.get('A', 'x'))
        b = P._norm(inputs.get('B', 'x'))
        cin = P._norm(inputs.get('CIN', inputs.get('CI', 'x')))
        return P.eval_xor([a, b, cin])  # SUM output

    if fam == 'maj':
        a = P._norm(inputs.get('A', 'x'))
        b = P._norm(inputs.get('B', 'x'))
        c = P._norm(inputs.get('C', 'x'))
        # MAJ = (A & B) | (B & C) | (A & C)
        ab = P.eval_and([a, b])
        bc = P.eval_and([b, c])
        ac = P.eval_and([a, c])
        return P.eval_or([ab, bc, ac])

    if fam == 'ao':
        # AO: Y = (group0_AND | group1_AND | ...) — non-inverted
        port_groups = _make_aoi_ports(info.groups)
        or_inputs = []
        for group in port_groups:
            vals = [P._norm(inputs.get(p, 'x')) for p in group]
            or_inputs.append(P.eval_and(vals))
        return P.eval_or(or_inputs)

    if fam == 'oa':
        # OA: Y = (group0_OR & group1_OR & ...) — non-inverted
        port_groups = _make_aoi_ports(info.groups)
        and_inputs = []
        for group in port_groups:
            vals = [P._norm(inputs.get(p, 'x')) for p in group]
            and_inputs.append(P.eval_or(vals))
        return P.eval_and(and_inputs)

    if fam == 'tie':
        return '0'  # tiehi/tielo — constant output, never X

    if fam == 'filler':
        return '0'  # filler cells have no functional output

    if fam == 'clock_gate':
        # Clock gate: conservative — if enable or clock is X, output is X
        for port, val in inputs.items():
            if P._norm(val) == 'x':
                return 'x'
        return '0'

    if fam in ('dff', 'latch'):
        # Sequential: forward returns 'x' if any control is X
        # This is a simplified model — the tracer core handles the full logic
        for port, val in inputs.items():
            if P._norm(val) == 'x':
                return 'x'
        return inputs.get('D', 'x')

    return 'x'  # unknown family


def backward_cell(info: CellInfo, inputs: dict[str, str]) -> list[str]:
    """Return causal X-valued input ports for a recognized standard cell."""
    fam = info.family

    if fam == 'inv' or fam == 'buf':
        port = 'A' if 'A' in inputs else 'in0'
        if P._norm(inputs.get(port, '0')) == 'x':
            return [port]
        return []

    if fam in ('and', 'nand'):
        n = info.num_inputs
        port_names = list('ABCDEFGH')[:n] if list('ABCDEFGH')[0] in inputs else [f'in{i}' for i in range(n)]
        inp = {p: inputs.get(p, 'x') for p in port_names}
        return P.backward_and_or('and', inp)

    if fam in ('or', 'nor'):
        n = info.num_inputs
        port_names = list('ABCDEFGH')[:n] if 'A' in inputs else [f'in{i}' for i in range(n)]
        inp = {p: inputs.get(p, 'x') for p in port_names}
        return P.backward_and_or('or', inp)

    if fam in ('xor', 'xnor'):
        n = info.num_inputs
        port_names = list('ABCDEFGH')[:n] if 'A' in inputs else [f'in{i}' for i in range(n)]
        inp = {p: inputs.get(p, 'x') for p in port_names}
        return P.backward_xor_xnor(inp)

    if fam == 'aoi':
        return _backward_aoi(info.groups, inputs)

    if fam == 'oai':
        return _backward_oai(info.groups, inputs)

    if fam == 'mux2':
        return _backward_mux2(inputs)

    if fam == 'mux4':
        return _backward_mux4(inputs)

    if fam == 'ao':
        # AO: Y = (G0 | G1 | ...) where Gi = AND of group i inputs
        # Same logic as AOI backward but without inversion
        return _backward_aoi(info.groups, inputs)

    if fam == 'oa':
        # OA: Y = (G0 & G1 & ...) where Gi = OR of group i inputs
        return _backward_oai(info.groups, inputs)

    if fam in ('tie', 'filler'):
        return []  # constant cells never cause X

    if fam == 'clock_gate':
        return [p for p, v in inputs.items() if P._norm(v) == 'x']

    if fam in ('ha', 'fa', 'maj'):
        # XOR-based / complex — conservative: return all X inputs
        return [p for p, v in inputs.items() if P._norm(v) == 'x']

    # Sequential or unknown family — return all X inputs
    return [p for p, v in inputs.items() if P._norm(v) == 'x']


def _backward_aoi(groups: list[int], inputs: dict[str, str]) -> list[str]:
    """backward_causes for AOI cells.

    AOI: Y = ~(G0 | G1 | ...) where Gi = AND of group i inputs.
    Y is X when the OR result is X.
    OR result is X when no group produces controlling value '1',
    and at least one group produces 'x'.

    For a group's AND to be X: no input in the group is '0', and at least one is 'x'.
    """
    port_groups = _make_aoi_ports(groups)

    # Compute each group's AND result
    group_results = []
    for group in port_groups:
        vals = [P._norm(inputs.get(p, 'x')) for p in group]
        group_results.append(P.eval_and(vals))

    # The OR of group results
    or_result = P.eval_or(group_results)
    if or_result != 'x':
        # Output is determined, no X causes
        return []

    # OR is X: find which groups contribute X, and which groups have controlling '1'
    # OR has controlling value '1', so if any group result is '1', OR is determined.
    # Since we're here, no group result is '1' (otherwise or_result wouldn't be X).
    # Return the specific input ports from groups whose AND result is 'x'.
    causes = []
    for group, result in zip(port_groups, group_results):
        if result == 'x':
            # This group's AND is X — which inputs in the group are X?
            # For AND: all X inputs are causal (since no input is 0, otherwise AND would be 0)
            for p in group:
                if P._norm(inputs.get(p, 'x')) == 'x':
                    causes.append(p)
    return causes


def _backward_oai(groups: list[int], inputs: dict[str, str]) -> list[str]:
    """backward_causes for OAI cells.

    OAI: Y = ~(G0 & G1 & ...) where Gi = OR of group i inputs.
    Y is X when the AND result is X.
    AND result is X when no group produces controlling value '0',
    and at least one group produces 'x'.
    """
    port_groups = _make_aoi_ports(groups)

    group_results = []
    for group in port_groups:
        vals = [P._norm(inputs.get(p, 'x')) for p in group]
        group_results.append(P.eval_or(vals))

    and_result = P.eval_and(group_results)
    if and_result != 'x':
        return []

    causes = []
    for group, result in zip(port_groups, group_results):
        if result == 'x':
            for p in group:
                if P._norm(inputs.get(p, 'x')) == 'x':
                    causes.append(p)
    return causes


def _backward_mux2(inputs: dict[str, str]) -> list[str]:
    """backward_causes for 2:1 MUX. X = S ? A1 : A0."""
    s = P._norm(inputs.get('S', 'x'))
    a0 = P._norm(inputs.get('A0', 'x'))
    a1 = P._norm(inputs.get('A1', 'x'))

    causes = []
    if s == 'x':
        causes.append('S')
        # When S is X, data inputs that are X also contribute
        if a0 == 'x':
            causes.append('A0')
        if a1 == 'x':
            causes.append('A1')
    elif s == '0':
        if a0 == 'x':
            causes.append('A0')
    else:  # s == '1'
        if a1 == 'x':
            causes.append('A1')

    return causes


def _backward_mux4(inputs: dict[str, str]) -> list[str]:
    """backward_causes for 4:1 MUX."""
    s0 = P._norm(inputs.get('S0', 'x'))
    s1 = P._norm(inputs.get('S1', 'x'))
    a = {f'A{i}': P._norm(inputs.get(f'A{i}', 'x')) for i in range(4)}

    causes = []

    if s0 == 'x':
        causes.append('S0')
    if s1 == 'x':
        causes.append('S1')

    # Determine which data inputs are selected / potentially selected
    if s1 == '0':
        if s0 == '0':
            selected = ['A0']
        elif s0 == '1':
            selected = ['A1']
        else:
            selected = ['A0', 'A1']
    elif s1 == '1':
        if s0 == '0':
            selected = ['A2']
        elif s0 == '1':
            selected = ['A3']
        else:
            selected = ['A2', 'A3']
    else:
        if s0 == '0':
            selected = ['A0', 'A2']
        elif s0 == '1':
            selected = ['A1', 'A3']
        else:
            selected = ['A0', 'A1', 'A2', 'A3']

    for port in selected:
        if a[port] == 'x':
            causes.append(port)

    return causes
