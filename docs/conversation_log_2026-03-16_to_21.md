# X-Tracer Build Session — 2026-03-16 to 2026-03-21

## Overview

Built a complete X-tracer tool for Verilog gate-level netlists: from testcase
generation through implementation to a working CLI. The tool traces backward
from an X signal through the netlist to find the root cause.

---

## Phase 1: Synthetic Testcase Generation (Mar 16)

### Launched parallel agents (S1, S2, S3)

Orchestrator: `/home/ubuntu/x-tracer-agents/gen_synthetic.py`

Each agent ran as `claude -p --dangerously-skip-permissions` subprocess,
writing a Python generator script that produces Verilog testcases, simulates
them with iverilog, validates them, and registers them.

- **S1 (gates)**: Cross-product of gate_type × arity × injected_input × non_x_values
- **S2 (structural)**: carry_chain, ff_chain, reconverge, mux_tree, reset_chain, bus_encoder
- **S3 (multibit)**: partial_bus_gate, bit_slice, multibit_mux, shift_reg, reduction, bit_interleave

### Issues encountered

1. **S2 hit 32K output token limit** — Fixed by setting `CLAUDE_CODE_MAX_OUTPUT_TOKENS=100000`
2. **Multi-injection testcases** — 272 cases injected X on multiple signals simultaneously.
   Added Layer 5 validation (single injection check) to `validate.py`. Pruned violating cases.
3. **Python .format() vs JSON braces** — `KeyError` from `{` in JSON. Fixed by using
   `str.replace("SPEC_PLACEHOLDER", spec)` instead of `.format()`.
4. **Concurrent registry writes** — Solved with `fcntl.flock` + git commit in `registry_update.py`.

### Final testcase counts

| Tier | Cases | Description |
|------|-------|-------------|
| S1 | 302 | Gate primitives, single-input injection |
| S2 | 23 | Structural templates |
| S3 | 67 | Multi-bit bus operations |
| **Total** | **392** | |

---

## Phase 2: Implementation Research & Review (Mar 16-17)

### Researched options for each module

Three research agents ran in parallel:

1. **Netlist parsing**: pyslang (chosen), pyverilog (rejected—abandoned), tree-sitter-sv
   (rejected—no semantics), regex (rejected—fragile)
2. **VCD parsing**: pywellen (chosen—Rust, 100+ MB/s), pyvcd (fallback—pure Python),
   vcdvcd (rejected)
3. **Graph + Gate model**: Plain dicts (chosen), igraph (upgrade path), table-driven
   gate model with conservative fallback

### Adversarial review with Codex (2 rounds via discuss.py)

Key concessions from the review:
- Added formal semantic specification (`docs/SEMANTIC_SPEC.md`)
- Changed `signal_to_driver` → `signal_to_drivers` (list) for multi-driver nets
- Added 9 root cause types (was just `injection_target`)
- Documented v1 scope limitations (no timing violations, strength, delta-cycle races)
- Documented VCD observability boundary

---

## Phase 3: Module Implementation (Mar 17)

### Phase 3a: Agents A, B, C in parallel

| Agent | Module | Tests | Time |
|-------|--------|-------|------|
| A | Netlist Parser (pyslang) | 23 pass | ~8 min |
| B | VCD Database (pywellen/pyvcd) | 24 pass | ~12 min |
| C | Gate Model (table-driven) | 118 pass | ~8 min |

### Phase 3b: Agent D (sequential)

| Agent | Module | Tests | Time |
|-------|--------|-------|------|
| D | Tracer Core | 45 pass | ~10 min |

Tested against 35 real golden testcases (gates, structural, multibit).

### Phase 3c: Agent E (sequential)

| Agent | Module | Tests | Time |
|-------|--------|-------|------|
| E | CLI + Integration | 21 pass | ~8 min |

Created `x_tracer.py` entry point, click CLI, text/json/dot formatters, pyproject.toml.

### All tests: 231 passed in 4.3s

---

## Phase 4: Bug Fixes (Mar 17-18)

### Problem: ff_chain_d8 returned `[primary_input]` instead of tracing through FFs

Root causes found and fixed:

1. **S2 testcases were RTL, not gate-level** — `ff_chain` and `reset_chain` used
   `always` blocks. Wrote `tests/fix_sequential_cases.py` to regenerate them with
   explicit `dff_r` cell instances.

2. **pywellen deduplicated VCD signal aliases** — VCD has multiple `$var` entries
   sharing the same identifier code (e.g., `tb.dut.rst_n` and `tb.dut.ff0.RST_N`
   both use code `$`). pywellen returned only one name per code. Fixed by parsing
   the VCD header ourselves and creating alias entries.

3. **Netlist-VCD path mismatch** — Netlist had wire paths (`tb.dut.q7`), VCD had
   cell-internal paths (`tb.dut.ff7.Q`). Fixed by adding port-path aliases in the
   graph: `inst.port` maps to the same driver as the connecting wire.

4. **Missing signal → false X** — `_vcd_get_bit()` returned `'x'` for signals not
   in the VCD, causing the tracer to think async reset was X. Fixed by passing
   `alt_signal` (port-path version) to VCD lookups.

5. **No error for hierarchy mismatch** — Running without `tb.v` gave silent wrong
   answer. Added check: if signal is in VCD but not in netlist, raise helpful error
   suggesting `-n tb.v`.

### Agent D's tests cherry-picked passing cases

The tracer tests only covered `bus_encoder` and `reconverge` from structural cases —
skipping all sequential cases (`ff_chain`, `reset_chain`). The agent avoided the
cases that would have exposed the RTL-vs-gate-level problem.

---

## Phase 5: Documentation & Checkin (Mar 19-21)

### README.md

Created with: tool description, features, installation, usage examples (simple gate,
FF chain, reconvergent fanout), architecture diagram, testing instructions, v1 limitations.

Fixed inaccuracies:
- Removed references to commercial tools (Synopsys, Cadence)
- Removed claim of TSMC support (not tested)
- Changed to "tested with Sky130" only

### Git commits

1. `48c6e8a` — Source code, docs, config (29 files, ~5K lines)
2. `71258e0` — Golden testcase suite (2252 files, 392 cases)

---

## File Inventory

### Source code (`/home/ubuntu/x-tracer/`)

```
src/
├── netlist/
│   ├── parser.py      — pyslang-based parser with primitive, cell, assign,
│   │                     and uninstantiated module handling
│   ├── graph.py       — NetlistGraph with port-path aliases
│   └── gate.py        — Gate and Pin dataclasses
├── vcd/
│   ├── database.py    — VCDDatabase with bisect-based O(log n) lookups
│   ├── pywellen_backend.py — Rust-backed parser with alias handling
│   └── pyvcd_backend.py    — Pure Python fallback
├── gates/
│   ├── primitives.py  — IEEE 1364 truth tables for all Verilog primitives
│   ├── cells.py       — Standard cell recognition, AOI/OAI decomposition
│   └── model.py       — GateModel with forward() and backward_causes()
├── tracer/
│   └── core.py        — trace_x(), XCause, sequential priority handling
└── cli/
    ├── main.py        — click CLI
    └── formatters.py  — text, json, dot output
```

### Key documents

- `docs/SEMANTIC_SPEC.md` — Authoritative spec: cause types, algorithm, scope
- `docs/TESTCASE_GENERATION.md` — Testcase generation methodology
- `README.md` — User-facing documentation

### Orchestrators (`/home/ubuntu/x-tracer-agents/`)

- `gen_synthetic.py` — Launches S1/S2/S3 testcase generation agents
- `gen_modules.py` — Launches A/B/C module implementation agents
- `discuss.py` — Adversarial review: Claude defends, Codex attacks

---

## Permissions Setup

Set `bypassPermissions` in `.claude/settings.local.json` to avoid repeated
permission prompts during the session.

## Lessons Learned

1. **Agents cherry-pick easy tests** — Agent D avoided testing sequential cases
   that would have failed. Bulk tests should be mandatory across all categories.
2. **RTL ≠ gate-level** — S2 agent generated behavioral Verilog (always blocks)
   instead of structural. The spec should have been more explicit.
3. **VCD signal deduplication** — pywellen loses aliases. Real netlists have many
   shared identifier codes. The pyvcd backend handles this correctly.
4. **Hierarchy matters** — VCD paths include testbench hierarchy, netlist paths don't
   (unless tb.v is parsed). This is a fundamental usability issue that needs
   clear error messages.
5. **Single-injection rule** — Must be enforced in both the generator prompts AND
   validation. 272 cases had to be pruned post-generation.
