# Ansible_EDA_Test — ServiceNow to Event-Driven Ansible

**This repository is a complete, working reference for triggering Ansible Automation Platform
automation from ServiceNow records — incidents, catalog tasks and problems — using Event-Driven
Ansible.**

It is written for someone who has never set up either platform. Every step says what to click, what
to type, and how to prove it worked.

> **This page is a map, not a manual.** It contains no build steps. It tells you which document to
> open, in what order, and what should be true before you move on. Start at
> [§2 Build order](#2-build-order).

> **Verified on** AAP 2.7 (Operator install on OpenShift) plus a ServiceNow Personal Developer
> Instance, September–October 2026. Where AAP 2.6 differs, the guides call it out.

> **New to the vocabulary?** Every term and acronym used anywhere in these guides is defined in the
> [Glossary](docs/glossary.md) — AAP, EDA, PDI, SCTASK, data pill, dot-walk, work note, `extra_vars`
> and the rest.

---

## 1. What this does

A ServiceNow record is created. A flow decides whether it belongs to this automation and which
team's endpoint to send it to. An action posts it to that endpoint. On the Ansible side, a rulebook
decides what to run, and a playbook does the work and writes back to the record.

```
ServiceNow                                          Ansible Automation Platform
──────────────────────────────────────────          ───────────────────────────────────
record created
    │
    ├─ Flow:  enrolled?  which team's stream?
    │
    └─ Action: build payload ──► POST ──────────►   Event stream  (one per team)
                                                         │
                                                    Rulebook: does a rule match?
                                                         │
                                                    Job template ──► Playbook
                                                         │
    record updated with a work note  ◄───────────────────┘
```

### The division of ownership

This single idea explains most of the design, and every guide is consistent with it:

> **ServiceNow owns *membership* — is this record in scope — and the *delivery address* — which
> team's stream. The rulebook owns *what runs, and under what conditions*.**

So priority, thresholds and anything else conditional live in a rulebook, never in ServiceNow
routing. The reasoning, and the options rejected along the way, are in
[Design decisions](docs/design-decisions.md).

### Three record types, one pipeline

| | Incident | SCTASK | Problem |
|---|---|---|---|
| Enrollment gate | No | **Yes** | No |
| Route lookup | Yes | Yes | Yes |
| Shared action and flow | One per record type | | |
| Route table row | **Shared** — one row per team serves every record type | | |

**Build incidents first.** It is the simplest of the three, and every worked example in the guides
is an incident. Adding the others afterwards is [08 §3](docs/08-routine-ops.md).

---

## 2. Build order

Work through these in order. Each one ends with a checkpoint you can verify before moving on.

| # | Document | What you get | Skip it if… |
|---|---|---|---|
| **01** | [Provision AAP](docs/01-provision-aap.md) | An AAP instance you can reach, sized so EDA works | Red Hat hosts your AAP — then skip its §3 and §4 |
| **02** | [Provision the ServiceNow PDI](docs/02-provision-pdi.md) | A ServiceNow instance with the four plugins enabled | You already have one |
| **03** | [AAP / EDA setup](docs/03-aap-eda-setup.md) | Per team: a job template, an event stream, a running activation | — |
| **04** | [The ServiceNow app](docs/04-servicenow-app.md) | The scoped application, three tables, one credential set per team | — |
| **05** | [The Action](docs/05-servicenow-action.md) | The three-step action that builds and posts the payload | — |
| **06** | [The Flow](docs/06-servicenow-flow.md) | The flow that decides whether and where to send | — |
| **07** | [Testing end to end](docs/07-end-to-end-test.md) | Proof, one layer at a time | — |
| **08** | [Routine operations](docs/08-routine-ops.md) | Adding items, teams and record types; rotating tokens | — |

**Then, as needed:**

| | Document | When |
|---|---|---|
| **09** | [Reconnect after an AAP rebuild](docs/09-reconnect-after-aap-rebuild.md) | Your AAP was rebuilt and ServiceNow survived. **Two values per team change** |
| **10** | [Troubleshooting](docs/10-troubleshooting.md) | Something does not work. Symptom index at its §1 |

> 🔴 **The two easiest mistakes, both of which fail silently:**
>
> 1. **Forgetting *Prompt on launch*** on the job template ([03 §2.5](docs/03-aap-eda-setup.md)). The
>    job runs with no variables and nothing tells you why.
> 2. **Writing the payload in the wrong shape** ([05 §7.1](docs/05-servicenow-action.md)). ServiceNow
>    reports `200`, the event arrives, and the rule simply never matches.

### Known gaps in the live build — the docs are ahead of the instance

All three flows reviewed in Workflow Studio on 2026-10-07. **All three are now fail-closed** — an
unrouted record cannot reach the action. None of this was ever a security issue: an empty connection
alias means the request never leaves ServiceNow ([10 §3.4](docs/10-troubleshooting.md)). What remains
costs diagnosability.

| Flow | Route gate | Remaining gaps |
|---|---|---|
| `…on SCTASK` | ✅ `sys_id is not empty`, nested inside the `Count > 0` branch — **the reference implementation** | Updated 2026-10-07; this row is pending a re-check of what changed |
| `…on Incident-EDA` | ✅ Added 2026-10-07 as `is empty → End Flow`, **condition verified to be on `Sys ID`** | Exit is silent |
| `…on Problem` | ✅ `sys_id is empty → End Flow` | Exit is silent |

**The silent exit is the one thing left.** `End Flow` with nothing before it is fail-closed but
leaves "enrolled but unroutable" indistinguishable from "not enrolled", which
[06 §0](docs/06-servicenow-flow.md) warns against. The fix is the same in all three: add an Update
Record work note **inside** the `is empty` branch, before the `End Flow` —
[06 §3.4](docs/06-servicenow-flow.md#34-retrofitting-the-gate-into-a-flow-you-have-already-built).

> ℹ️ **The Send Email half is deliberately deferred** (decided 2026-10-07), so it is a recorded
> choice rather than an outstanding defect. [06 §3.3](docs/06-servicenow-flow.md) and
> [06 §6](docs/06-servicenow-flow.md) still prescribe it, because on a shared instance somebody has
> to be told. On a single-owner lab the **work note carries most of the value** — it puts the real
> reason on the record you are already looking at — and it is the cheaper half to add.

---

## 3. Reference documents

These are not stages. Read them when the question comes up.

| Document | Covers |
|---|---|
| [Glossary](docs/glossary.md) | Every term and acronym, in one place |
| [Rulebook anatomy](docs/rulebook-anatomy.md) | What a rulebook is, a real one annotated line by line, and the five values you change per team. **Read before [08 §2.2](docs/08-routine-ops.md)** |
| [Design decisions](docs/design-decisions.md) | Why one stream per team, the **per-team vs shared token choice** and its object-count and rotation trade-offs, the rejected Decision Table, and the open questions |
| [Adding a record type](docs/adding-record-types.md) | The long-form guide for adding SCTASK and Problem to existing teams |
| [Git workflow](docs/git-workflow.md) | **Read before your second pull request.** The squash-merge trap and the habit that prevents it |
| [Action scripts](docs/scripts/) | Canonical copies of all six ServiceNow step scripts, with their step sys_ids and declared variable names |
| [AAP platform troubleshooting](docs/aap-platform-troubleshooting.md) | **Self-hosted AAP only.** The cluster-level failures underneath AAP — a project sync that never completes, and every pod disappearing when the namespace's ReplicaSet quota fills. Symptom index at its §1 |
| [Screenshots](docs/images/README.md) | Image inventory, numbering scheme and the redaction rules |
| [OAuth direct launch](docs/appendix-oauth-direct-launch.md) | **Reference only.** The non-EDA alternative, kept because it is the same groundwork the Ansible Spoke needs |

> 🔴 **Paste scripts from [`docs/scripts/`](docs/scripts/), never from a rendered page.** Copying
> JavaScript out of rendered Markdown converts straight quotes to curly ones, which leaves an
> unterminated string and reports as `')' expected` — a paste bug that reads like a logic bug.

---

## 4. Tooling

Two Python tools in [`scripts/`](scripts/), standard library only. Both take `--gateway` or read
`AAP_GATEWAY`.

| Tool | What it does |
|---|---|
| [`verify_team.py`](scripts/verify_team.py) | **Read-only.** Checks the repo, AAP and ServiceNow for one team — including the route row's `event_stream_uuid` against the real AAP stream UUID, and the activation's pinned `rulebook_hash` against the rulebook at the project's synced revision. Record-type aware: a type the team's rulebook does not mention reports `SKIP`, not `FAIL`. Exits non-zero on failure; `--json` for CI |
| [`provision_team.py`](scripts/provision_team.py) | Builds a new team's AAP objects and renders its rulebook. **Dry run by default** — `--apply` is required to write. Idempotent, records a manifest, and `--destroy` removes exactly what it made |

> ℹ️ **Build your first team by hand** ([08 §2](docs/08-routine-ops.md)). The script removes four
> silent failure modes *by construction*, which is exactly why a successful scripted run teaches you
> nothing about them — and those four are what you will be debugging later.

> ✅ **Fixed 2026-10-07 — the routing-key gap is closed.** `verify_team.py` still *finds* a team's row
> by `team_code`, which is the only stable handle it has, but it now also **re-runs the query the flow
> actually uses** — `assignment_group` plus `active=true` — and asserts two things: that **exactly one**
> active row is keyed on that group, and that it is **the same row** the rest of the checks examined.
> So a row that looks healthy while the flow routes elsewhere now FAILs. Verified with a four-scenario
> negative control; Team A scores 46, Team C 40 plus one skip.

---

## 5. Repo contents

```
.
├── rulebooks/                       # ONE PER TEAM, one rule per record type
│   ├── team_a_rulebook.yml          #   incident + sctask + problem
│   ├── team_b_rulebook.yml          #   incident + sctask + problem
│   ├── team_c_rulebook.yml          #   incident + problem (no SCTASK — deliberate)
│   ├── my_eda_rulebook.yml          # 🔴 single-rulebook REFERENCE shape. Inert; attach to NOTHING
│   └── catchall_debug_rulebook.yml  # 🔴 matches EVERY event. Attach to NOTHING
├── collections/
│   └── requirements.yml             # servicenow.itsm — installed at project sync
├── servicenow_incident_handler.yml  # one playbook per RECORD TYPE, shared by every team.
├── servicenow_sctask_handler.yml    #   The per-team file is the rulebook, not the playbook.
├── servicenow_problem_handler.yml   #   Problem writes findings only — it cannot change state
├── my_action_playbook.yml           # minimal debug playbook for smoke tests
├── local-test/                      # run a rulebook on your laptop, no AAP needed (07 §1)
│   ├── rulebook_logic_only.yml
│   └── inventory.yml
├── scripts/
│   ├── verify_team.py
│   └── provision_team.py
├── docs/
│   ├── 01-provision-aap.md  …  10-troubleshooting.md     # the build sequence
│   ├── glossary.md                              # every term
│   ├── rulebook-anatomy.md                      # a rulebook, annotated
│   ├── design-decisions.md                      # why it is shaped this way
│   ├── adding-record-types.md                   # SCTASK and Problem, long form
│   ├── git-workflow.md
│   ├── aap-platform-troubleshooting.md          # cluster failures under AAP, self-hosted only
│   ├── appendix-oauth-direct-launch.md          # reference only, non-EDA
│   ├── scripts/                                 # canonical ServiceNow step scripts
│   └── images/
└── README.md                        # this map
```

> 🔴 **Two rulebooks must stay unattached, both kept on purpose.**
> `catchall_debug_rulebook.yml` matches **everything** by design, so attaching it to an activation
> that shares a stream double-launches every job — a symptom that looks like a completely different
> fault. It is kept because [Experiment 4](docs/design-decisions.md) needs it.
> `my_eda_rulebook.yml` is the **single-rulebook reference shape**, for anyone who would rather run
> one rulebook than one per team; it is inert as shipped and its header lists what to change. Details:
> [Rulebook anatomy §5](docs/rulebook-anatomy.md#5--two-rulebooks-in-this-repo-must-not-be-attached--leave-them-alone).

> ⚠️ **Rulebooks must live in `rulebooks/` or `extensions/eda/rulebooks/` at the repository root.**
> The search is **not** recursive — a rulebook anywhere else is invisible to AAP.

### Superseded documents

Still present, pending removal. They contain accurate material but also known errors, and the
numbered guides supersede them:

**Removed 2026-10-07.** Both superseded documents have been deleted now that their unique content is
migrated; they remain in git history.

| File | Replaced by | What was carried across before deleting |
|---|---|---|
| `docs/servicenow-dynamic-team-routing.md` (1,705 lines) | `04`, `06`, `08 §2`, `design-decisions.md`, `docs/scripts/` | The `For Each` Array-pill grey-out diagnostic → [06 §3.1](docs/06-servicenow-flow.md); the extra-match-column option and its `Order by` wildcard trap, the rulebook-dispatch example, and the decision-table API findings → [design decisions §3.4–§3.5](docs/design-decisions.md) |
| `docs/phase2b-two-org-runbook.md` | `03`, `design-decisions.md` | Nothing unique — it referenced a "Team D" that does not exist and an activation log string since renamed |

> ℹ️ **`aap-eda-project-sync-fix.md` was on this list and is no longer.** It is now
> [`docs/aap-platform-troubleshooting.md`](docs/aap-platform-troubleshooting.md) — renamed because it
> covers two unrelated cluster failures rather than one, restructured with a symptom index, and with
> its four known defects fixed. It is a live reference again, listed in [§3](#3-reference-documents).

---

## 6. Open questions

Recorded as unknown rather than guessed at. Full list and how to settle each:
[Design decisions §4](docs/design-decisions.md).

| Question | Blocked on |
|---|---|
| ~~Does a bad event-stream token return `401` or `403`?~~ | **SETTLED 2026-10-07 — it is `403`.** An unknown UUID returns `400`, not `404` — [07 §2.1](docs/07-end-to-end-test.md) |
| ~~Is `spec.api` the correct Custom Resource path in the memory patch?~~ | **SETTLED 2026-10-07 — yes, on AAP 2.7.** It patches the gateway Deployment's `api` container — [01 §4](docs/01-provision-aap.md) |
| Does `revisionHistoryLimit: 1` survive an operator reconcile? | **Partly answered 2026-10-07:** it survived a full sandbox idle-and-restore cycle with all 12 Deployments still at `1`. Not yet tested across an AAP *upgrade* — [AAP platform troubleshooting §4.6](docs/aap-platform-troubleshooting.md#46-why-this-one-can-come-back) |
| Is event-stream delivery really fan-out, or only inferred? | Experiment 4 — [design decisions §1.3](docs/design-decisions.md) |
| Is `Authorization` always redacted from forwarded headers? | Two sources disagree. **The prohibition stands either way** |
