# Rulebook anatomy

**This document explains what a rulebook is, walks through a real one line by line, and names the
five values you change when adding a team.**

> **This is a reference, not a build stage.** Nothing here is a step to perform. Read it **before**
> [08 §2.2](08-routine-ops.md), which asks you to edit five values in a rulebook, and whenever a rule
> is not firing.
>
> **Related:** [03 §0](03-aap-eda-setup.md) introduces the vocabulary ·
> [05 §7](05-servicenow-action.md) defines the payload the conditions read

> **Any unfamiliar word?** Every term and acronym used in these guides is defined in the
> [Glossary](glossary.md) — including AAP, EDA, PDI, SCTASK, data pill, dot-walk, work note
> and `extra_vars`.

---

## 0. Words you'll need

| Term | What it means |
|---|---|
| **Playbook** | An Ansible file that *does* work — installs, restarts, writes to ServiceNow. One shared playbook serves every team |
| **Rulebook** | An Ansible file that *decides whether* work should happen. **It is not a playbook** and its keywords are different |
| **Ruleset** | One top-level block in a rulebook. The `- name:` at the outermost level names it |
| **Rule** | One condition-plus-action pair inside a ruleset. A ruleset can hold many |
| **Source** | Where events come from. In this project it is replaced at run time — see §4 |
| **Condition** | A boolean expression over the incoming event. If it is true, the action runs |
| **Action** | What to do when a condition matches. Here, always "launch this job template" |
| **Jinja** | The `{{ ... }}` templating syntax Ansible uses to read values out of data |
| **`event.payload`** | The JSON body ServiceNow sent, verbatim |
| **`event.meta`** | Metadata **AAP itself adds**, which the sender cannot set or forge |

> 🔴 **Rulebook is not playbook, and confusing them has a specific cost.** A rulebook uses `sources:`
> and `rules:`, which are not valid playbook keywords. Selecting a rulebook where a *playbook* is
> expected — easy to do, because [03 §2.5](03-aap-eda-setup.md)'s dropdown offers both — fails only
> when an event arrives, with:
>
> ```
> ERROR! 'sources' is not a valid attribute for a Play
> ```

---

## 1. The four levels

A rulebook nests four deep, and every pill path and error message refers to one of these levels:

```
rulebook file                 rulebooks/team_a_rulebook.yml
  └── ruleset                 "Team A - ServiceNow event automation"
        ├── sources           where events arrive (replaced at run time)
        └── rules
              ├── rule        "Launch Team A incident handler"
              │     ├── condition      when to fire
              │     └── action         run_job_template
              ├── rule        "Launch Team A SCTASK handler"
              └── rule        "Launch Team A Problem handler"
```

One ruleset, three rules — one per record type. Team C has only two, because it deliberately has no
SCTASK handler.

---

## 2. A real rulebook, annotated

This is `rulebooks/team_a_rulebook.yml`, trimmed to one rule. Open the real file alongside it.

### 2.1 The ruleset header

```yaml
- name: Team A - ServiceNow event automation
  hosts: all
  sources:
    - ansible.eda.webhook:
        host: 0.0.0.0
        port: 5000
```

| Line | What it does |
|---|---|
| `name:` | The **ruleset** name. Reported as `ansible_eda.ruleset` on every job this rulebook launches |
| `hosts: all` | Required by the file format and otherwise unused — a rulebook does not connect to hosts |
| `sources:` | Where events come from. **In this project it is a placeholder** — see §4 |

> ⚠️ **Do not name the ruleset after one record type.** This one handles three. A stale name like
> "ServiceNow incident automation" is not a functional bug — nothing matches on it — but it is the
> first thing you read when diagnosing, and it will mislead you.

> 🔴 **This `name:` is NOT the job template name.** They are different fields at different levels.
> See §3.

### 2.2 The condition

```yaml
  rules:
    - name: Launch Team A incident handler
      condition: >-
        event.meta.eda_event_stream_name == "sn-team-a" and
        event.payload.event_type == "servicenow.incident.created"
```

Both halves must be true. That is **fail-closed** — it launches only on a positive match, never
"unless".

| Half | Why it is there |
|---|---|
| `event.meta.eda_event_stream_name` | **The primary tenant check.** AAP injects this, not the sender, so **it cannot be forged.** It identifies which stream delivered the event |
| `event.payload.event_type` | Which *kind* of event this is, so a future event family on the same stream does not fire this rule |

> ℹ️ **`>-` is YAML for "fold these lines into one string and drop the trailing newline."** It lets a
> long condition span lines readably. The condition is one expression, not two.

### 2.3 The action

```yaml
      action:
        run_job_template:
          name: "Team A Incident Handler"
          organization: "Team A"
          job_args:
            extra_vars:
              incident_number: "{{ event.payload.incident_number | default('') }}"
              short_description: "{{ event.payload.short_description | default('') }}"
              sys_id: "{{ event.payload.sys_id | default('') }}"
              event_version: "{{ event.payload.event_version | default('') }}"
              source: "{{ event.payload.source | default('') }}"
              target_team: "{{ event.payload.target_team | default('') }}"
              source_stream: "{{ event.meta.eda_event_stream_name | default('') }}"
              sn_close_incident: true
```

**How to read an `extra_vars` line** — this is the single most useful thing on this page:

```
              incident_number: "{{ event.payload.incident_number | default('') }}"
              ^^^^^^^^^^^^^^^      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
              the variable your    where the rulebook reads it
              playbook will see    from, in the incoming event
```

The two sides are independent. They happen to share a name here, which is conventional and not
required.

> 🔴 **`| default('')` goes on EVERY mapping.** One missing key without it fails the whole action
> with:
>
> ```
> Object of type StrictUndefined is not JSON serializable
> ```
>
> and **launches nothing at all.** The rule matched, and then the launch request could not be built.
> Partial payloads are normal — the default makes them survivable.

| Field | Note |
|---|---|
| `name:` | **Matched against the AAP job template by exact string.** Get it wrong and nothing fires |
| `organization:` | Must be that team's organization |
| `source_stream` | Reads from `event.meta`, not `event.payload` — it records which stream delivered this |
| `sn_close_incident: true` | A literal, not read from the event. The playbook defaults it to **false**; the rulebook opts in |

### 2.4 How the three record types differ

| | Incident | SCTASK | Problem |
|---|---|---|---|
| `event_type` matched | `servicenow.incident.created` | `servicenow.sctask.created` | `servicenow.problem.created` |
| Record number variable | `incident_number` | **`task_number`** | `problem_number` |
| Completion flag | `sn_close_incident` | **`sn_close_task`** | **`sn_resolve_problem`** |

> ⚠️ **Problem uses `sn_resolve_problem`, not `sn_close_problem`, and the difference is deliberate.**
> The playbook moves a problem to **Resolved** and leaves the formal close to problem management.
> `problem.state` is read-only to the API anyway, so automation writes findings and a human closes.

All three flags default to **false** in the playbook, so a manual launch cannot move a real record.

---

## 3. The five values you change per team

This is what [08 §2.2](08-routine-ops.md) asks for. They sit on four lines, which is exactly how one
gets missed.

| # | Value | Where it is | Matched at run time? |
|---|---|---|---|
| 1 | Ruleset `name:` | Top level, §2.1 | No — but it labels every job |
| 2 | Rule `name:` | Inside `rules:`, §2.2 | No — but see the warning below |
| 3 | Condition's stream name | Inside `condition:`, §2.2 | **Yes, exact string** |
| 4 | `run_job_template.name` | Inside `action:`, §2.3 | **Yes, exact string** |
| 5 | `run_job_template.organization` | Next to it, §2.3 | Yes |

> 🔴 **Only 3, 4 and 5 break the build if wrong. Number 2 breaks your ability to diagnose it.** A
> rulebook still carrying another team's *rule* name is valid YAML and fires correctly — but
> `Last rule fired` on the activation, and the rule name inside the job's event payload, then both
> name the wrong team. A passing test becomes unreadable rather than failing. This was missed on the
> real Team C build.

Catch it with the check from [08 §2.2](08-routine-ops.md): a `grep` for the copied team's name must
return nothing.

---

## 4. The source is a placeholder — this surprises everyone

```yaml
  sources:
    - ansible.eda.webhook:
        host: 0.0.0.0
        port: 5000
```

**That webhook listener is never started and port 5000 is never bound.**

At run time, the activation's **event-stream source mapping** ([03 §2.12](03-aap-eda-setup.md),
page 2) replaces it with `eda.builtin.pg_listener`, which reads from the event stream instead. You
can see the substitution in the activation log:

```
ansible_rulebook.engine - INFO - load source eda.builtin.pg_listener
```

> 🔴 **If that log line says `ansible.eda.webhook` instead, the page-2 mapping did not save** — and
> the activation is listening on a port nothing posts to. Your conditions and rules are fine; the
> wiring is not.

> ⚠️ **Every edit re-pins the mapping to a new Git SHA**, which is why changing a rulebook needs all
> four steps — push, sync, **re-attach**, restart ([03 §3](03-aap-eda-setup.md)). Skip the re-attach
> and the activation keeps running the old commit and fails with
> `Rulebook has changed since the sources were mapped.`

---

## 5. 🔴 Two rulebooks in this repo are dangerous — leave them alone

Your EDA project discovers **every** rulebook in the repository and offers all five when you create
an activation ([03 §2.12](03-aap-eda-setup.md)). Nothing filters the list, and two of the five must
**never** be attached to an activation.

| File | Status | Why |
|---|---|---|
| `team_a_rulebook.yml` | ✅ live | Team A, three record types |
| `team_b_rulebook.yml` | ✅ live | Team B, three record types |
| `team_c_rulebook.yml` | ✅ live | Team C, incident and problem only |
| `catchall_debug_rulebook.yml` | 🔴 **never attach** | **Matches every event on purpose.** Attach it to an activation sharing a stream and it double-launches every job |
| `my_eda_rulebook.yml` | 🔴 **never attach** | A teaching example only. It matches the retired flat `event_type` value `incident_created`, so it **cannot fire** against any current payload, and it names a job template and organization that do not exist |

> ⚠️ **`catchall_debug` is the dangerous one, because it works.** It will fire, launch jobs, and move
> stream counters. The symptom — several rules firing for one event — looks identical to
> [10 §4.4](10-troubleshooting.md)'s "both activations mapped to the same stream", so you would
> diagnose the wrong cause. **Check what is attached before you believe that diagnosis.**

---

## 6. Test a rulebook without AAP

A condition change takes seconds to check locally and minutes to check in AAP.
[`local-test/rulebook_logic_only.yml`](../local-test/rulebook_logic_only.yml) is a ready-made
example: it swaps the source for `ansible.eda.generic` carrying two fixed events, and swaps
`run_job_template` for `debug`.

Full instructions: [07 §1](07-end-to-end-test.md).

> ℹ️ **You cannot test the real rulebook this way.** `ansible-rulebook` validates that
> `run_job_template` has controller credentials **before emitting any events**, so a credential-free
> run exits without exercising your rules — which looks like a silent pass.

---

## 7. When a rule is not firing

In the order that resolves fastest:

1. **Is the activation `Running`?** Events posted while it is down are dropped silently and
   permanently.
2. **Does the activation log say `pg_listener`?** If it says `ansible.eda.webhook`, see §4.
3. **Does `eventsProcessed` move?** If not, the stream is not mapped to this activation.
4. **Compare `event_type` character for character** against what the payload actually sends
   ([05 §7](05-servicenow-action.md)). This is the most common mismatch.
5. **Compare the stream name** in the condition against the stream's name in AAP.
6. **Compare `run_job_template.name`** against the job template's name in AAP.
7. **Did you re-attach and restart** after the last edit? If not, you are testing the old commit.

Fuller catalogue: [10 §4](10-troubleshooting.md).

---

## Self-check

**Did I skip any prerequisite steps?** This document performs no steps, so there are none to skip.
It exists because [08 §2.2](08-routine-ops.md) previously asked for five edits to a file structure
the documentation never showed.

**Is every command copy-paste ready with context?** The only commands here are the `grep` in §3,
which links to its full form in `08`, and the local test in §6, which links to `07`. The YAML blocks
are excerpts for reading, and §2 says to open the real file alongside them rather than paste from
here — pasting YAML out of rendered Markdown risks the same quote mangling as JavaScript.

**Would a complete novice understand every single sentence?** The two hardest ideas are front-loaded:
rulebook-is-not-playbook in §0, with the exact error that confusion produces, and the
left-side/right-side reading of an `extra_vars` line in §2.3, which is drawn out as a diagram because
it is the one thing that makes the rest legible. `>-`, `event.meta` versus `event.payload`, and
Jinja are all defined before use.
