#!/usr/bin/env python3
"""
Automated adversarial review discussion between Claude and Codex.

Usage:
    python3 discuss.py [--rounds N] [--doc PATH]

Each round:
  - Claude defends / responds to critique
  - Codex attacks / finds flaws adversarially

After all rounds, Claude produces a final synthesis with agreed changes.
"""

import argparse
import subprocess
import sys
from pathlib import Path

CLAUDE_DIR = Path("/home/ubuntu/x-tracer-agents/claude-master")
CODEX_DIR  = Path("/home/ubuntu/x-tracer-agents/codex-master")
DISCUSSION_DIR = Path("/home/ubuntu/x-tracer-agents/discussion")


# ── prompts ──────────────────────────────────────────────────────────────────

CLAUDE_ROUND1_PROMPT = """\
You are the author defending the following testcase generation plan.

Present the strongest case for why this approach is sound. Cover:
- Why testcases-first is the right sequencing
- Why explicit X injection eliminates the need for a reference simulator
- Why the clean-environment constraint is enforceable
- Why the validation pipeline is sufficient

Be specific and structured. Reference concrete sections of the document.
Anticipate the sharpest objections and pre-empt them. 400-600 words.

=== DOCUMENT UNDER REVIEW ===
{doc}
"""

CODEX_ROUND_PROMPT = """\
You are an adversarial reviewer. Your job is to find every flaw, gap, and
unsound assumption in this testcase generation plan. Be specific and ruthless.

Rules:
- Cite the specific section or claim you are attacking
- Prefer concrete failure modes over vague concerns
- Identify at least 5 distinct problems per round
- Do not praise anything — only attack
- In rounds 2+, escalate: push harder on unresolved issues and find new angles

=== DOCUMENT UNDER REVIEW ===
{doc}

=== DISCUSSION SO FAR ===
{history}

=== LATEST DEFENSE ===
{latest_claude}

Write your adversarial critique now.
"""

CLAUDE_REPLY_PROMPT = """\
You are the author defending the testcase generation plan. Respond to the
adversarial critique below.

For each critique:
- If it is valid: concede clearly, then propose a specific concrete fix
- If it is wrong: counter-argue with evidence from the document or first principles
- Do not ignore any point

Be direct. Avoid waffling. If the plan needs changes, say exactly what they are.

=== DOCUMENT UNDER REVIEW ===
{doc}

=== DISCUSSION SO FAR ===
{history}

=== LATEST CRITIQUE ===
{latest_codex}

Write your response now.
"""

SYNTHESIS_PROMPT = """\
You are the author of the testcase generation plan. The adversarial review
discussion is now complete. Produce a final synthesis.

Structure your output as:
1. **Points conceded** — list each valid critique and the specific change it
   requires in the document
2. **Points rejected** — list each critique you are not acting on and why
3. **Updated document** — rewrite TESTCASE_GENERATION.md in full, incorporating
   all accepted changes. Preserve all sections; add, modify, or remove content
   only where the discussion identified a genuine problem.

=== ORIGINAL DOCUMENT ===
{doc}

=== FULL DISCUSSION ===
{history}
"""


# ── helpers ──────────────────────────────────────────────────────────────────

def run_claude(prompt: str) -> str:
    result = subprocess.run(
        ["claude", "-p", prompt,
         "--dangerously-skip-permissions",
         "--add-dir", str(DISCUSSION_DIR)],
        capture_output=True, text=True,
        cwd=str(CLAUDE_DIR),
    )
    if result.returncode != 0:
        print(f"[ERROR] claude exited {result.returncode}:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()


def run_codex(prompt: str, output_file: Path) -> str:
    result = subprocess.run(
        ["codex", "exec",
         "-C", str(CODEX_DIR),
         "--skip-git-repo-check",
         "--dangerously-bypass-approvals-and-sandbox",
         "-o", str(output_file),
         prompt],
        capture_output=True, text=True,
        cwd=str(CODEX_DIR),
    )
    if result.returncode != 0:
        print(f"[ERROR] codex exited {result.returncode}:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)
    return output_file.read_text().strip()


def banner(msg: str):
    width = 70
    print("\n" + "=" * width)
    print(f"  {msg}")
    print("=" * width + "\n", flush=True)


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Automated Claude ↔ Codex adversarial review")
    parser.add_argument("--rounds", type=int, default=4, help="Number of back-and-forth rounds")
    parser.add_argument("--doc", type=str,
                        default=str(CLAUDE_DIR / "TESTCASE_GENERATION.md"),
                        help="Document to review")
    args = parser.parse_args()

    doc_path = Path(args.doc)
    if not doc_path.exists():
        print(f"[ERROR] Document not found: {doc_path}", file=sys.stderr)
        sys.exit(1)

    doc = doc_path.read_text()
    DISCUSSION_DIR.mkdir(exist_ok=True)

    # Copy doc into discussion dir for reference
    (DISCUSSION_DIR / doc_path.name).write_text(doc)

    history_parts = []  # accumulates all rounds for context

    for round_num in range(1, args.rounds + 1):
        banner(f"ROUND {round_num} / {args.rounds}")

        # ── Claude's turn ────────────────────────────────────────────────────
        print(f"[Claude] writing round {round_num} defense...", flush=True)

        history = "\n\n---\n\n".join(history_parts) if history_parts else "(none yet)"

        if round_num == 1:
            claude_prompt = CLAUDE_ROUND1_PROMPT.format(doc=doc)
        else:
            latest_codex = (DISCUSSION_DIR / f"round_{round_num - 1}_codex.md").read_text()
            claude_prompt = CLAUDE_REPLY_PROMPT.format(
                doc=doc, history=history, latest_codex=latest_codex
            )

        claude_response = run_claude(claude_prompt)
        claude_file = DISCUSSION_DIR / f"round_{round_num}_claude.md"
        claude_file.write_text(f"# Round {round_num} — Claude\n\n{claude_response}\n")
        print(claude_response)
        history_parts.append(f"## Round {round_num} — Claude\n\n{claude_response}")

        # ── Codex's turn ─────────────────────────────────────────────────────
        print(f"\n[Codex] writing round {round_num} critique...", flush=True)

        history = "\n\n---\n\n".join(history_parts)
        codex_prompt = CODEX_ROUND_PROMPT.format(
            doc=doc, history=history, latest_claude=claude_response
        )

        codex_file = DISCUSSION_DIR / f"round_{round_num}_codex.md"
        codex_response = run_codex(codex_prompt, codex_file)
        # codex writes to the file itself via -o; prepend a header
        codex_file.write_text(f"# Round {round_num} — Codex\n\n{codex_response}\n")
        print(codex_response)
        history_parts.append(f"## Round {round_num} — Codex\n\n{codex_response}")

    # ── Final synthesis ───────────────────────────────────────────────────────
    banner("FINAL SYNTHESIS")
    print("[Claude] producing final synthesis and updated document...", flush=True)

    history = "\n\n---\n\n".join(history_parts)
    synthesis_prompt = SYNTHESIS_PROMPT.format(doc=doc, history=history)
    synthesis = run_claude(synthesis_prompt)

    synthesis_file = DISCUSSION_DIR / "final_synthesis.md"
    synthesis_file.write_text(f"# Final Synthesis\n\n{synthesis}\n")
    print(synthesis)

    banner("DONE")
    print(f"All rounds saved to: {DISCUSSION_DIR}")
    print(f"Final synthesis:     {synthesis_file}")


if __name__ == "__main__":
    main()
