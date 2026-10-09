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

**Proposed, not built.** Four pieces, in dependency order.

1. **Make the marker explicit.** Reconciliation needs to ask "was this record automated?" and get a
   reliable answer. Today the only marker is a work note whose text the playbook writes. Measured
   format, from a real run on 2026-10-09:

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

4. **Make re-processing safe.** Reconciliation re-sends events, so the playbook may run twice for one
   record. It must be harmless the second time.

> 🔴 **Step 4 is an open question, not a detail, and it should be answered before step 3 is built.**
> The incident handler closes the incident it processed. What a second run does to an
> already-closed incident has **not been tested**, and if it reopens it, writes a duplicate note, or
> fails loudly, reconciliation would be worse than the problem it solves. Test that first.

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
before use, and the dependency order in §4 is explicit — step 4 is marked as blocking step 3,
because building reconciliation on an unsafe re-run would make things worse.

**Is every command copy-paste ready with context?** There are no commands to run here; this page is
a measurement summary and a proposal. The one code-shaped block is the measured work-note format,
shown because step 1 argues against relying on it. The procedure this page refers to has its
commands in [08 §6](08-routine-ops.md#6-apply-a-rulebook-change).

**Would a complete novice understand every single sentence?** The hardest idea is why a success
response can mean the event was thrown away. That is given its own paragraph with the mechanism
(`LISTEN`/`NOTIFY` having no queue) rather than asserted, and the two misleading signals — the
stream counter and the `running` status — are called out explicitly, because both would otherwise
reassure a reader who checked them.

**What is measured and what is proposed** is marked per claim: §1 and §2 are measured and dated,
§3's recommendation is reasoning from those measurements, and §4 is a proposal with one untested
assumption flagged in red.
