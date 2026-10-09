# Handling the window where events are lost

**This document explains why some events sent to Event-Driven Ansible are silently thrown away, and
proposes what to build so none are lost without anybody noticing.**

> **This is a reference and a proposal, not a build stage.** The measurements in it are real. The
> design in [§4](#4-what-to-build) is **proposed and not built** — it is written so it can be
> argued with before anybody spends time on it.

> **Any unfamiliar word?** Every term is defined in the [Glossary](glossary.md). The three used
> most here are defined again below, because this page makes no sense without them.

---

## 1. The problem, in one paragraph

A **rulebook activation** is the always-running process in Ansible Automation Platform (AAP) that
watches for arriving events and starts automation. An **event stream** is the web address that
ServiceNow posts those events to. When the activation is not running, the event stream still accepts
the post and answers **`HTTP 200`**, and the event is then **discarded**. It is not queued, and it is
not delivered when the activation comes back. ServiceNow is told it succeeded.

Measured on 2026-10-09, three times, with a working control either side of the window:

| Event posted while the activation is… | Sender sees | Reached the rulebook? |
|---|---|---|
| running | `HTTP 200` | Yes |
| **stopped** | **`HTTP 200`** | **No, and never afterwards** |
| running again | `HTTP 200` | Yes |

**Why it happens.** An event stream hands events to an activation over a PostgreSQL
**`LISTEN`/`NOTIFY`** channel — a messaging feature where a sender announces a message and only
processes *currently listening* receive it. There is no queue. A message announced while nothing is
listening is discarded by design. A stopped activation is not a slow consumer; it is an absent one.

> 🔴 **Two things cannot be used to detect this, both measured.** The event stream's
> `events_received` counter rises identically whether the event was processed, discarded, or
> rejected for a bad token — so a healthy-looking counter proves nothing. And the activation's
> status reads `running` before the rule engine has actually begun listening, so status alone is
> not proof either.

> 🔴 **`enable_persistence` does not fix it, despite the name.** Switching it on is refused unless
> you supply a rule engine credential, and that credential type describes itself as
> *"Credential for EDA Rule Engine persistence. This uses the Postgres DB Credential"*. It gives the
> **rule engine** a database for its own state. The loss happens before the rule engine is involved.
> There is nothing for it to preserve. [Measured 2026-10-09.]

---

## 2. The window is not only when you plan it

It is tempting to treat this as a problem of planned changes — you restart an activation to apply a
rulebook edit, so you plan around that one window. The lab says otherwise.

Measured on 2026-10-09, across the three activations in this lab:

- **59 restarts** in total (`restart_count` of 22, 24 and 13).
- Of one activation's last 20 instances, **5 ended in `failed`** — not stopped by a person. The
  recorded reasons were *"Activation is unresponsive. Readiness check for ansible-rulebook timed
  out"*, *"Liveness check … timed out"* and *"Missing container for running activation"*.
- One restart that same day failed because the decision environment image could not be pulled, and
  AAP retried it. That single retry stretched a planned 37-second window to **111 seconds**.

So unplanned windows happen, they are more frequent here than planned ones, and their length is not
predictable.

> ⚠️ **This is the load-bearing conclusion of this page.** A procedure that only covers planned
> changes — "pause the sender, make the change, resume" — leaves every crash, image-pull failure and
> readiness timeout silently losing events. Whatever else is done, **something has to find events
> that were lost without anyone planning a window.**

---

## 3. The three strategies, and which to pick

| Strategy | What it is | Covers unplanned outages? | Cost |
|---|---|---|---|
| **Pause the sender** | Stop ServiceNow posting for the duration, then resume | **No** | Low, but needs a catch-up for records created while paused |
| **Pick a quiet period** | Make changes when little traffic is expected | **No** | None, but reduces the odds rather than the risk |
| **Reconcile afterwards** | Find records that should have been automated and were not, then re-send them | **Yes** | Highest to build; the only one that works when nobody knew there was a window |

**Recommendation: build reconciliation, and use the other two as well when the change is planned.**

The reasoning is the measurement in [§2](#2-the-window-is-not-only-when-you-plan-it). Pausing the
sender is genuinely useful and much cheaper, but it can only cover a window somebody scheduled.
Reconciliation covers both, and it is the only one of the three that would have caught today's
image-pull failure.

> ℹ️ **These are not alternatives.** For a planned rulebook change, pause the sender *and* let
> reconciliation act as the safety net. Pausing keeps the number of records needing reconciliation
> near zero; reconciliation is what makes "near zero" safe to say.

---

## 4. What to build

**Proposed, not built.** Four pieces, in dependency order. The question that used to block all of
them — whether running the handler twice is safe — is now measured, in
[§4.1](#41-is-it-safe-to-run-twice--measured-2026-10-09).

1. **Make the marker explicit, and check it before re-sending.** Reconciliation needs to ask "was
   this record automated?" and get a reliable answer — and [§4.1](#41-is-it-safe-to-run-twice--measured-2026-10-09)
   shows it must also *act* on that answer, because a second run adds a duplicate work note and runs
   the remediation again. Today the only marker is a work note whose text the playbook writes.
   Measured format, from a real run on 2026-10-09:

   ```
   2026-10-09 10:48:35 - System Administrator (Work notes)
   Ansible Automation completed at 2026-10-09 12:48:34 CDT
   ```

   Matching on prose is fragile. Add a dedicated field — a checkbox or a correlation id the playbook
   sets — so the query is exact rather than a text search.

2. **Record every window.** `scripts/eda_apply_rulebook_change.py` already measures and prints the
   window it caused. Have it also write the start and end somewhere durable. Unplanned windows need
   the same treatment from the other direction: an activation whose status leaves `running` is the
   start, and its return is the end, which AAP's own activation-instance records already carry
   (`started_at` and `ended_at` per instance).

3. **A scheduled reconciliation job.** On a schedule, find records that match the trigger criteria,
   were created or updated in the lookback period, and carry no automation marker from step 1. For
   each, re-post the event to that team's event stream. Where it runs is a real choice:
   - **In ServiceNow**, as a scheduled job — it already has the records and the credentials to post.
   - **In AAP**, as a scheduled job template — keeps the logic beside the rest of the automation.

   A scheduled job in ServiceNow is the smaller build, because the query and the outbound post both
   already exist there.

4. **Keep re-processing safe.** Reconciliation re-sends events, so the handler may run twice for one
   record. [§4.1](#41-is-it-safe-to-run-twice--measured-2026-10-09) measures what that does today: the
   ServiceNow write-back survives it, the remediation is the part to watch.

### 4.1 Is it safe to run twice? — measured 2026-10-09

This was the open question blocking the rest of the design. It was tested by creating an incident,
sending its event, letting the handler close it, and then **sending the identical event again**.

| | After run 1 | After run 2 |
|---|---|---|
| Job result | `successful` | **`successful`** — no failure |
| `state` | `Closed` | **`Closed`** — unchanged |
| `close_code` | `Solution provided` | **unchanged** |
| `reopen_count` | `0` | **`0`** — it does **not** reopen |
| `sys_mod_count` | 2 | 3 |
| Automation work notes | 1 | **2 — a duplicate** |

**The good half: nothing breaks.** A second run does not fail, does not reopen the incident, and
does not corrupt its state or close code. So reconciliation cannot damage records that were already
handled, which is what the design needed to know before being built.

**The other half: it is additive, not idempotent.** Each run appends another work note:

```
2026-10-09 11:43:38 - System Administrator (Work notes)
Ansible Automation completed at 2026-10-09 13:43:37 CDT

2026-10-09 11:43:10 - System Administrator (Work notes)
Ansible Automation completed at 2026-10-09 13:43:09 CDT
```

That is why step 1 above is a **gate** and not merely a query: reconciliation has to skip records
that already carry the marker, or a job running on a schedule will keep adding notes to records it
already handled.

> 🔴 **This tested the ServiceNow write-back, not a real remediation.** This lab's remediation tasks
> are debug messages — in the second run, *Execute disk cleanup remediation* was skipped and
> *Execute generic remediation* only printed a message. So the measurement says re-sending an event
> is safe **for this handler as written**. A handler whose remediation actually changes a machine
> must be checked for repeat-safety on its own terms before reconciliation is pointed at it. The
> handler has no guard against re-processing of any kind, so that safety has to come from the gate in
> step 1.

---

## 5. What this does not solve

- **It does not shorten the window.** Scripting the change already cut it from minutes of clicking
  to 37–43 seconds; reconciliation is about the events inside it, not its length.
- **It does not make the loss visible at the time.** The sender still receives `HTTP 200`. The gap
  is found later, by looking, which is why the schedule in step 3 is part of the design rather than
  an afterthought.
- **It does nothing for events a rule never matched.** A record whose event arrives and matches no
  rule is not lost — it was received and deliberately ignored. That is a different problem with a
  different fix.

---

## 6. How this interacts with the topology decision

Under a single shared activation, one window costs **every** team's events at once. Under one
activation per team, the identical window costs **one** team. That difference is why the decision
brief treats this dimension as the strongest argument for a path per team.

Reconciliation is needed either way. What changes is how much it has to clean up each time.

---

## Self-check

**Did I skip any prerequisite steps?** No. The three terms the page depends on are defined in §1
before use, and the dependency order in §4 is explicit. The re-run question that used to block the
build is now measured in §4.1, and the result moved work rather than removing it: step 1's marker is
now a required gate rather than a convenience, because re-running is non-destructive but additive.

**Is every command copy-paste ready with context?** There are no commands to run here; this page is
a measurement summary and a proposal. The one code-shaped block is the measured work-note format,
shown because step 1 argues against relying on it. The procedure this page refers to has its
commands in [08 §6](08-routine-ops.md#6-apply-a-rulebook-change).

**Would a complete novice understand every single sentence?** The hardest idea is why a success
response can mean the event was thrown away. That is given its own paragraph with the mechanism
(`LISTEN`/`NOTIFY` having no queue) rather than asserted, and the two misleading signals — the
stream counter and the `running` status — are called out explicitly, because both would otherwise
reassure a reader who checked them.

**What is measured and what is proposed** is marked per claim: §1, §2 and §4.1 are measured and
dated, §3's recommendation is reasoning from those measurements, and §4's four pieces are a proposal.
One scope limit is flagged in red rather than left implicit: §4.1 exercised the ServiceNow
write-back, not a remediation that changes a machine, because this lab's remediation tasks are debug
messages.
