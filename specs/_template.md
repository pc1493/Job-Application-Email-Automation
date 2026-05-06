## 4. Spec Template

Every task gets a spec written before any code is generated. The spec is the contract.

```
Task: <Name>

Context
What the agent needs to know about where this fits in the larger project.
2-4 sentences. Reference instruction files explicitly.

Required instruction files
@~/.claude/methodology.md
@~/.claude/<stack>-patterns.md
@<project>/CLAUDE.md
(anything else specifically relevant)

Inputs
File / artifact A: location, format, what it contains
File / artifact B: location, format, what it contains
(only what is actually needed)

Goal
One sentence. What does success look like?

Steps
Specific, ordered actions.
Not "build the model" — "create stg_X.sql materializing as view, selecting fields A, B, C from source S, applying filter F."
Each step should be small enough that you can predict the output before running it.


Output
Exact file(s) to create or modify.
Expected format / schema / signature.

Acceptance criteria
[ ] Specific, testable conditions.
[ ] Edge cases explicitly named.
[ ] Error behavior defined.
[ ] Lint / type-check / tests pass (specify which).
[ ] Verification: run @~/.claude/_verification.md before commit

Out of scope
Explicitly exclude things the agent might "helpfully" add.
Do not modify existing models X, Y, Z.
Do not add logging beyond what is specified.
Do not introduce new dependencies.
```