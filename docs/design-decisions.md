# Design decisions

**This document records why the architecture is shaped the way it is, including the options that were
evaluated and rejected.**

> **This is a reference, not a build stage.** Read it when you want to know *why*, when someone
> proposes changing the topology, or before porting this pattern to another instance.

> **Any unfamiliar word?** Every term and acronym used in these guides is defined in the
> [Glossary](glossary.md) — including AAP, EDA, PDI, SCTASK, data pill, dot-walk, work note
> and `extra_vars`.

> ⚠️ **Scope of verification.** Everything here was checked against a Red Hat Developer Sandbox on
> **AAP 2.7** and a ServiceNow PDI. Nothing has been checked against AAP 2.6 or 2.5. Where a claim
> depends on how EDA's PostgreSQL listener or the event-stream mapping validator is implemented,
> treat it as **version-sensitive** and re-verify before relying on it elsewhere.

---

## 1. One event stream per team, not one shared stream

### 1.1 The question

Once a second team wants ServiceNow to trigger its own automation, there is a fork:

- **one shared event stream** that every team's activation maps to, or
- **one event stream per team**, each with its own token and activation.

The answer hinges on one fact you cannot see from the AAP interface: **does an event stream deliver
each inbound POST to every mapped activation, or to exactly one of them?**

| Delivery model | One event POSTed to a stream mapped to 2 activations |
|---|---|
| **Fan-out** (broadcast) | **Both** activations receive it. Both can match and launch |
| **Queue** (competing consumers) | **Exactly one** receives it. The other never sees it |

If it is fan-out, a shared stream is a live hazard — every team's activation sees every other team's
events, and only your rule conditions stand between "Team A's incident" and "Team B's job template
launches too." If it is a queue, a shared stream is merely inconvenient.

### 1.2 The evidence: it is fan-out

> 🔴 **This is inference from reading the upstream `ansible/eda-server` source, not a documented
> guarantee and not proof by observation.** Red Hat's documentation does not state the delivery
> semantics of a stream mapped to multiple activations anywhere.

- `Activation.event_streams` is a genuine many-to-many relationship. Nothing in the schema limits a
  stream to one activation.
- Each event stream gets a PostgreSQL `LISTEN`/`NOTIFY` channel named `eda_event_stream_<uuid>`,
  derived **only** from the stream's own UUID. No activation identity is folded into the name.
- An inbound POST issues a single `NOTIFY` on that one channel.
- Every activation mapped to that stream opens a `LISTEN` on that same channel.
- `LISTEN`/`NOTIFY` is a **broadcast primitive**: no queue, no acknowledgement, no consumer group, no
  row-claiming. Every listener on a channel receives every notification.

Therefore: **N activations on one stream = N listeners on one broadcast channel = N copies of every
event = potentially N job launches from one ServiceNow POST.**

### 1.3 Experiment 4 — still outstanding

**"Experiment 4"** is the test that would confirm the above empirically rather than by inference.
Several notes in this repository refer to it, so here is what it is:

1. Map the **same** catch-all rulebook (`rulebooks/catchall_debug_rulebook.yml`) onto both Team A's
   and Team B's activations.
2. Point both at **one shared** stream.
3. POST a single event.
4. Count how many activation logs show it.

**Two logs confirms fan-out. One log would falsify it.**

> ⚠️ **It has not been run.** `catchall_debug_rulebook.yml` was to be deleted once Experiment 4 was
> recorded, and it is still in the repository — which is how you can tell. Until then, §1.2 remains
> inference.

> 🔴 **While it exists, never attach `catchall_debug_rulebook.yml` to a production activation.** It
> matches every event on purpose. See
> [Rulebook anatomy §5](rulebook-anatomy.md#5--two-rulebooks-in-this-repo-are-dangerous--leave-them-alone).

### 1.4 This is our decision, not Red Hat's recommendation

> 🔴 **Correcting an earlier claim in this project's own notes.** They stated that Red Hat recommends
> one event stream per organization. **That is wrong**, and it is worth saying plainly so it stops
> being repeated.

- Searching the event-routing chapters for AAP 2.5, 2.6 and 2.7 — the section is titled *simplified
  event routing*, not "event stream routing" — turns up no such guidance. "Organization" appears
  there only as a form-field name when creating a stream.
- What Red Hat *does* document is the opposite axis: one stream endpoint receives events from one
  source and is then usable across **multiple rulebooks**. Their framing leans toward *fewer*
  endpoints reused broadly, not one endpoint per tenant.

**One stream per team is this project's own decision**, made because of the fan-out inference in
§1.2, the token isolation in §1.5, and the organization scoping in
[03 §4](03-aap-eda-setup.md). If you write this up elsewhere, present it as *"our decision, for these
reasons"* — never as *"Red Hat's recommended pattern."*

### 1.5 Tokens: one per stream by default, or one shared — a real choice

The stream's bearer token lives on an Automation Decisions credential of type
`ServiceNow Event Stream`, and that credential is what the endpoint checks on every POST.

**First, the thing that makes this a free choice rather than a constraint: the token and the UUID do
different jobs.**

| Value | Job | Must it be per team? |
|---|---|---|
| **Event stream UUID** | **Selects which stream** the POST lands on. It is the path | **Yes — always.** This is what routing *is* |
| **Token** | Proves the caller is allowed to post. Nothing more | **No.** Your choice |

So sharing a token **cannot** misroute anything. ServiceNow still sends each record to exactly one
team's UUID, taken from that record's route row ([04 §4.1](04-servicenow-app.md)). Routing
correctness comes from the UUID; the token is only authentication. Nothing in EDA compares tokens
across streams, so two streams holding identical token values is a supported configuration, not a
hack.

What differs is **blast radius and rotation**:

| | One token per stream *(default in these guides)* | One shared token |
|---|---|---|
| A leaked token lets the holder post to | that one stream | **every** stream whose UUID they also know |
| Rotation | per team, isolated, no coordination | **lockstep** — every AAP credential and every ServiceNow credential at once, with a window where mismatches return `403` ([08 §4](08-routine-ops.md)) |
| AAP objects | one Event Stream credential per team | **one**, reusable by every stream |
| ServiceNow objects | credential + alias + connection **per team** | **one set total**, with every route row's `connection_alias` pointing at it |
| Objects at 3 teams | 3 AAP + 9 ServiceNow | 1 AAP + 3 ServiceNow |
| Objects at 30 teams | 30 AAP + 90 ServiceNow | 1 AAP + 3 ServiceNow |

**The recommendation stays one token per stream**, because a leak is contained and rotation never
becomes an all-teams outage. The UUID is *not* protected the way the token is — it travels in URLs,
appears in logs and is easy to discover — so the token is the only thing actually separating one
team's endpoint from another's.

**When the shared token is the better call:**

- **A single-owner lab**, where "contain the leak to one team" protects you from yourself and nothing
  else. Three credentials, three aliases and three connections is real clicking for no real benefit.
- **At scale, if the per-team object count is what stops you shipping.** The 30-team column above is
  the honest version of this argument: 120 objects to maintain and rotate by hand, versus 4.

**If you take the shared path, write it down.** The failure mode is not technical — it is somebody
later assuming isolation that is not there, rotating "just Team B's token" and taking down all of
them. Record it in the route table's description or alongside this section, so the next person reads
the decision rather than inferring a guarantee.

> 🔴 **Never share the UUID, whichever token scheme you pick.** One UUID per stream is not a
> preference — two teams pointed at one UUID means both teams' records land on one stream, and
> because streams are fan-out ([§1.2](#12-the-evidence-it-is-fan-out)) every activation mapped there
> receives all of them.

### 1.6 The cost model: streams are cheap, activations are pods

- An **event stream** is a database row plus a PostgreSQL channel. Ten of them cost ten rows.
- A **rulebook activation**, while enabled, is an **always-on pod** running `ansible-rulebook` inside
  its decision environment — not on demand.

That asymmetry is the argument for putting the isolation boundary on the **stream**, which is nearly
free to multiply, rather than on the activation, which is not. One activation per team is the minimum
the fan-out finding requires; the mistake is adding *extra* activations — one per rulebook version,
one per test scenario — where another stream would do.

> ⚠️ **A second reason to keep activation count low on a small cluster.** An activation's pod
> validates its connection to the Controller **at startup**, before serving any event. If the
> Controller is itself cold-starting it returns `503`, the readiness check times out at roughly 65
> seconds, and the activation restarts. **This was previously misdiagnosed as memory or CPU
> pressure; it is not.** Every extra always-on activation independently races the Controller's
> startup.
>
> Compounding it: on Kubernetes, EDA sets only `limits` on activation pods and **never** `requests` —
> both default to none — so what each pod actually gets is decided by the cluster's `LimitRange`,
> not by EDA.

---

## 2. The rulebook hash, and why whitespace costs you a re-attach

A source mapping is pinned to a **SHA-256 of the rulebook file**, computed when you attach the event
stream to the activation. Red Hat states the consequence plainly: if the rulebook is modified after
the mapping is created and a restart happens, the activation fails. The API's error text is:

```
Rulebook has changed since the sources were mapped. Please reattach event streams.
```

It is **plain `sha256` of the file's raw bytes** — measured against a live activation, not inferred.
So you can check for staleness yourself rather than waiting for a restart to fail:

```bash
cd /path/to/Ansible_EDA_Test
git show <eda-project-git-hash>:rulebooks/team_a_rulebook.yml | shasum -a 256
```

Expected output: a 64-character hex digest. Compare it against `rulebook_hash` inside the
activation's `source_mappings`. `scripts/verify_team.py` does this comparison for you.

> 🔴 **Use the *synced revision*, not your working tree.** An uncommitted edit is not what AAP is
> running.

> ⚠️ **There is no content normalisation — whitespace counts.** A single trailing newline produces a
> different hash and invalidates the mapping. So reformatting a rulebook, or an editor that silently
> appends a final newline on save, costs the full re-attach cycle even though nothing functional
> changed.

> ⚠️ **Automation Execution and Automation Decisions sync independently**, even pointing at the same
> Git URL. So the controller project and the EDA project can sit at two *different* revisions of the
> same repository. Check a project's synced revision against `git log` before diagnosing a mapping
> failure as anything else.

Procedure: [03 §3](03-aap-eda-setup.md). Diagnosis: [10 §6.7](10-troubleshooting.md).

---

## 3. Routing lives in a custom table, not a Decision Table

**Evaluated 2026-10-06 and rejected.** A ServiceNow **Decision Table** — Decision Builder — was
considered for the assignment-group-to-stream mapping, and built end to end on the PDI before being
set aside.

### 3.1 Why it was plausible

Decision tables are an established pattern on Centene's instances, including for exactly this kind of
work: one routing table there carries over a thousand rows of assignment logic. The feature is
neither obscure nor discouraged.

### 3.2 Why it was rejected

| Reason | Detail |
|---|---|
| **It is a one-key mapping, not a decision matrix** | One assignment group resolves to exactly one stream, with no priority or environment overrides. That is a foreign key. A decision table's value is holding *precedence* between competing conditions, and there are none |
| **It adds a publish step to a data change** | Onboarding a team should be inserting a row. With a decision table it is a row plus publishing a governed artifact, and nothing takes effect until published |
| **It would put stream UUIDs in an exportable artifact** | Those are closer to credentials than business rules. They belong in a table with ACLs on it |
| **Troubleshooting gets harder** | The flow log shows the lookup, its query and the matched row. A decision table returns a sys_id without showing why — and three different causes of an empty result are indistinguishable: table unpublished, no condition matched, or a mismatched input key |
| **There is no flow action for it** | No generic "evaluate a decision table" Flow Designer action exists, so it costs a script step on top |

### 3.3 The division that settles it

> **ServiceNow owns *membership* (is this record enrolled) and the *delivery address* (which stream).
> The rulebook owns *what runs and under what conditions*.**

That is why priority will never select a stream: priority is a *condition*, so it belongs in a
rulebook condition. A per-priority stream would be using the address space to express a condition.

### 3.4 What would reopen it

Only one thing: **ServiceNow taking back ownership of automation selection from the rulebooks.** That
is an architectural reversal, not incremental growth. "More streams" is not a trigger — thirty
streams keyed on one attribute is still a foreign key.

---

## 4. Open questions — genuinely unsettled

These are recorded as unknown rather than guessed at.

| Question | Status | How to settle it |
|---|---|---|
| ~~Does a bad token return `401` or `403`?~~ | **SETTLED 2026-10-07: `403`.** A missing header is `400`, and so is an unknown UUID — `404` is never returned | Measured; commands recorded in [07 §2.1](07-end-to-end-test.md) |
| Is `spec.api` the right Custom Resource path? | **Unconfirmed.** A merge patch silently discards unknown fields, so a wrong path looks like success | `K explain ansibleautomationplatform.spec` — see [01 §4](01-provision-aap.md) |
| Is fan-out real, or only inferred? | **Inferred from source**, not observed | Experiment 4, §1.3 |
| Can an activation select another organization's stream? | **Undocumented and untested upstream** | See §4.1 below — but do not design on the answer |

### 4.1 The cross-organization caveat — do not design on it either way

Can an activation in one organization select an event stream belonging to a different one?

From reading the source, the only gate is RBAC — whether your account can see and select the other
organization's stream — and the mapping validator performs **no organization-equality check**. That
is a statement about the current code path, not a guarantee, and exactly the kind of implementation
detail that changes without a changelog entry.

> 🔴 **Whatever a hands-on test shows, do not build a design around it.** If you need an
> organization boundary to hold, enforce it with separate streams and separate tokens (§1.5), which
> make cross-organization delivery structurally impossible — not with an assumption about validator
> behaviour that Red Hat has never committed to.

### 4.2 The `Authorization` header: two sources disagree

- This project's build guide says that listing `Authorization` in a stream's *Additional data
  headers* copies the token into `meta.headers`, into the job's `extra_vars`, and into the AAP
  database **in cleartext**.
- An older note in this repository says headers are dropped unless listed, **and `Authorization` is
  always redacted regardless, with no override.**

**Both cannot be true, and the question has not been settled.**

> 🔴 **The prohibition stands either way, because the cost is asymmetric.** If the redaction claim is
> right, listing `Authorization` gains you nothing. If it is wrong, you have written a live
> credential into a database in plain text. **Never list it.**

Related and not in doubt: never write a rule condition against `event.meta.headers.Authorization` or
any header expecting to route on it. By design the one header you would most want to check is the one
you can never see.

---

## 5. Smaller findings worth not relearning

- **"An event stream can only be used once in a rulebook source swap" is per-activation, not
  global.** Read literally it sounds like it forbids the fan-out topology in §1. It does not — it
  means you cannot map one stream to two different `sources:` entries **inside the same activation's
  rulebook**. It says nothing about two *different* activations each mapping the same stream.
  Misreading it as a global rule would rule out fan-out before you tested for it.
- **On a shared stream, `event.meta.eda_event_stream_name` is useless as a tenant discriminator** —
  it is identical for every tenant. It is only unforgeable *and* useful when each tenant has its own
  stream. On a genuinely shared stream you would fall back to a payload field like `target_team`,
  which a sender **can** forge.
- **A stream must have forwarding on before it can be selected on an activation's mapping page.** A
  stream left in test mode simply does not appear as an option. If you are troubleshooting why a
  stream "isn't there", that is a configuration gap, not broken routing.
- **The two testing modes are mutually exclusive, per stream.** Forwarding on and you read the
  activation log; forwarding off and you read the stream's Events tab while nothing launches. See
  [03 §2.11](03-aap-eda-setup.md).
- **Organization isolation is asymmetric.** Attaching another organization's *credential* to a job
  template is rejected; attaching another organization's *inventory* succeeds. An organization is a
  hard boundary for secrets and a soft one for everything else. Full classification:
  [03 §4](03-aap-eda-setup.md).

---

## Self-check

**Did I skip any prerequisite steps?** This document performs no steps. It exists because five
places in the old documentation referred to "Experiment 4" while only one defined it, and because
the reasoning behind the topology was mixed into a build guide where nobody would find it.

**Is every command copy-paste ready with context?** The two commands — the `shasum` comparison in §2
and the `curl` referenced in §4 — both state their working directory or link to the document holding
the full form, and §2 states its expected output.

**Would a complete novice understand every single sentence?** This is the one document in the set
that assumes you have already built the thing, so it uses the vocabulary freely and leans on the
[Glossary](glossary.md). Where a claim's *confidence* matters more than its content — fan-out being
inferred rather than observed, the cross-organization behaviour being undocumented, the header
question being unsettled — that status is stated before the claim rather than after it.
