"""GateModel: unified interface for gate X-propagation evaluation.

Combines Verilog primitive truth tables (Tier 1) with standard cell
pattern matching (Tier 2) and conservative fallback (Tier 4).
"""

from . import primitives as P
from .cells import identify_cell, forward_cell, backward_cell, strip_cell_name

# Verilog primitive types
_PRIMITIVES = {
    'and', 'nand', 'or', 'nor', 'xor', 'xnor',
    'not', 'buf',
    'bufif0', 'bufif1', 'notif0', 'notif1',
}

# Map primitives to their eval functions (multi-input)
_MULTI_INPUT_FN = {
    'and': P.eval_and,
    'nand': P.eval_nand,
    'or': P.eval_or,
    'nor': P.eval_nor,
    'xor': P.eval_xor,
    'xnor': P.eval_xnor,
}

# Tri-state primitives
_TRISTATE = {'bufif0', 'bufif1', 'notif0', 'notif1'}
_TRISTATE_FN = {
    'bufif0': P.eval_bufif0,
    'bufif1': P.eval_bufif1,
    'notif0': P.eval_notif0,
    'notif1': P.eval_notif1,
}
_TRISTATE_ACTIVE = {
    'bufif0': '0',
    'bufif1': '1',
    'notif0': '0',
    'notif1': '1',
}


class GateModel:
    """X-propagation model for gate-level evaluation.

    Supports:
    - Tier 1: Verilog primitives (and, or, xor, not, buf, tri-state)
    - Tier 2: Standard cell families (pattern-matched from cell_type)
    - Tier 4: Conservative fallback for unknown cells
    """

    def forward(self, cell_type: str, inputs: dict[str, str]) -> str:
        """Compute output value given cell type and input values.

        inputs: {port_name: value} where value is '0','1','x','z'
        Returns: '0','1','x', or 'z'
        """
        ct = cell_type.lower()

        # Tier 1: Verilog primitives
        if ct in _MULTI_INPUT_FN:
            vals = self._get_ordered_inputs(inputs)
            return _MULTI_INPUT_FN[ct](vals)

        if ct == 'not':
            val = inputs.get('in0', next(iter(inputs.values()), 'x'))
            return P.eval_not(val)

        if ct == 'buf':
            val = inputs.get('in0', next(iter(inputs.values()), 'x'))
            return P.eval_buf(val)

        if ct in _TRISTATE:
            data = inputs.get('in0', inputs.get('A', inputs.get('data', 'x')))
            enable = inputs.get('in1', inputs.get('B', inputs.get('enable', 'x')))
            return _TRISTATE_FN[ct](data, enable)

        # Also handle "assign" as a buffer
        if ct == 'assign':
            val = next(iter(inputs.values()), 'x')
            return P.eval_buf(val)

        # Tier 2: Standard cell pattern matching
        info = identify_cell(cell_type)
        if info is not None:
            return forward_cell(info, inputs)

        # Tier 4: Conservative fallback
        for v in inputs.values():
            if P._norm(v) == 'x':
                return 'x'
        return '0'

    def backward_causes(self, cell_type: str,
                        inputs: dict[str, str]) -> list[str]:
        """Return input port names that are X and causally responsible
        for the output being X.

        Returns empty list if cell_type is unknown AND has no X inputs.
        For unknown cells, returns ALL X-valued ports (conservative).
        """
        ct = cell_type.lower()

        # Tier 1: Verilog primitives
        if ct in ('and', 'nand'):
            return P.backward_and_or('and', inputs)
        if ct in ('or', 'nor'):
            return P.backward_and_or('or', inputs)
        if ct in ('xor', 'xnor'):
            return P.backward_xor_xnor(inputs)
        if ct in ('not', 'buf'):
            return P.backward_buf_not(inputs)
        if ct in _TRISTATE:
            active = _TRISTATE_ACTIVE[ct]
            data_port = 'in0' if 'in0' in inputs else ('A' if 'A' in inputs else 'data')
            enable_port = 'in1' if 'in1' in inputs else ('B' if 'B' in inputs else 'enable')
            return P.backward_bufif(
                data_port, enable_port,
                inputs.get(data_port, 'x'),
                inputs.get(enable_port, 'x'),
                active)
        if ct == 'assign':
            return P.backward_buf_not(inputs)

        # Tier 2: Standard cell
        info = identify_cell(cell_type)
        if info is not None:
            return backward_cell(info, inputs)

        # Tier 4: Conservative fallback — all X-valued ports
        return [p for p, v in inputs.items() if P._norm(v) == 'x']

    def is_known_cell(self, cell_type: str) -> bool:
        """Return True if the gate model knows how to evaluate this cell type."""
        ct = cell_type.lower()
        if ct in _PRIMITIVES or ct == 'assign':
            return True
        return identify_cell(cell_type) is not None

    @staticmethod
    def _get_ordered_inputs(inputs: dict[str, str]) -> list[str]:
        """Extract input values in port order (in0, in1, ...) or (A, B, C, ...)."""
        if 'in0' in inputs:
            i = 0
            vals = []
            while f'in{i}' in inputs:
                vals.append(inputs[f'in{i}'])
                i += 1
            return vals
        # Try alphabetical port names
        return [inputs[k] for k in sorted(inputs.keys())]
