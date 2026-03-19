"""Truth tables for Verilog primitives (IEEE 1364 semantics).

All values are single-character strings: '0', '1', 'x', 'z'.
'z' is treated as 'x' for evaluation purposes.
"""


def _norm(v: str) -> str:
    """Normalize value: treat 'z' as 'x'."""
    return 'x' if v == 'z' else v


# --- Primitive two-input truth tables ---
# Indexed as TABLE[a][b] -> result

AND2 = {
    '0': {'0': '0', '1': '0', 'x': '0'},
    '1': {'0': '0', '1': '1', 'x': 'x'},
    'x': {'0': '0', '1': 'x', 'x': 'x'},
}

OR2 = {
    '0': {'0': '0', '1': '1', 'x': 'x'},
    '1': {'0': '1', '1': '1', 'x': '1'},
    'x': {'0': 'x', '1': '1', 'x': 'x'},
}

XOR2 = {
    '0': {'0': '0', '1': '1', 'x': 'x'},
    '1': {'0': '1', '1': '0', 'x': 'x'},
    'x': {'0': 'x', '1': 'x', 'x': 'x'},
}

XNOR2 = {
    '0': {'0': '1', '1': '0', 'x': 'x'},
    '1': {'0': '0', '1': '1', 'x': 'x'},
    'x': {'0': 'x', '1': 'x', 'x': 'x'},
}

NOT_TABLE = {'0': '1', '1': '0', 'x': 'x'}


def _invert(v: str) -> str:
    return NOT_TABLE[v]


def eval_and(vals: list[str]) -> str:
    """N-input AND with IEEE 1364 semantics."""
    result = '1'
    for v in vals:
        v = _norm(v)
        result = AND2[result][v]
    return result


def eval_or(vals: list[str]) -> str:
    """N-input OR with IEEE 1364 semantics."""
    result = '0'
    for v in vals:
        v = _norm(v)
        result = OR2[result][v]
    return result


def eval_xor(vals: list[str]) -> str:
    """N-input XOR with IEEE 1364 semantics."""
    result = '0'
    for v in vals:
        v = _norm(v)
        result = XOR2[result][v]
    return result


def eval_xnor(vals: list[str]) -> str:
    """N-input XNOR = inverted XOR."""
    return _invert(eval_xor(vals))


def eval_nand(vals: list[str]) -> str:
    return _invert(eval_and(vals))


def eval_nor(vals: list[str]) -> str:
    return _invert(eval_or(vals))


def eval_not(val: str) -> str:
    return NOT_TABLE[_norm(val)]


def eval_buf(val: str) -> str:
    v = _norm(val)
    return v


def eval_bufif0(data: str, enable: str) -> str:
    """bufif0: output = data when enable is 0, z when enable is 1."""
    d, e = _norm(data), _norm(enable)
    if e == '0':
        return d
    if e == '1':
        return 'z'
    # enable is x
    if d == 'x':
        return 'x'
    return 'x'


def eval_bufif1(data: str, enable: str) -> str:
    """bufif1: output = data when enable is 1, z when enable is 0."""
    d, e = _norm(data), _norm(enable)
    if e == '1':
        return d
    if e == '0':
        return 'z'
    if d == 'x':
        return 'x'
    return 'x'


def eval_notif0(data: str, enable: str) -> str:
    """notif0: output = ~data when enable is 0, z when enable is 1."""
    d, e = _norm(data), _norm(enable)
    if e == '0':
        return _invert(d)
    if e == '1':
        return 'z'
    return 'x'


def eval_notif1(data: str, enable: str) -> str:
    """notif1: output = ~data when enable is 1, z when enable is 0."""
    d, e = _norm(data), _norm(enable)
    if e == '1':
        return _invert(d)
    if e == '0':
        return 'z'
    return 'x'


# --- Controlling values for backward_causes ---

CONTROLLING_VALUE = {
    'and': '0',
    'nand': '0',
    'or': '1',
    'nor': '1',
}

# XOR/XNOR have no controlling value — any X input produces X output.


def backward_and_or(gate_type: str, inputs: dict[str, str]) -> list[str]:
    """backward_causes for AND/NAND/OR/NOR gates.

    Returns ports that are X and causally responsible for X output.
    If any input has the controlling value, output is determined (not X),
    so this should not be called — but we handle it gracefully.
    """
    base = gate_type  # 'and', 'nand', 'or', 'nor'
    ctrl = CONTROLLING_VALUE[base]

    # Normalize inputs
    normed = {p: _norm(v) for p, v in inputs.items()}

    # If any input has controlling value, output is known — no X causes
    for v in normed.values():
        if v == ctrl:
            return []

    # Return all X-valued ports
    return [p for p, v in normed.items() if v == 'x']


def backward_xor_xnor(inputs: dict[str, str]) -> list[str]:
    """backward_causes for XOR/XNOR — any X input is causal."""
    return [p for p, v in inputs.items() if _norm(v) == 'x']


def backward_buf_not(inputs: dict[str, str]) -> list[str]:
    """backward_causes for BUF/NOT — single input."""
    return [p for p, v in inputs.items() if _norm(v) == 'x']


def backward_bufif(data_port: str, enable_port: str,
                   data_val: str, enable_val: str,
                   active_enable: str) -> list[str]:
    """backward_causes for tri-state buffers.

    active_enable: '0' for bufif0/notif0, '1' for bufif1/notif1.
    """
    d, e = _norm(data_val), _norm(enable_val)
    causes = []

    if e == 'x':
        causes.append(enable_port)
        if d == 'x':
            causes.append(data_port)
    elif e == active_enable:
        # Output is driven — if data is X, data is the cause
        if d == 'x':
            causes.append(data_port)
    # If enable is inactive (output is z), z is treated as x.
    # The enable being deterministically inactive means the z is "expected"
    # but z IS x for tracing purposes, so enable causes it.
    else:
        causes.append(enable_port)

    return causes
