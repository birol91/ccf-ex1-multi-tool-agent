# Exercise 1 — Multi-Tool Support Agent with Escalation Logic

> An **AI agent** that reads a customer's natural-language message, decides on its own
> which tools to call, and **escalates to a human** when it must not act automatically.
>
> A **learning exercise** (CCA-F official Preparation Exercise 1) — not a production system;
> data is mocked. The goal is to write an agent's inner mechanics *by hand* to understand them.
>
> 📐 See [`architecture.html`](architecture.html) for the visual system diagram.

---

## 1. What Is an "Agent"?

In an ordinary program, *you* write the control flow. In an **agent**, the **LLM** decides
the flow by running a loop:

```
User message → LLM thinks → "call this tool with these inputs"
            → code runs the tool → result fed back to LLM
            → LLM thinks again → asks for another tool, or "I'm done"
            → final answer to the user
```

This loop is the **agentic loop** — the heart of the project. A single LLM call is not an
agent; the loop plus the LLM choosing tools **on its own** (model-driven, not hard-coded
`if/else`) is what makes it one.

---

## 2. Three Core Concepts

### `stop_reason` — the only correct stop signal
Every Claude response says **why** it stopped:

| Value | Meaning | Loop action |
|---|---|---|
| `"tool_use"` | "I need a tool — your turn." | **Continue** |
| `"end_turn"` | "I've finished." | **Stop** |
| `"max_tokens"` | Output budget ran out | Handle (edge case) |

The loop is driven **only** by this field — never by parsing the response text for a word
like "done" (a classic anti-pattern).

### `tool_use` — a request, not an execution
When the model wants a tool, its response contains a `tool_use` block carrying `id`,
`name`, and `input`. **Claude does not run the tool** — it only *requests* it. **You**
execute it and return a `tool_result` whose `tool_use_id` must match the original `id`
(mismatch → API 400). The tools are the ones **you define and code**; Claude only picks
from your list.

### `hook` — a deterministic guardrail (the new idea)
Code that runs **before** a tool executes, to enforce a business rule. No `process_refund`
ever runs on the model's word alone. The hook gates **every** refund call (by tool name —
100% deterministic) and applies two layers:

- **amount ≥ 500** → escalate to a human (large refunds need human oversight).
- **amount < 500** → ask the **user** to confirm (`"Confirm refund of X? (yes/no)"`).
  *yes* → run the refund; *no* → cancel, no money moves.

Why a gate at all? Because tool selection is probabilistic — the model could hallucinate and
call `process_refund` even when the user only asked for *info* (e.g. a 300 status query
mis-routed to a refund). A description reduces that risk but cannot eliminate it. The
confirmation gate stops the unwanted refund: the user is asked, says *no*, money is safe.
We enforce this **in code, not in the prompt**, because a prompt can be ignored while code
runs identically every time. This is the exam's key distinction: **critical business rules =
programmatic enforcement, not prompt enforcement.**

---

## 3. What We're Building (Scenario)

A **customer support agent**. The customer can write:

- "What's the status of order ORD-987?" → looks up the order and its line items (products,
  quantities, prices, total), answers. If the model mistakenly tries a refund, the
  **confirmation gate** asks the user first → user says no → safe.
- "Refund 400 on that order." → gate asks the user to confirm → *yes* → refund processed.
- "Refund 900 on that order." → ≥ 500 → **escalates to a human** (no auto-refund).
- "Tell me the status *and* issue the refund." → **decomposes** both into one reply.

The goal is not a support bot, but to combine five agent skills in one system:

| Skill | Step |
|---|---|
| Stopping the loop correctly (`stop_reason`) | 2 |
| Defining similar tools without confusing the model | 1 |
| Structured error handling (retry vs explain) | 3 |
| Enforcing a business rule **in code** | 4 |
| Decomposing multiple requests | 5 |

---

## 4. Architecture

Everything in **one file** (`agent.py`, ~150 lines), in three layers. See
[`architecture.html`](architecture.html) for the diagram.

1. **LLM (brain)** — the Anthropic Claude API. Decides *which* tool to call. Runs in the
   cloud (HTTPS). Stateless — we resend the full conversation every turn.
2. **Loop (orchestration)** — our `run_agent()`. Applies the decision, executes tools,
   feeds results back, drives the loop via `stop_reason`. **We control it, not the LLM.**
3. **Tools + mock data (hands)** — `execute_tool()` + fake data in `database.xlsx` (a mock
   Excel "database" with `customers`, `orders`, and `order_items` sheets, read with
   `openpyxl`; built by `create_database.py`). `lookup_order` joins an order with its line
   items (product, qty, unit price) and derives the total `amount = Σ(qty × unit_price)`.
   Real-world: a database or MCP server.

The hook sits **between** the loop and `execute_tool()`: every tool call passes through it
first, so *every* `process_refund` is gated before any money moves — ≥ 500 escalates to a
human, < 500 asks the user to confirm.

---

## 5. Technology

| | | |
|---|---|---|
| **LLM API** | Claude API (Anthropic), `anthropic` SDK | CCA-F = Claude Certified Architect |
| **Model** | `claude-sonnet-4-6` | Good learning/cost balance |
| **Framework** | **None — plain Python** | See below |
| **Data** | Mock Excel `database.xlsx` (`openpyxl`) | Stands in for a DB/MCP server |
| **Files** | `agent.py` + `create_database.py` (+ `database.xlsx`) | Simple, portfolio-friendly |

**Why no LangGraph / LangChain?** They write the agentic loop *for you* and **hide** its
internals. The whole point here is to write that loop by hand — the CCA-F exam tests those
internals. Especially the **hook** (Step 4): intercepting a tool *before* it runs is only
possible when you control the loop yourself.

---

## 6. Exam Coverage (CCA-F)

Reinforces **three domains at once**:

- **Domain 1 — Agentic Architecture:** driving the loop with `stop_reason`.
- **Domain 2 — Tool Design:** distinguishing `lookup_order` (read) vs `process_refund`
  (move money) so the model never confuses them.
- **Domain 5 — Reliability:** structured errors (transient/validation/permission), retry
  strategy, code-level guardrails.

Plus two new concepts: **programmatic hook** (gate in code) and **multi-concern
decomposition** (split requests, synthesise one answer).

---

## 7. Build Plan (Checklist)

> Pace: step by step, written together (concept → code → why). Output: `agent.py`.
> Specialist agents are used only for review/test/support.

**Prerequisites:** `anthropic` not installed · `ANTHROPIC_API_KEY` not set (live run = paid)
· Python 3.13 available.

**Step 1 — Define 4 tools with clear descriptions** (Domain 2) ✅
- [x] `get_customer`, `lookup_order` (read-only); `process_refund`, `escalate_to_human`
- [x] Boundary sentences separating `lookup_order` (no money) vs `process_refund`
- [x] SUPPORT: prompt-engineer (separation OK) · ai-engineer (docs consistent) · code-reviewer (schema valid)

**Step 2 — Agentic loop via `stop_reason`** (Domain 1) ✅
- [x] `run_agent()` while loop; append assistant turn **before** processing results
- [x] `end_turn` → return text; `tool_use` → run all blocks, results in ONE user message
- [x] Correct `tool_use_id`; `is_error: True` on errors; handle unexpected `stop_reason`
- [x] SUPPORT: ai-engineer (flow consistent) · code-reviewer (9/9 anti-pattern checks pass)

**Step 3 — Structured error responses** (Domain 5) ✅
- [x] Mock Excel `database.xlsx` (customers + orders + order_items) read via `openpyxl`;
      `lookup_order` joins line items and derives the total; `make_error(...)`; `execute_tool` per tool
- [x] DECISION: transient error tested via a deterministic fixture — `ORD-FLAKY` fails once
      (transient, isRetryable=true), then succeeds on retry
- [x] SYSTEM prompt: retry transient, explain validation/permission
- [x] SUPPORT: ai-engineer (docs consistent) · code-reviewer (error structure valid)

**Step 4 — Programmatic hook (confirmation + escalation gate)** ✅
- [x] `tool_hook()` gates **every** `process_refund` (by tool name):
      `≥ 500` → escalate to human · `< 500` → ask user to confirm (`input()`, yes/no)
- [x] Wired into loop before `execute_tool`; verified: 300 status-mis-route → user says no → safe;
      400 → confirm yes → processed; 900 → escalated
- [x] SUPPORT: ai-engineer (consistent, is_error:False correct) · code-reviewer (7/7, gate is deterministic)

**Step 5 — Multi-concern test** (integrated) ✅
- [x] Scenario A: status + 900 refund → get_customer → lookup_order → process_refund
      hits hook (≥ 500) → **escalated** → combined reply (verified live)
- [x] Scenario B: status + 300 refund → lookup_order → process_refund hits hook (< 500) →
      asks user to confirm; "no" cancels, "yes" processes (and ORD-FLAKY exercises the
      transient-retry path) → combined reply (verified live)
- [x] SUPPORT: ai-engineer + code-reviewer (code sound, chain consistent)

**Closeout** — `requirements.txt`; fill §9 with real output; optional live run.

---

## 8. Success Criteria & Anti-Patterns

**Must pass:** 4 tools defined, lookup vs refund distinguished · loop driven by
`stop_reason` · assistant turn appended before results, `tool_use_id` matches · structured
errors with `is_error` · transient retried, validation/permission explained · hook gates
**every** refund — ≥ 500 escalates, < 500 asks the user to confirm · multi-concern
decomposed into one reply.

| Anti-Pattern | The right way |
|---|---|
| Enforce business rule via prompt | Gate in code (hook) |
| Drive loop by inspecting `content` | Use `stop_reason` |
| Generic "an error occurred" | Structured error (errorCategory + isRetryable) |
| Retry every error | Retry only transient + isRetryable |
| Vague tool description | Boundary sentences |
| Results in separate user messages | All `tool_result` in one user message |
| Use a `tool_runner` helper | Write a manual loop (needed for the hook) |

---

## 9. Setup & Sample Output

```bash
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt                      # anthropic, openpyxl, python-dotenv, flask
python create_database.py                             # build the mock database.xlsx (once)
export ANTHROPIC_API_KEY="sk-ant-..."                 # or place it in a project-root .env

python agent.py        # terminal: runs the two multi-concern scenarios
python app.py          # web chat UI at http://localhost:5050
```

### Web chat UI

`app.py` (Flask) serves a simple chat page that drives the same agent. The refund
confirmation happens **in the chat**: when a refund under 500 is requested, the agent
replies "Confirm refund? (yes/no)" and waits for your next message — a two-turn
human-in-the-loop. Larger refunds (≥ 500) escalate automatically. The core agent logic
(`agent.py`) is unchanged; the web layer only adds a `confirm_callback` so the hook can ask
for confirmation over chat instead of the terminal `input()`.

> Port is **5050**, not 5000 — on macOS port 5000 is taken by the AirPlay Receiver.

> **Domain note:** The same confirm/escalate guardrail maps onto a BMS command agent —
> a routine command asks the operator to confirm before applying; an over-threshold
> current/voltage command escalates for human oversight (mirroring the < 500 confirm /
> ≥ 500 escalate split here).

**Sample output (live run, `claude-sonnet-4-6`):**

_Scenario A — status + 900 refund (escalation path):_
```
USER: Hi, I'm CUST-123. Two things: (1) what is the status of order ORD-987?
      (2) I also want a 900 refund on order ORD-654.
stop_reason: tool_use
stop_reason: tool_use
stop_reason: tool_use
stop_reason: end_turn
AGENT: Your case has been escalated! Ticket ESC-001 — a human agent will review your
       $900 refund request for order ORD-654 and reach out shortly.
```

_Scenario B — status + 300 refund, user confirms "yes" (ORD-FLAKY also exercises the
transient-retry path, so the hook prompts twice):_
```
USER: ... tell me the status of ORD-987, and also process a 300 refund on ORD-FLAKY.
stop_reason: tool_use
Confirm refund of 300 for ORD-FLAKY? (yes/no): yes
stop_reason: tool_use
Confirm refund of 300 for ORD-FLAKY? (yes/no): yes
stop_reason: end_turn
AGENT: Order ORD-987 — Delivered (Wireless Mouse ×2 @ $50, Mechanical Keyboard ×1 @ $150,
       total $250). Refund on ORD-FLAKY — $300 processed successfully.
```
All four mechanics fire together: stop_reason loop, multi-concern decomposition, the
confirm/escalate hook, and the transient retry.
