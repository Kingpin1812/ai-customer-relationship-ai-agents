# 0002: Rules planner by default

**Status:** Accepted, 2026-10-31

## Context

The spec starts development with Ollama and a Qwen model. The development machine has an i3-1215U, 7.6 GB of RAM and no usable GPU. Measured on 2026-10-30 and 2026-10-31:

| Model | Result |
|---|---|
| `qwen3:latest` | No answer within 240 seconds. "Say hi" took about 90 seconds. |
| `llama3.2:latest` | 16 to 36 seconds for a plan. |

`llama3.2` first looked unusable because every plan had empty `actions`. The cause was ours. Fields with defaults are optional in JSON Schema, so the model left `actions` out. The schema sent to the model now marks every field as required, and a plan without `actions` is refused. The same two requests then gave all four correct actions, and the injected `attacker@evil.test` did not appear in either plan.

The model also added pointless questions such as "What is the total tax amount?", which would have stopped complete workflows. Model questions are now discarded. Our own checks decide what is missing.

With those fixes, the demo request ran end to end through the real API on `llama3.2`: 22 seconds to the approval pause, then exactly one email after approval.

## Decision

`PLANNER_MODE` defaults to `rules`. The model is opt-in with `PLANNER_MODE=auto`, and `llama3.2:latest` is the recommended model on this class of machine. `OLLAMA_MODEL` still defaults to `qwen3:latest`, as the spec asks for, on the assumption that a machine able to run it is the one opting in.

In `auto` mode, a plan with no actions falls back to the rules planner.

## Consequences

- The demo works immediately, needs no model, and gives the same result every time.
- Rules understand common phrasing only. A model handles looser wording but has only been checked by hand on these two requests, so its quality on other wording is unknown.
- Safety does not depend on this choice. Either planner only describes what was asked, and recipients, totals and approvals are decided elsewhere.
