# How We Built an SoC Debugging Tool in 6 Days Using AI Agents

## The spark

When I read about Normal Computing [building a 580K-line Verilog simulator in 43 days using AI](https://normalcomputing.com/blog/building-an-open-source-verilog-simulator-with-ai-580k-lines-in-43-days), it got me thinking. If AI agents could tackle something that ambitious, what about the debugging tools that chip engineers actually reach for every day? That's what set this project in motion.

## The problem

If you've worked on chip design, you know the pain. You run a gate-level simulation of your SoC, and somewhere in the waveform, a signal goes X — unknown. That X propagates through thousands of gates, corrupts downstream logic, and your simulation fails. Now you need to find where it started.

On the Ramanujan chip at Mirafra, the engineering team spent significant time doing exactly this — manually tracing X's backward through the netlist, staring at waveforms, making educated guesses. It's tedious, error-prone, and every chip team does it. No open-source tool existed to automate it.

@Aadi and I thought this was a good candidate to test what agentic AI development can actually do on a non-trivial engineering problem. The tool needed to parse multi-million-gate netlists, query gigabytes of waveform data, implement IEEE-standard logic propagation rules, and handle the countless quirks of real EDA tool output.

## The setup

We used **Claude** (via Claude Code) as the builder and **Codex** as the adversarial reviewer. The entire project took about 6 days of part-time work.

We had been used to using AI tools like Cursor and Claude to do function/feature level coding but here we treated Claude not as a coding assistant you chat with, but as a team of agents you architect, deploy, and supervise. This shift in methodology required new ways of thinking and structuring the project.

## The methodology

### 1. Testcases before code

We wanted the agents to do most of the work without our intervention. That meant that they needed to iterate on the code independently. We decided to build an extensive test-suite.

Getting the specifications of the test-suite right proved to be the most challenging part of the project.

The idea is to let the design stabilise to a non-x state, and then inject a single 'x' on a signal. By Verilog semantics, this can be the only cause of all x's from that point on (There were no multi-driver nets, or timing checks). The tool is expected to find this signal from any starting 'x'. 

Communicating this idea precisely to the agents was difficult. We had Claude come up with an initial description and then engage with Codex in an adversarial review for three rounds. We were hoping that the two would be able to nail down the specification with this but after a lot of big words, even bigger ideas and a lot of tokens, we had to refine and clarify the basic idea.

Once this test plan was ready, we had three agents generate testcases in parallel. One produced 302 gate-level tests (every combination of gate type, input count, and injected value). Another produced 23 structural patterns — flip-flop chains, mux trees, reconvergent fanout, reset distribution trees. A third produced 67 multi-bit scenarios — partial bus injection, bit slicing, shift registers.

Each testcase came with a golden manifest: the expected root cause, the expected trace path, the expected leaf nodes. When the implementation agents later wrote the tracer, every run was an unambiguous pass or fail. 

### 2. Implementation Specification

We had defined the problem, the expected size of the inputs to Claude. Based on this Claude did its research and came up with an implementation specification. This included the main algorithm, the choice of libraries and the interface between various components. We do not remember if we provided much feedback at this point.

### 3. Parallel agents with interface contracts

We explicitly asked Claude to use multiple agents. Claude decomposed the system into five modules and assigned each to a separate agent:

- Netlist parser
- Waveform database
- Gate model (logic propagation rules)
- Tracer core (the main algorithm)
- CLI and output formatting

The first three had no dependencies on each other and ran in parallel. The tracer core started after they completed. The CLI came last.

This mirrors how an experienced engineering lead decomposes work across a team. 

### 4. Real-world validation

After Claude was able to get all the tests to pass, we pointed it to the SoC netlist. This was the most impressive part:

- Claude figured out the verification environment independently.
- It was able to broadly get the design architecture from the netlist
- It modified the Makefile based verification environment and the appropriate files to come up with x injection tests on the SoC.
- It iterated on the solution tens of times as it hit roadblocks. You can read about some of these iterations in docs/development_process.md.

## The lessons and surprises

**The AI agents are more powerful than we imagined**. After the initial problem description and the testplan all the work was done by agents independently. At one point, we were so tired of watching Claude work that we asked it to periodically email us progress reports, and it did.

**Agents take the path of least resistance.** The tracer agent reported "45 tests passing" — but it had silently skipped every difficult test category. It ran the easy structural tests and avoided sequential logic entirely. 

**Testcase generation is as or more important than the code.** One agent generated structurally valid testcases that used the wrong abstraction level — RTL constructs instead of gate-level primitives. The tests compiled and passed, but they weren't testing anything meaningful. We caught it during review, but it's a reminder: you need to validate the *tests*, not just the code.

**Structure matters more than prompting.** We spent very little time crafting clever prompts. We spent a lot of time getting the *problem definition* right — once that was clear, the agents ran with it.

**Don't trust, verify.** Agents will tell you things are working when they've only tested the easy cases. Enforce coverage. Run the full suite yourself. Review the substance of what agents produce, not their summaries.

**Testcase-first is even more important with AI.** When a human writes code, they carry an intuitive understanding of correctness. AI doesn't. It needs explicit, automated ground truth. Generate the testcases first, make them comprehensive, and validate that the tests themselves are correct.

## Final Thoughts

AI will enable a lot more software to be written. Although we faced this problem in a real project, we would not have thought about writing this tool without the help of AI. 

Open Source tools will become more mature and competitive with commercial tools as the effort to add functionality or improve performance has decreased significantly. AI + open source libraries will enable teams to write software which is designed for their use cases.

AI tools are very powerful even as they are today. They will have more impact on the practice and business of software that at least we could foresee before we did this project.