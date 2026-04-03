#!/usr/bin/env python3
"""Generate synthetic VCD files for stress_edge test cases.

Timing model (matching real simulator VCD behavior):
- At posedge T: clock rises, FF Q values update (capture old D)
- At T+1: combinational signals update (D inputs, buf outputs) from new Q values
- At negedge T+HALF: clock falls

This ensures the tracer can look at D at time T-1 (before posedge) and see
the pre-capture value, while D at T+1 shows the post-capture combinational update.

VCD timescale: 1ps (matching -timescale 1ns/1ps; 1 VCD tick = 1ps)
Clock period: 10ns = 10000 ticks unless otherwise noted.
"""

import json
import os
from pathlib import Path

BASE = Path(__file__).parent


def _id_gen():
    """Generate unique VCD identifier codes using printable ASCII."""
    chars = []
    for c in range(33, 127):
        chars.append(chr(c))
    idx = 0
    while True:
        if idx < len(chars):
            yield chars[idx]
        else:
            i2 = idx - len(chars)
            yield chars[i2 // len(chars)] + chars[i2 % len(chars)]
        idx += 1


class VCDWriter:
    """Simple VCD writer that tracks signal values and only emits changes."""

    def __init__(self):
        self.signals = {}       # full_path -> (id_code, width, var_type)
        self.values = {}        # full_path -> current_value_str
        self._id_gen = _id_gen()
        self._scope_tree = {}
        self._lines = []
        self._time_pending = None

    def add_signal(self, scope_path, name, width=1, var_type='wire'):
        full_path = f"{scope_path}.{name}"
        id_code = next(self._id_gen)
        self.signals[full_path] = (id_code, width, var_type)
        self.values[full_path] = None
        parts = scope_path.split('.')
        node = self._scope_tree
        for p in parts:
            if p not in node:
                node[p] = {}
            node = node[p]
        if '__signals__' not in node:
            node['__signals__'] = []
        node['__signals__'].append((name, full_path, id_code, width, var_type))
        return full_path

    def _write_scope_tree(self, node, lines):
        for key in sorted(node.keys()):
            if key == '__signals__':
                continue
            lines.append(f"$scope module {key} $end")
            child = node[key]
            if '__signals__' in child:
                for name, _, id_code, width, var_type in child['__signals__']:
                    lines.append(f"$var {var_type} {width} {id_code} {name} $end")
            self._write_scope_tree(child, lines)
            lines.append("$upscope $end")

    def header(self):
        lines = ["$date", "    Mon Mar 30 12:00:00 2026", "$end",
                 "$version", "    Synthetic VCD Generator", "$end",
                 "$timescale", "    1ps", "$end", ""]
        self._write_scope_tree(self._scope_tree, lines)
        lines.append("$enddefinitions $end")
        return '\n'.join(lines) + '\n'

    def set_value(self, full_path, value):
        self.values[full_path] = value

    def emit_time(self, time):
        self._time_pending = time

    def _flush_time(self):
        if self._time_pending is not None:
            self._lines.append(f"#{self._time_pending}")
            self._time_pending = None

    def emit_changes(self, changes):
        actual = {}
        for path, val in changes.items():
            if self.values.get(path) != val:
                actual[path] = val
                self.values[path] = val
        if actual:
            self._flush_time()
            for path, val in actual.items():
                id_code, width, _ = self.signals[path]
                if width == 1:
                    self._lines.append(f"{val}{id_code}")
                else:
                    self._lines.append(f"b{val} {id_code}")

    def emit_dumpvars(self):
        self._flush_time()
        self._lines.append("$dumpvars")
        for path, (id_code, width, _) in sorted(self.signals.items()):
            val = self.values.get(path, 'x')
            if val is None:
                val = 'x'
            if width == 1:
                self._lines.append(f"{val}{id_code}")
            else:
                self._lines.append(f"b{val} {id_code}")
        self._lines.append("$end")

    def get_output(self):
        return self.header() + '\n'.join(self._lines) + '\n'


# ============================================================================
# Helper: gate evaluation functions
# ============================================================================
def xor_v(a, b):
    if a == 'x' or b == 'x': return 'x'
    return '1' if a != b else '0'

def and_v(a, b):
    if a == '0' or b == '0': return '0'
    if a == '1' and b == '1': return '1'
    return 'x'

def or_v(a, b):
    if a == '1' or b == '1': return '1'
    if a == '0' and b == '0': return '0'
    return 'x'

def bufif1_v(data, en):
    if en == '1': return data
    if en == '0': return 'z'
    return 'x'


# ============================================================================
# Test 1: deep_pipeline
# ============================================================================
def gen_deep_pipeline():
    NUM_STAGES = 104
    CLK_PERIOD = 10000
    HALF_CLK = CLK_PERIOD // 2

    w = VCDWriter()

    # Register all signals
    tb_clk = w.add_signal('tb', 'clk', var_type='reg')
    tb_rst_n = w.add_signal('tb', 'rst_n', var_type='reg')
    tb_data_in = w.add_signal('tb', 'data_in', var_type='reg')
    tb_final_out = w.add_signal('tb', 'final_out')
    dut_clk = w.add_signal('tb.dut', 'clk')
    dut_rst_n = w.add_signal('tb.dut', 'rst_n')
    dut_data_in = w.add_signal('tb.dut', 'data_in')
    dut_final_out = w.add_signal('tb.dut', 'final_out')

    ff_sigs = []  # [(Q, CLK, D, RST_N)]
    dut_ff_q = []
    dut_buf_o = []
    buf_sigs = []  # [(A, Y)]

    for i in range(NUM_STAGES):
        ff_sigs.append((
            w.add_signal(f'tb.dut.ff_{i}', 'Q'),
            w.add_signal(f'tb.dut.ff_{i}', 'CLK'),
            w.add_signal(f'tb.dut.ff_{i}', 'D'),
            w.add_signal(f'tb.dut.ff_{i}', 'RST_N'),
        ))
        dut_ff_q.append(w.add_signal('tb.dut', f'ff_q_{i}'))

    for i in range(NUM_STAGES - 1):
        dut_buf_o.append(w.add_signal('tb.dut', f'buf_o_{i}'))
        buf_sigs.append((
            w.add_signal(f'tb.dut.buf_{i}', 'A'),
            w.add_signal(f'tb.dut.buf_{i}', 'Y'),
        ))

    # State
    ff_state = ['0'] * NUM_STAGES
    rst_n = '0'; data_in = '0'
    force_ff0 = False

    def emit_clk_edge(changes, val):
        changes[tb_clk] = val; changes[dut_clk] = val
        for i in range(NUM_STAGES):
            changes[ff_sigs[i][1]] = val

    def emit_q(changes):
        for i in range(NUM_STAGES):
            changes[ff_sigs[i][0]] = ff_state[i]
            changes[dut_ff_q[i]] = ff_state[i]
        changes[dut_final_out] = ff_state[-1]
        changes[tb_final_out] = ff_state[-1]

    def emit_comb(changes):
        """Combinational: buf outputs and D inputs."""
        changes[ff_sigs[0][2]] = data_in  # ff_0.D = data_in
        changes[ff_sigs[0][3]] = rst_n
        for i in range(NUM_STAGES - 1):
            v = ff_state[i]
            changes[buf_sigs[i][0]] = v; changes[buf_sigs[i][1]] = v
            changes[dut_buf_o[i]] = v
            changes[ff_sigs[i+1][2]] = v  # ff_{i+1}.D
            changes[ff_sigs[i+1][3]] = rst_n
        # Also set RST_N and last ff RST_N
        for i in range(NUM_STAGES):
            changes[ff_sigs[i][3]] = rst_n

    def emit_inputs(changes):
        changes[tb_rst_n] = rst_n; changes[dut_rst_n] = rst_n
        changes[tb_data_in] = data_in; changes[dut_data_in] = data_in

    def do_capture():
        nonlocal ff_state
        if rst_n == '0':
            ff_state = ['0'] * NUM_STAGES
        else:
            new = [data_in] + ff_state[:NUM_STAGES-1]
            ff_state = new
        if force_ff0:
            ff_state[0] = 'x'

    # t=0 initial
    t = 0
    w.emit_time(0)
    ch = {}; emit_clk_edge(ch, '0'); emit_inputs(ch); emit_q(ch); emit_comb(ch)
    for k, v in ch.items(): w.set_value(k, v)
    w.emit_dumpvars()

    def clock_cycle():
        nonlocal t
        # posedge
        t += HALF_CLK
        do_capture()
        w.emit_time(t)
        ch = {}; emit_clk_edge(ch, '1'); emit_inputs(ch); emit_q(ch); w.emit_changes(ch)
        # combinational update T+1
        w.emit_time(t + 1)
        ch = {}; emit_comb(ch); w.emit_changes(ch)
        # negedge
        t += HALF_CLK
        w.emit_time(t)
        ch = {}; emit_clk_edge(ch, '0'); w.emit_changes(ch)

    # Phase 1: Reset 80ns
    while t + CLK_PERIOD <= 80000:
        clock_cycle()

    # Phase 2: Release reset
    rst_n = '1'; data_in = '1'
    for _ in range(20):
        clock_cycle()

    # Phase 3: Force ff_0.Q=x for 110 cycles (enough to fill 104-stage pipeline)
    force_ff0 = True
    for _ in range(110):
        clock_cycle()

    # Release
    force_ff0 = False

    # Phase 4: 20 more cycles (X still present at output since pipeline is full)
    for _ in range(20):
        clock_cycle()

    # Phase 5: 5 trailing cycles
    for _ in range(5):
        clock_cycle()

    return w.get_output()


# ============================================================================
# Test 2: wide_fanout
# ============================================================================
def gen_wide_fanout():
    CLK_PERIOD = 10000; HALF_CLK = CLK_PERIOD // 2
    w = VCDWriter()

    tb_clk = w.add_signal('tb', 'clk', var_type='reg')
    tb_rst_n = w.add_signal('tb', 'rst_n', var_type='reg')
    tb_src_in = w.add_signal('tb', 'src_in', var_type='reg')
    tb_final_out = w.add_signal('tb', 'final_out')
    tb_side_in = [w.add_signal('tb', f'side_in[{i}]', var_type='reg') for i in range(32)]
    dut_clk = w.add_signal('tb.dut', 'clk')
    dut_rst_n = w.add_signal('tb.dut', 'rst_n')
    dut_src_in = w.add_signal('tb.dut', 'src_in')
    dut_final_out = w.add_signal('tb.dut', 'final_out')
    dut_side_in = [w.add_signal('tb.dut', f'side_in[{i}]') for i in range(32)]

    # Source FF
    dut_src_q = w.add_signal('tb.dut', 'src_q')
    ff_src = (w.add_signal('tb.dut.ff_src', 'Q'), w.add_signal('tb.dut.ff_src', 'CLK'),
              w.add_signal('tb.dut.ff_src', 'D'), w.add_signal('tb.dut.ff_src', 'RST_N'))

    # 32 gate+FF paths
    side_in = ['1']*8 + ['0']*24  # AND needs 1, OR needs 0
    g_sigs = []; gate_inst = []; ff_p = []; p_sigs = []
    gate_names = []
    for i in range(32):
        g_sigs.append(w.add_signal('tb.dut', f'g_{i}'))
        p_sigs.append(w.add_signal('tb.dut', f'p_{i}'))
        if i < 8:    gn = f'and_{i}'
        elif i < 16: gn = f'or_{i}'
        elif i < 24: gn = f'xor_{i}'
        else:        gn = f'buf_{i}'
        gate_names.append(gn)
        ga = w.add_signal(f'tb.dut.{gn}', 'A')
        gy = w.add_signal(f'tb.dut.{gn}', 'Y')
        gb = w.add_signal(f'tb.dut.{gn}', 'B') if i < 24 else None
        gate_inst.append((ga, gb, gy))
        ff_p.append((w.add_signal(f'tb.dut.ff_p{i}', 'Q'),
                      w.add_signal(f'tb.dut.ff_p{i}', 'CLK'),
                      w.add_signal(f'tb.dut.ff_p{i}', 'D'),
                      w.add_signal(f'tb.dut.ff_p{i}', 'RST_N')))

    # XOR tree
    def make_xor_level(prefix, count):
        sigs = []; insts = []
        for i in range(count):
            sigs.append(w.add_signal('tb.dut', f'{prefix}_{i}'))
            insts.append((w.add_signal(f'tb.dut.{prefix.replace("t","xr")}_{i}', 'A'),
                          w.add_signal(f'tb.dut.{prefix.replace("t","xr")}_{i}', 'B'),
                          w.add_signal(f'tb.dut.{prefix.replace("t","xr")}_{i}', 'Y')))
        return sigs, insts

    # Fix xor tree naming to match netlist: xr1_0..xr1_15, etc
    t1_sigs = []; xr1 = []
    for i in range(16):
        t1_sigs.append(w.add_signal('tb.dut', f't1_{i}'))
        xr1.append((w.add_signal(f'tb.dut.xr1_{i}', 'A'),
                     w.add_signal(f'tb.dut.xr1_{i}', 'B'),
                     w.add_signal(f'tb.dut.xr1_{i}', 'Y')))
    t2_sigs = []; xr2 = []
    for i in range(8):
        t2_sigs.append(w.add_signal('tb.dut', f't2_{i}'))
        xr2.append((w.add_signal(f'tb.dut.xr2_{i}', 'A'),
                     w.add_signal(f'tb.dut.xr2_{i}', 'B'),
                     w.add_signal(f'tb.dut.xr2_{i}', 'Y')))
    t3_sigs = []; xr3 = []
    for i in range(4):
        t3_sigs.append(w.add_signal('tb.dut', f't3_{i}'))
        xr3.append((w.add_signal(f'tb.dut.xr3_{i}', 'A'),
                     w.add_signal(f'tb.dut.xr3_{i}', 'B'),
                     w.add_signal(f'tb.dut.xr3_{i}', 'Y')))
    t4_sigs = []; xr4 = []
    for i in range(2):
        t4_sigs.append(w.add_signal('tb.dut', f't4_{i}'))
        xr4.append((w.add_signal(f'tb.dut.xr4_{i}', 'A'),
                     w.add_signal(f'tb.dut.xr4_{i}', 'B'),
                     w.add_signal(f'tb.dut.xr4_{i}', 'Y')))
    t5_sig = w.add_signal('tb.dut', 't5_0')
    xr5 = (w.add_signal('tb.dut.xr5_0', 'A'),
            w.add_signal('tb.dut.xr5_0', 'B'),
            w.add_signal('tb.dut.xr5_0', 'Y'))

    # Output FF
    dut_out_q = w.add_signal('tb.dut', 'out_q')
    ff_out = (w.add_signal('tb.dut.ff_out', 'Q'), w.add_signal('tb.dut.ff_out', 'CLK'),
              w.add_signal('tb.dut.ff_out', 'D'), w.add_signal('tb.dut.ff_out', 'RST_N'))

    # State
    src_q = '0'; p_state = ['0']*32; out_q = '0'
    rst_n = '0'; src_in = '0'; force_src = False

    def gate_eval(i, sq):
        si = side_in[i]
        if i < 8:    return and_v(sq, si)
        elif i < 16: return or_v(sq, si)
        elif i < 24: return xor_v(sq, si)
        else:        return sq

    def xor_tree(pv):
        t1 = [xor_v(pv[2*i], pv[2*i+1]) for i in range(16)]
        t2 = [xor_v(t1[2*i], t1[2*i+1]) for i in range(8)]
        t3 = [xor_v(t2[2*i], t2[2*i+1]) for i in range(4)]
        t4 = [xor_v(t3[2*i], t3[2*i+1]) for i in range(2)]
        t5 = xor_v(t4[0], t4[1])
        return t1, t2, t3, t4, t5

    def emit_clk(ch, val):
        ch[tb_clk] = val; ch[dut_clk] = val
        ch[ff_src[1]] = val
        for i in range(32): ch[ff_p[i][1]] = val
        ch[ff_out[1]] = val

    def emit_q(ch):
        ch[ff_src[0]] = src_q; ch[dut_src_q] = src_q
        for i in range(32):
            ch[ff_p[i][0]] = p_state[i]; ch[p_sigs[i]] = p_state[i]
        ch[ff_out[0]] = out_q; ch[dut_out_q] = out_q
        ch[dut_final_out] = out_q; ch[tb_final_out] = out_q

    def emit_comb(ch):
        """Combinational: gate outputs, XOR tree, D inputs."""
        ch[tb_rst_n] = rst_n; ch[dut_rst_n] = rst_n
        ch[tb_src_in] = src_in; ch[dut_src_in] = src_in
        for i in range(32):
            ch[tb_side_in[i]] = side_in[i]; ch[dut_side_in[i]] = side_in[i]
        ch[ff_src[2]] = src_in; ch[ff_src[3]] = rst_n

        gate_outs = [gate_eval(i, src_q) for i in range(32)]
        for i in range(32):
            ch[g_sigs[i]] = gate_outs[i]
            ga, gb, gy = gate_inst[i]
            ch[ga] = src_q; ch[gy] = gate_outs[i]
            if gb is not None: ch[gb] = side_in[i]
            ch[ff_p[i][2]] = gate_outs[i]; ch[ff_p[i][3]] = rst_n

        t1, t2, t3, t4, t5 = xor_tree(p_state)
        for i in range(16):
            ch[t1_sigs[i]] = t1[i]
            ch[xr1[i][0]] = p_state[2*i]; ch[xr1[i][1]] = p_state[2*i+1]; ch[xr1[i][2]] = t1[i]
        for i in range(8):
            ch[t2_sigs[i]] = t2[i]
            ch[xr2[i][0]] = t1[2*i]; ch[xr2[i][1]] = t1[2*i+1]; ch[xr2[i][2]] = t2[i]
        for i in range(4):
            ch[t3_sigs[i]] = t3[i]
            ch[xr3[i][0]] = t2[2*i]; ch[xr3[i][1]] = t2[2*i+1]; ch[xr3[i][2]] = t3[i]
        for i in range(2):
            ch[t4_sigs[i]] = t4[i]
            ch[xr4[i][0]] = t3[2*i]; ch[xr4[i][1]] = t3[2*i+1]; ch[xr4[i][2]] = t4[i]
        ch[t5_sig] = t5
        ch[xr5[0]] = t4[0]; ch[xr5[1]] = t4[1]; ch[xr5[2]] = t5
        ch[ff_out[2]] = t5; ch[ff_out[3]] = rst_n

    def do_capture():
        nonlocal src_q, p_state, out_q
        if rst_n == '0':
            src_q = '0'; p_state = ['0']*32; out_q = '0'
        else:
            old_gate_outs = [gate_eval(i, src_q) for i in range(32)]
            _, _, _, _, old_t5 = xor_tree(p_state)
            src_q = src_in
            if force_src: src_q = 'x'
            p_state = old_gate_outs
            out_q = old_t5

    # t=0
    t = 0; w.emit_time(0)
    ch = {}; emit_clk(ch, '0'); emit_q(ch); emit_comb(ch)
    for k, v in ch.items(): w.set_value(k, v)
    w.emit_dumpvars()

    def clock_cycle():
        nonlocal t
        t += HALF_CLK; do_capture()
        w.emit_time(t); ch = {}; emit_clk(ch, '1'); emit_q(ch); w.emit_changes(ch)
        w.emit_time(t+1); ch = {}; emit_comb(ch); w.emit_changes(ch)
        t += HALF_CLK; w.emit_time(t); ch = {}; emit_clk(ch, '0'); w.emit_changes(ch)

    # Reset 80ns
    while t + CLK_PERIOD <= 80000: clock_cycle()
    # Release
    rst_n = '1'; src_in = '1'
    for _ in range(20): clock_cycle()
    # Force for 5 cycles (trace depth is 3, so 5 is generous)
    force_src = True
    for _ in range(5): clock_cycle()
    force_src = False
    # Propagation
    for _ in range(10): clock_cycle()
    for _ in range(5): clock_cycle()

    return w.get_output()


# ============================================================================
# Test 3: clock_crossing
# ============================================================================
def gen_clock_crossing():
    CLKA_HALF = 5000; CLKB_HALF = 7000
    w = VCDWriter()

    tb_clk_a = w.add_signal('tb', 'clk_a', var_type='reg')
    tb_clk_b = w.add_signal('tb', 'clk_b', var_type='reg')
    tb_rst_n = w.add_signal('tb', 'rst_n', var_type='reg')
    tb_data_in = w.add_signal('tb', 'data_in', var_type='reg')
    tb_final_out = w.add_signal('tb', 'final_out')
    dut_clk_a = w.add_signal('tb.dut', 'clk_a')
    dut_clk_b = w.add_signal('tb.dut', 'clk_b')
    dut_rst_n = w.add_signal('tb.dut', 'rst_n')
    dut_data_in = w.add_signal('tb.dut', 'data_in')
    dut_final_out = w.add_signal('tb.dut', 'final_out')

    wire_names = ['a_q0','a_q1','a_q2','a_buf0','a_buf1','sync_q0','sync_q1','sync_buf','b_q0','b_q1','b_buf0']
    dut_wires = {n: w.add_signal('tb.dut', n) for n in wire_names}

    ff_names_a = ['ff_a0','ff_a1','ff_a2']
    ff_names_sync = ['ff_sync0','ff_sync1']
    ff_names_b = ['ff_b0','ff_b1']
    all_ff_names = ff_names_a + ff_names_sync + ff_names_b
    ff_inst = {}
    for fn in all_ff_names:
        ff_inst[fn] = (w.add_signal(f'tb.dut.{fn}', 'Q'),
                       w.add_signal(f'tb.dut.{fn}', 'CLK'),
                       w.add_signal(f'tb.dut.{fn}', 'D'),
                       w.add_signal(f'tb.dut.{fn}', 'RST_N'))

    buf_names = ['buf_a0','buf_a1','buf_sync','buf_b0']
    buf_inst = {}
    for bn in buf_names:
        buf_inst[bn] = (w.add_signal(f'tb.dut.{bn}', 'A'),
                        w.add_signal(f'tb.dut.{bn}', 'Y'))

    # State: a_q[3], sync_q[2], b_q[2]
    a_q = ['0','0','0']; sync_q = ['0','0']; b_q = ['0','0']
    rst_n = '0'; data_in = '0'; clk_a = '0'; clk_b = '0'
    force_a0 = False

    def emit_all(ch):
        ch[tb_clk_a] = clk_a; ch[dut_clk_a] = clk_a
        ch[tb_clk_b] = clk_b; ch[dut_clk_b] = clk_b
        ch[tb_rst_n] = rst_n; ch[dut_rst_n] = rst_n
        ch[tb_data_in] = data_in; ch[dut_data_in] = data_in

        # Q values
        ch[dut_wires['a_q0']] = a_q[0]; ch[ff_inst['ff_a0'][0]] = a_q[0]
        ch[dut_wires['a_q1']] = a_q[1]; ch[ff_inst['ff_a1'][0]] = a_q[1]
        ch[dut_wires['a_q2']] = a_q[2]; ch[ff_inst['ff_a2'][0]] = a_q[2]
        ch[dut_wires['sync_q0']] = sync_q[0]; ch[ff_inst['ff_sync0'][0]] = sync_q[0]
        ch[dut_wires['sync_q1']] = sync_q[1]; ch[ff_inst['ff_sync1'][0]] = sync_q[1]
        ch[dut_wires['b_q0']] = b_q[0]; ch[ff_inst['ff_b0'][0]] = b_q[0]
        ch[dut_wires['b_q1']] = b_q[1]; ch[ff_inst['ff_b1'][0]] = b_q[1]
        ch[dut_final_out] = b_q[1]; ch[tb_final_out] = b_q[1]

        # CLK for each FF
        for fn in ff_names_a: ch[ff_inst[fn][1]] = clk_a
        for fn in ff_names_sync + ff_names_b: ch[ff_inst[fn][1]] = clk_b

        # Buf/comb
        ch[dut_wires['a_buf0']] = a_q[0]; ch[dut_wires['a_buf1']] = a_q[1]
        ch[buf_inst['buf_a0'][0]] = a_q[0]; ch[buf_inst['buf_a0'][1]] = a_q[0]
        ch[buf_inst['buf_a1'][0]] = a_q[1]; ch[buf_inst['buf_a1'][1]] = a_q[1]
        ch[dut_wires['sync_buf']] = sync_q[0]
        ch[buf_inst['buf_sync'][0]] = sync_q[0]; ch[buf_inst['buf_sync'][1]] = sync_q[0]
        ch[dut_wires['b_buf0']] = b_q[0]
        ch[buf_inst['buf_b0'][0]] = b_q[0]; ch[buf_inst['buf_b0'][1]] = b_q[0]

        # D inputs
        ch[ff_inst['ff_a0'][2]] = data_in; ch[ff_inst['ff_a0'][3]] = rst_n
        ch[ff_inst['ff_a1'][2]] = a_q[0]; ch[ff_inst['ff_a1'][3]] = rst_n  # buf transparent
        ch[ff_inst['ff_a2'][2]] = a_q[1]; ch[ff_inst['ff_a2'][3]] = rst_n
        ch[ff_inst['ff_sync0'][2]] = a_q[2]; ch[ff_inst['ff_sync0'][3]] = rst_n
        ch[ff_inst['ff_sync1'][2]] = sync_q[0]; ch[ff_inst['ff_sync1'][3]] = rst_n
        ch[ff_inst['ff_b0'][2]] = sync_q[1]; ch[ff_inst['ff_b0'][3]] = rst_n
        ch[ff_inst['ff_b1'][2]] = b_q[0]; ch[ff_inst['ff_b1'][3]] = rst_n

    def emit_q_only(ch):
        """Only Q values and final_out - for posedge update."""
        ch[dut_wires['a_q0']] = a_q[0]; ch[ff_inst['ff_a0'][0]] = a_q[0]
        ch[dut_wires['a_q1']] = a_q[1]; ch[ff_inst['ff_a1'][0]] = a_q[1]
        ch[dut_wires['a_q2']] = a_q[2]; ch[ff_inst['ff_a2'][0]] = a_q[2]
        ch[dut_wires['sync_q0']] = sync_q[0]; ch[ff_inst['ff_sync0'][0]] = sync_q[0]
        ch[dut_wires['sync_q1']] = sync_q[1]; ch[ff_inst['ff_sync1'][0]] = sync_q[1]
        ch[dut_wires['b_q0']] = b_q[0]; ch[ff_inst['ff_b0'][0]] = b_q[0]
        ch[dut_wires['b_q1']] = b_q[1]; ch[ff_inst['ff_b1'][0]] = b_q[1]
        ch[dut_final_out] = b_q[1]; ch[tb_final_out] = b_q[1]

    def emit_comb_only(ch):
        """Combinational signals only."""
        ch[dut_wires['a_buf0']] = a_q[0]; ch[dut_wires['a_buf1']] = a_q[1]
        ch[buf_inst['buf_a0'][0]] = a_q[0]; ch[buf_inst['buf_a0'][1]] = a_q[0]
        ch[buf_inst['buf_a1'][0]] = a_q[1]; ch[buf_inst['buf_a1'][1]] = a_q[1]
        ch[dut_wires['sync_buf']] = sync_q[0]
        ch[buf_inst['buf_sync'][0]] = sync_q[0]; ch[buf_inst['buf_sync'][1]] = sync_q[0]
        ch[dut_wires['b_buf0']] = b_q[0]
        ch[buf_inst['buf_b0'][0]] = b_q[0]; ch[buf_inst['buf_b0'][1]] = b_q[0]
        ch[ff_inst['ff_a0'][2]] = data_in
        ch[ff_inst['ff_a1'][2]] = a_q[0]
        ch[ff_inst['ff_a2'][2]] = a_q[1]
        ch[ff_inst['ff_sync0'][2]] = a_q[2]
        ch[ff_inst['ff_sync1'][2]] = sync_q[0]
        ch[ff_inst['ff_b0'][2]] = sync_q[1]
        ch[ff_inst['ff_b1'][2]] = b_q[0]

    # Event-driven simulation with two clocks
    # Group simultaneous events to avoid time-decrease in VCD
    SIM_END = 800000
    events = []
    ta = CLKA_HALF
    while ta <= SIM_END:
        events.append((ta, 'a')); ta += CLKA_HALF
    tb_ = CLKB_HALF
    while tb_ <= SIM_END:
        events.append((tb_, 'b')); tb_ += CLKB_HALF
    events.sort(key=lambda x: (x[0], x[1]))

    # Group events by time
    grouped = []
    i = 0
    while i < len(events):
        t_cur = events[i][0]
        group = []
        while i < len(events) and events[i][0] == t_cur:
            group.append(events[i][1])
            i += 1
        grouped.append((t_cur, group))

    # t=0
    w.emit_time(0); ch = {}; emit_all(ch)
    for k, v in ch.items(): w.set_value(k, v)
    w.emit_dumpvars()

    posedge_a_count = 0; reset_released = False
    force_start_a = None; force_released = False
    posedge_b_after_release = 0; done = False

    for t, evt_types in grouped:
        if done: break

        any_captured = False
        for evt_type in evt_types:
            if evt_type == 'a':
                if clk_a == '0':
                    clk_a = '1'
                    if rst_n == '0':
                        a_q = ['0','0','0']
                    else:
                        new_a = [data_in, a_q[0], a_q[1]]
                        a_q = new_a
                        if force_a0: a_q[0] = 'x'
                    if reset_released: posedge_a_count += 1
                    any_captured = True
                else:
                    clk_a = '0'
            elif evt_type == 'b':
                if clk_b == '0':
                    clk_b = '1'
                    if rst_n == '0':
                        sync_q = ['0','0']; b_q = ['0','0']
                    else:
                        new_sync = [a_q[2], sync_q[0]]
                        new_b = [sync_q[1], b_q[0]]
                        sync_q = new_sync; b_q = new_b
                    if force_released: posedge_b_after_release += 1
                    any_captured = True
                else:
                    clk_b = '0'

        # Phase transitions
        if not reset_released and t >= 100000:
            rst_n = '1'; data_in = '1'; reset_released = True; posedge_a_count = 0
        if reset_released and not force_a0 and not force_released and posedge_a_count >= 31:
            if 'a' in evt_types and clk_a == '1':
                force_a0 = True; force_start_a = posedge_a_count; a_q[0] = 'x'
        if force_a0 and force_start_a is not None and posedge_a_count >= force_start_a + 3:
            force_a0 = False; force_released = True
        if force_released and posedge_b_after_release >= 26: done = True

        # Emit: clocks + Q at event time, comb at event time + 1
        w.emit_time(t); ch = {}
        ch[tb_clk_a] = clk_a; ch[dut_clk_a] = clk_a
        ch[tb_clk_b] = clk_b; ch[dut_clk_b] = clk_b
        ch[tb_rst_n] = rst_n; ch[dut_rst_n] = rst_n; ch[tb_data_in] = data_in; ch[dut_data_in] = data_in
        for fn in ff_names_a: ch[ff_inst[fn][1]] = clk_a
        for fn in ff_names_sync + ff_names_b: ch[ff_inst[fn][1]] = clk_b
        if any_captured:
            emit_q_only(ch)
        w.emit_changes(ch)
        if any_captured:
            w.emit_time(t + 1); ch = {}; emit_comb_only(ch); w.emit_changes(ch)

    return w.get_output()


# ============================================================================
# Test 4: tristate_bus
# ============================================================================
def gen_tristate_bus():
    CLK_PERIOD = 10000; HALF_CLK = CLK_PERIOD // 2
    w = VCDWriter()

    tb_clk = w.add_signal('tb', 'clk', var_type='reg')
    tb_rst_n = w.add_signal('tb', 'rst_n', var_type='reg')
    tb_final_out = w.add_signal('tb', 'final_out')
    tb_drv_data = [w.add_signal('tb', f'drv_data[{i}]', var_type='reg') for i in range(4)]
    tb_drv_en = [w.add_signal('tb', f'drv_en[{i}]', var_type='reg') for i in range(4)]
    dut_clk = w.add_signal('tb.dut', 'clk')
    dut_rst_n = w.add_signal('tb.dut', 'rst_n')
    dut_final_out = w.add_signal('tb.dut', 'final_out')
    dut_drv_data = [w.add_signal('tb.dut', f'drv_data[{i}]') for i in range(4)]
    dut_drv_en = [w.add_signal('tb.dut', f'drv_en[{i}]') for i in range(4)]

    ff_d_inst = []
    dut_dq = []
    for i in range(4):
        ff_d_inst.append((w.add_signal(f'tb.dut.ff_d{i}', 'Q'),
                          w.add_signal(f'tb.dut.ff_d{i}', 'CLK'),
                          w.add_signal(f'tb.dut.ff_d{i}', 'D'),
                          w.add_signal(f'tb.dut.ff_d{i}', 'RST_N')))
        dut_dq.append(w.add_signal('tb.dut', f'd{i}_q'))

    dut_bus = w.add_signal('tb.dut', 'bus')
    tri_inst = []
    for i in range(4):
        tri_inst.append((w.add_signal(f'tb.dut.tri_d{i}', 'A'),
                         w.add_signal(f'tb.dut.tri_d{i}', 'B'),
                         w.add_signal(f'tb.dut.tri_d{i}', 'Y')))

    ff_recv = (w.add_signal('tb.dut.ff_recv', 'Q'), w.add_signal('tb.dut.ff_recv', 'CLK'),
               w.add_signal('tb.dut.ff_recv', 'D'), w.add_signal('tb.dut.ff_recv', 'RST_N'))
    dut_recv_q = w.add_signal('tb.dut', 'recv_q')

    buf_out = (w.add_signal('tb.dut.buf_out', 'A'), w.add_signal('tb.dut.buf_out', 'Y'))
    dut_out_buf = w.add_signal('tb.dut', 'out_buf')

    ff_out = (w.add_signal('tb.dut.ff_out', 'Q'), w.add_signal('tb.dut.ff_out', 'CLK'),
              w.add_signal('tb.dut.ff_out', 'D'), w.add_signal('tb.dut.ff_out', 'RST_N'))
    dut_out_q = w.add_signal('tb.dut', 'out_q')

    # State
    drv_data = ['0','1','0','1']; drv_en = ['0','0','0','0']
    d_q = ['0']*4; recv_q = '0'; out_q = '0'
    rst_n = '0'; force_d2 = False

    def resolve_bus():
        active = []
        for i in range(4):
            v = bufif1_v(d_q[i], drv_en[i])
            if v != 'z': active.append(v)
        if not active: return 'z'
        if len(active) == 1: return active[0]
        if all(a == active[0] for a in active): return active[0]
        return 'x'

    def emit_q(ch):
        for i in range(4):
            ch[ff_d_inst[i][0]] = d_q[i]; ch[dut_dq[i]] = d_q[i]
        ch[ff_recv[0]] = recv_q; ch[dut_recv_q] = recv_q
        ch[ff_out[0]] = out_q; ch[dut_out_q] = out_q
        ch[dut_final_out] = out_q; ch[tb_final_out] = out_q

    def emit_comb(ch):
        bus = resolve_bus()
        ch[dut_bus] = bus
        for i in range(4):
            ch[tri_inst[i][0]] = d_q[i]; ch[tri_inst[i][1]] = drv_en[i]
            ch[tri_inst[i][2]] = bufif1_v(d_q[i], drv_en[i])
            ch[ff_d_inst[i][2]] = drv_data[i]; ch[ff_d_inst[i][3]] = rst_n
        ch[ff_recv[2]] = bus; ch[ff_recv[3]] = rst_n
        ch[buf_out[0]] = recv_q; ch[buf_out[1]] = recv_q
        ch[dut_out_buf] = recv_q
        ch[ff_out[2]] = recv_q; ch[ff_out[3]] = rst_n
        for i in range(4):
            ch[tb_drv_data[i]] = drv_data[i]; ch[dut_drv_data[i]] = drv_data[i]
            ch[tb_drv_en[i]] = drv_en[i]; ch[dut_drv_en[i]] = drv_en[i]
        ch[tb_rst_n] = rst_n; ch[dut_rst_n] = rst_n

    def emit_clk(ch, val):
        ch[tb_clk] = val; ch[dut_clk] = val
        for i in range(4): ch[ff_d_inst[i][1]] = val
        ch[ff_recv[1]] = val; ch[ff_out[1]] = val

    def do_capture():
        nonlocal d_q, recv_q, out_q
        if rst_n == '0':
            d_q = ['0']*4; recv_q = '0'; out_q = '0'
        else:
            old_bus = resolve_bus()
            old_recv = recv_q
            d_q = list(drv_data)
            if force_d2: d_q[2] = 'x'
            recv_q = old_bus
            out_q = old_recv

    t = 0; w.emit_time(0)
    ch = {}; emit_clk(ch, '0'); emit_q(ch); emit_comb(ch)
    for k, v in ch.items(): w.set_value(k, v)
    w.emit_dumpvars()

    def clock_cycle():
        nonlocal t
        t += HALF_CLK; do_capture()
        w.emit_time(t); ch = {}; emit_clk(ch, '1'); emit_q(ch); w.emit_changes(ch)
        w.emit_time(t+1); ch = {}; emit_comb(ch); w.emit_changes(ch)
        t += HALF_CLK; w.emit_time(t); ch = {}; emit_clk(ch, '0'); w.emit_changes(ch)

    # Reset
    while t + CLK_PERIOD <= 80000: clock_cycle()
    rst_n = '1'; drv_en = ['1','0','0','0']; drv_data = ['0','1','0','1']
    for _ in range(20): clock_cycle()
    # Switch to driver 2
    drv_en = ['0','0','1','0']; drv_data[2] = '1'
    clock_cycle(); clock_cycle()
    # Force
    force_d2 = True
    for _ in range(3): clock_cycle()
    force_d2 = False
    for _ in range(15): clock_cycle()

    return w.get_output()


# ============================================================================
# Test 5: nested_clock_gate
# ============================================================================
def gen_nested_clock_gate():
    CLK_PERIOD = 10000; HALF_CLK = CLK_PERIOD // 2
    w = VCDWriter()

    tb_clk = w.add_signal('tb', 'clk', var_type='reg')
    tb_rst_n = w.add_signal('tb', 'rst_n', var_type='reg')
    tb_en1 = w.add_signal('tb', 'en1', var_type='reg')
    tb_en2 = w.add_signal('tb', 'en2', var_type='reg')
    tb_en3 = w.add_signal('tb', 'en3', var_type='reg')
    tb_data_a = w.add_signal('tb', 'data_a', var_type='reg')
    tb_data_b = w.add_signal('tb', 'data_b', var_type='reg')
    tb_data_c = w.add_signal('tb', 'data_c', var_type='reg')
    tb_data_d = w.add_signal('tb', 'data_d', var_type='reg')
    tb_out_a = w.add_signal('tb', 'out_a')
    tb_out_b = w.add_signal('tb', 'out_b')
    tb_out_c = w.add_signal('tb', 'out_c')
    tb_out_d = w.add_signal('tb', 'out_d')
    tb_final_out = w.add_signal('tb', 'final_out')

    dut_clk = w.add_signal('tb.dut', 'clk')
    dut_rst_n = w.add_signal('tb.dut', 'rst_n')
    dut_en1 = w.add_signal('tb.dut', 'en1')
    dut_en2 = w.add_signal('tb.dut', 'en2')
    dut_en3 = w.add_signal('tb.dut', 'en3')
    dut_data_a = w.add_signal('tb.dut', 'data_a')
    dut_data_b = w.add_signal('tb.dut', 'data_b')
    dut_data_c = w.add_signal('tb.dut', 'data_c')
    dut_data_d = w.add_signal('tb.dut', 'data_d')
    dut_out_a = w.add_signal('tb.dut', 'out_a')
    dut_out_b = w.add_signal('tb.dut', 'out_b')
    dut_out_c = w.add_signal('tb.dut', 'out_c')
    dut_out_d = w.add_signal('tb.dut', 'out_d')
    dut_final_out = w.add_signal('tb.dut', 'final_out')
    dut_gclk_l1 = w.add_signal('tb.dut', 'gclk_l1')
    dut_gclk_l2 = w.add_signal('tb.dut', 'gclk_l2')
    dut_gclk_l3 = w.add_signal('tb.dut', 'gclk_l3')

    # ICG instances
    icg = {}
    for lvl in [1,2,3]:
        n = f'icg_l{lvl}'
        icg[n] = {
            'CLK': w.add_signal(f'tb.dut.{n}', 'CLK'),
            'EN': w.add_signal(f'tb.dut.{n}', 'EN'),
            'en_lat': w.add_signal(f'tb.dut.{n}', 'en_lat', var_type='reg'),
            'GCLK': w.add_signal(f'tb.dut.{n}', 'GCLK'),
            'and_A': w.add_signal(f'tb.dut.{n}.and_gate', 'A'),
            'and_B': w.add_signal(f'tb.dut.{n}.and_gate', 'B'),
            'and_Y': w.add_signal(f'tb.dut.{n}.and_gate', 'Y'),
        }

    ff = {}
    for fn in ['ff_a','ff_b','ff_c','ff_d']:
        ff[fn] = (w.add_signal(f'tb.dut.{fn}', 'Q'), w.add_signal(f'tb.dut.{fn}', 'CLK'),
                  w.add_signal(f'tb.dut.{fn}', 'D'), w.add_signal(f'tb.dut.{fn}', 'RST_N'))
    dut_qa = w.add_signal('tb.dut', 'qa')
    dut_qb = w.add_signal('tb.dut', 'qb')
    dut_qc = w.add_signal('tb.dut', 'qc')
    dut_qd = w.add_signal('tb.dut', 'qd')
    dut_xor_ab = w.add_signal('tb.dut', 'xor_ab')
    dut_xor_cd = w.add_signal('tb.dut', 'xor_cd')
    xor_inst = {}
    for gn in ['xor_g1','xor_g2','xor_g3']:
        xor_inst[gn] = (w.add_signal(f'tb.dut.{gn}', 'A'),
                        w.add_signal(f'tb.dut.{gn}', 'B'),
                        w.add_signal(f'tb.dut.{gn}', 'Y'))

    # State
    clk = '0'; rst_n = '0'
    en1 = '0'; en2 = '0'; en3 = '0'
    data_a = '0'; data_b = '0'; data_c = '0'; data_d = '0'
    en_lat1 = '0'; en_lat2 = '0'; en_lat3 = '0'
    qa = '0'; qb = '0'; qc = '0'; qd = '0'
    force_en3 = False
    prev_gclk1 = '0'; prev_gclk2 = '0'; prev_gclk3 = '0'

    def compute_gclks():
        el3 = 'x' if force_en3 else en_lat3
        g1 = and_v(clk, en_lat1)
        g2 = and_v(g1, en_lat2)
        g3 = and_v(g2, el3)
        return g1, g2, g3

    def update_latches():
        nonlocal en_lat1, en_lat2, en_lat3
        # Latch transparent when input CLK is low
        if clk == '0': en_lat1 = en1
        g1 = and_v(clk, en_lat1)
        if g1 == '0': en_lat2 = en2
        g2 = and_v(g1, en_lat2)
        if g2 == '0' and not force_en3: en_lat3 = en3

    def update_ffs():
        nonlocal qa, qb, qc, qd, prev_gclk1, prev_gclk2, prev_gclk3
        g1, g2, g3 = compute_gclks()
        if rst_n == '0':
            qa = '0'; qb = '0'; qc = '0'; qd = '0'
        else:
            if g3 == 'x':
                qa = 'x'; qb = 'x'
            elif prev_gclk3 == '0' and g3 == '1':
                qa = data_a; qb = data_b
            if prev_gclk2 == '0' and g2 == '1':
                qc = data_c
            if prev_gclk1 == '0' and g1 == '1':
                qd = data_d
        prev_gclk1 = g1; prev_gclk2 = g2; prev_gclk3 = g3

    def emit_all(ch):
        g1, g2, g3 = compute_gclks()
        el3 = 'x' if force_en3 else en_lat3
        ch[tb_clk] = clk; ch[dut_clk] = clk
        ch[tb_rst_n] = rst_n; ch[dut_rst_n] = rst_n
        ch[tb_en1] = en1; ch[dut_en1] = en1
        ch[tb_en2] = en2; ch[dut_en2] = en2
        ch[tb_en3] = en3; ch[dut_en3] = en3
        ch[tb_data_a] = data_a; ch[dut_data_a] = data_a
        ch[tb_data_b] = data_b; ch[dut_data_b] = data_b
        ch[tb_data_c] = data_c; ch[dut_data_c] = data_c
        ch[tb_data_d] = data_d; ch[dut_data_d] = data_d

        ch[dut_gclk_l1] = g1; ch[dut_gclk_l2] = g2; ch[dut_gclk_l3] = g3
        ch[icg['icg_l1']['CLK']] = clk; ch[icg['icg_l1']['EN']] = en1
        ch[icg['icg_l1']['en_lat']] = en_lat1; ch[icg['icg_l1']['GCLK']] = g1
        ch[icg['icg_l1']['and_A']] = clk; ch[icg['icg_l1']['and_B']] = en_lat1; ch[icg['icg_l1']['and_Y']] = g1
        ch[icg['icg_l2']['CLK']] = g1; ch[icg['icg_l2']['EN']] = en2
        ch[icg['icg_l2']['en_lat']] = en_lat2; ch[icg['icg_l2']['GCLK']] = g2
        ch[icg['icg_l2']['and_A']] = g1; ch[icg['icg_l2']['and_B']] = en_lat2; ch[icg['icg_l2']['and_Y']] = g2
        ch[icg['icg_l3']['CLK']] = g2; ch[icg['icg_l3']['EN']] = en3
        ch[icg['icg_l3']['en_lat']] = el3; ch[icg['icg_l3']['GCLK']] = g3
        ch[icg['icg_l3']['and_A']] = g2; ch[icg['icg_l3']['and_B']] = el3; ch[icg['icg_l3']['and_Y']] = g3

        ch[ff['ff_a'][0]] = qa; ch[ff['ff_a'][1]] = g3; ch[ff['ff_a'][2]] = data_a; ch[ff['ff_a'][3]] = rst_n
        ch[ff['ff_b'][0]] = qb; ch[ff['ff_b'][1]] = g3; ch[ff['ff_b'][2]] = data_b; ch[ff['ff_b'][3]] = rst_n
        ch[ff['ff_c'][0]] = qc; ch[ff['ff_c'][1]] = g2; ch[ff['ff_c'][2]] = data_c; ch[ff['ff_c'][3]] = rst_n
        ch[ff['ff_d'][0]] = qd; ch[ff['ff_d'][1]] = g1; ch[ff['ff_d'][2]] = data_d; ch[ff['ff_d'][3]] = rst_n
        ch[dut_qa] = qa; ch[dut_qb] = qb; ch[dut_qc] = qc; ch[dut_qd] = qd

        xab = xor_v(qa, qb); xcd = xor_v(qc, qd); fo = xor_v(xab, xcd)
        ch[dut_xor_ab] = xab; ch[dut_xor_cd] = xcd
        ch[xor_inst['xor_g1'][0]] = qa; ch[xor_inst['xor_g1'][1]] = qb; ch[xor_inst['xor_g1'][2]] = xab
        ch[xor_inst['xor_g2'][0]] = qc; ch[xor_inst['xor_g2'][1]] = qd; ch[xor_inst['xor_g2'][2]] = xcd
        ch[xor_inst['xor_g3'][0]] = xab; ch[xor_inst['xor_g3'][1]] = xcd; ch[xor_inst['xor_g3'][2]] = fo
        ch[tb_out_a] = qa; ch[dut_out_a] = qa
        ch[tb_out_b] = qb; ch[dut_out_b] = qb
        ch[tb_out_c] = qc; ch[dut_out_c] = qc
        ch[tb_out_d] = qd; ch[dut_out_d] = qd
        ch[tb_final_out] = fo; ch[dut_final_out] = fo

    # t=0
    tc = 0; w.emit_time(0)
    ch = {}; emit_all(ch)
    for k, v in ch.items(): w.set_value(k, v)
    w.emit_dumpvars()

    def half_cycle():
        nonlocal tc, clk
        tc += HALF_CLK
        clk = '1' if clk == '0' else '0'
        update_latches()
        update_ffs()
        w.emit_time(tc); ch = {}; emit_all(ch); w.emit_changes(ch)

    def full_cycle():
        half_cycle(); half_cycle()

    # Reset 80ns
    for _ in range(8): full_cycle()
    # Release
    rst_n = '1'; en1 = '1'; en2 = '1'; en3 = '1'
    data_a = '1'; data_b = '0'; data_c = '1'; data_d = '0'
    for _ in range(20): full_cycle()
    # Force en_lat3 = x
    half_cycle()  # posedge
    force_en3 = True
    update_ffs()
    w.emit_time(tc); ch = {}; emit_all(ch); w.emit_changes(ch)
    half_cycle()  # negedge
    # Toggle data for 5 cycles
    for _ in range(5):
        data_a = '0' if data_a == '1' else '1'
        data_b = '0' if data_b == '1' else '1'
        full_cycle()
    for _ in range(5): full_cycle()
    force_en3 = False
    for _ in range(15): full_cycle()

    return w.get_output()


# ============================================================================
# Main
# ============================================================================
def main():
    tests = [
        ('deep_pipeline', gen_deep_pipeline),
        ('wide_fanout', gen_wide_fanout),
        ('clock_crossing', gen_clock_crossing),
        ('tristate_bus', gen_tristate_bus),
        ('nested_clock_gate', gen_nested_clock_gate),
    ]
    for name, gen_fn in tests:
        print(f"Generating VCD for {name}...")
        try:
            vcd_content = gen_fn()
            out_path = BASE / name / 'sim.vcd'
            out_path.write_text(vcd_content)
            print(f"  -> {out_path} ({len(vcd_content)} bytes)")
        except Exception as e:
            print(f"  FAILED: {e}")
            import traceback; traceback.print_exc()

if __name__ == '__main__':
    main()
