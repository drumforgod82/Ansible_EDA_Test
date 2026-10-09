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

> ✅ **Measured 2026-10-08 — it is fan-out, observed rather than inferred.** Three activations were
> pointed at one shared stream, two of them running the identical catch-all rulebook so the
> comparison was symmetric. Five events were posted one at a time, each with its own identifier, and
> every activation's log was read separately. **All three logged all five: fifteen receipts for five
> events.** A queue would have produced five in total. Five trials, not one, because under queue
> semantics the winning consumer can alternate.
>
> **Red Hat still documents nothing about delivery semantics**, so this is what this version does
> rather than a guarantee you can hold them to. The reasoning below explains *why* it behaves this
> way and is worth keeping for that — but the conclusion no longer rests on it.

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

### 1.3 Experiment 4 — run, and the answer is fan-out

**"Experiment 4"** was the test that would confirm the above empirically rather than by inference.
It was run on 2026-10-08. Several notes in this repository refer to it, so here is what it was and
what it found:

1. Map the **same** catch-all rulebook (`rulebooks/catchall_debug_rulebook.yml`) onto both Team A's
   and Team B's activations.
2. Point both at **one shared** stream.
3. POST a single event.
4. Count how many activation logs show it.

**Two logs confirms fan-out. One log would falsify it.**

> ✅ **Result, 2026-10-08: fan-out.** Run with three activations rather than two — the two symmetric
> catch-all listeners plus one unrelated activation already on that stream — and repeated five
> times. Every activation logged every event: **fifteen receipts for five events**, where a queue
> would have produced five. Both listeners' logs contain the same event identifier, each with its
> own rules engine reporting the event received. No job was launched, because the probe carried an
> event type no rule matches.
>
> **So §1.2 is now a measurement, not an inference.** What remains unanswered is whether the
> behaviour is *supported* rather than simply what this version does, because the vendor publishes
> no statement on delivery semantics either way.

> ℹ️ **`catchall_debug_rulebook.yml` has served its purpose and can now be deleted**, along with the
> two `exp4-listener-*` activations the run created
> ([08 §4.2](08-routine-ops.md#42-temporary-objects-in-the-sandbox--what-they-are-and-when-to-remove-them)).
> It is kept for the moment only so the experiment can be repeated on a future AAP version, since
> the result is a property of the implementation rather than a documented contract.

> 🔴 **While it exists, never attach `catchall_debug_rulebook.yml` to a production activation.** It
> matches every event on purpose. See
> [Rulebook anatomy §5](rulebook-anatomy.md#5--not-every-rulebook-here-is-safe-to-attach).

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

> 📌 **What this lab runs today, changed 2026-10-08: the shared token.** All three teams authenticate
> with **one** credential object — `shared-stream-token` in AAP, reached through the single
> `Ansible EDA Shared Alias` in ServiceNow. The guides in
> [03 §2.9](03-aap-eda-setup.md) still *teach* one token per team, because that is the better default
> for a shared-ownership environment; this single-owner lab deliberately took the other path to test
> whether it works. It does — see the measurements below. The per-team aliases for the second and
> third teams still exist but no route row points at them, so reverting is one field edit per row.

**First, the thing that makes this a free choice rather than a constraint: the token and the UUID do
different jobs.**

| Value | Job | Must it be per team? |
|---|---|---|
| **Event stream UUID** | **Selects which stream** the POST lands on. It is the path | **Yes — always.** This is what routing *is* |
| **Token** | Proves the caller is allowed to post. Nothing more | **No.** Your choice |

So sharing a token **cannot** misroute anything. ServiceNow still sends each record to exactly one
team's UUID, taken from that record's route row ([04 §4.1](04-servicenow-app.md)). Routing
correctness comes from the UUID; the token is only authentication. Nothing in EDA compares tokens
across streams.

**Measured end to end on 2026-10-08.** This was reasoning until that date, so it is now recorded as
a result rather than an argument. With one shared token serving three streams in three different
organizations, one qualifying record was created per team. Each team's stream counter rose by exactly
one, no other team's counter moved, and three jobs launched — one per team, each from its own ruleset,
each with `target_team` and `source_stream` matching that record's own team. Sharing the token cost
nothing in routing isolation.

#### Two different things are both called "sharing a token"

They behave identically at the endpoint and they are **not** interchangeable, because only one of
them saves you anything. A **credential object** is the stored record; a **token value** is the
64-character string inside it.

| | What you build | Objects at 30 teams | Saves work? |
|---|---|---|---|
| **One shared credential object** | a single Event Stream credential, reused by every stream | 1 AAP + 3 ServiceNow | **Yes.** This is the whole argument for sharing |
| **Same token value, pasted into one credential per team** | 30 separate credentials that happen to hold the same string | 30 AAP + 90 ServiceNow | **No.** Identical object count to per-team tokens |

Both authenticate, so a test passes either way. The second gives you a shared token's blast radius
**and** the full per-team administrative burden, which is strictly worse than giving each team its own
token. If you share, share the object.

> ✅ **Measured 2026-10-08:** one credential object can be referenced by event streams belonging to
> **different organizations**. An event stream owned by one organization was repointed at a credential
> owned by another; the change was accepted and a request carrying that shared token was accepted at
> the stream. This had never been tested before that date and is the premise the whole shared-token
> option rests on.

> ⚠️ **Permitted is not the same as supported.** What the measurement shows is that the platform
> allows this, not that Red Hat endorses it. Red Hat documents only that *each event stream must have
> exactly one credential* and says nothing about the reverse direction — whether one credential may
> serve several streams. Treat it as working-but-unblessed and ask the vendor before relying on it in
> production.

> ℹ️ **The organization boundary on credentials is not applied consistently.** Attaching another
> organization's credential to a **job template** is refused outright (measured: HTTP 400,
> `Credential matching query does not exist`), while referencing another organization's credential
> from an **event stream** is accepted and works (measured 2026-10-08). Same credential concept, two
> different answers depending on what you attach it to. Do not generalise either result to the other.

What differs is **blast radius and rotation**:

| | One token per stream *(default in these guides)* | One shared token |
|---|---|---|
| A leaked token lets the holder post to | that one stream | **every** stream whose UUID they also know |
| Rotation | per team, isolated, no coordination | **lockstep** — every AAP credential and every ServiceNow credential at once, with a window where mismatches return `403` ([08 §4](08-routine-ops.md)) |
| AAP objects | one Event Stream credential per team | **one credential object**, referenced by every stream |
| ServiceNow objects | credential + alias + connection **per team** | **one set total**, with every route row's `connection_alias` pointing at that one alias |
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

**Keep the alias on the route row even when every row holds the same value.** Under a shared token all
thirty rows name one alias, so the `connection_alias` column looks like redundancy and invites someone
to delete it and hard-code the alias into the flow's REST step instead. Do not. The column costs one
reference per row and it is the seam that lets a single team be moved onto a different alias later —
a team with its own trust requirement, a team on a separate AAP instance, a team mid-migration —
**without editing the flow at all**. Hard-coding removes that option and buys nothing.

> ℹ️ **Why the flow does not care.** The REST step takes the alias as a bare reference pill — a
> dragged-in token representing the route row's `connection_alias` field — so it resolves per record
> at run time. Pointing a row at a different alias is a field edit, not a flow change. The flow build
> is in [06 — the ServiceNow flow](06-servicenow-flow.md).

**If you take the shared path, write it down.** The failure mode is not technical — it is somebody
later assuming isolation that is not there, rotating "just Team B's token" and taking down all of
them. Record the decision where the next person will actually meet it.

> ⚠️ **The table's own description field is not writable through the Table API.** A `PATCH` to
> `short_description` on the table record returns `200` and changes nothing — tried twice on
> 2026-10-08 and confirmed empty afterwards by reading it back. Either set it in the user interface,
> or put the note somewhere the API does accept it. On this instance it is recorded in two places that
> a reader meets anyway: the **description of the shared connection alias** in ServiceNow, and the
> **description of the shared Event Stream credential** in AAP.

> 🔑 **A `200` that changes nothing looks exactly like success.** Always read the field back after
> writing it. This applies to every write in these guides, not just this one.

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
> different hash. So reformatting a rulebook, or an editor that silently appends a final newline on
> save, costs a sync and a restart even though nothing functional changed.

### 2.1 What a rulebook edit actually costs — measured 2026-10-09

The paragraphs above describe the hash correctly. The *consequence* needed narrowing, because a real
rulebook edit was pushed, synced and restarted end to end to find out. A comment-only change was
used, so the rulebook's **sources were not altered** — that limit matters, and
[§2.2](#22-what-was-not-tested) says why.

What happened, in order:

1. **The sync rewrote the stored hash by itself.** The rulebook changed from `b2574fed…` to
   `a38082c1…`, and the activation's `source_mappings` showed `a38082c1…` with no manual
   re-attach. **The mapping is not left stale by an edit**, which is the premise the "you must
   re-attach" advice rests on.
2. **The sync updated the rulebook record in place.** Same `rulebook_id`, still one row for that
   filename in that project. An activation does **not** need repointing at a new rulebook id. Note
   that `modified_at` on the rulebook did *not* change, so it cannot be used to detect an edit.
3. **The running activation kept the old rulebook**, exactly as documented — the project sat at the
   new Git revision while the running instance still reported the old one.
4. **A plain stop and start picked up the new rulebook.** The new instance reported the new Git
   revision. **No event stream re-attach was required for the edit to take effect.**
5. **The flag survived that restart.** AAP still reported *"Rulebook content has changed since event
   stream sources were mapped"* even though the hash was correct and the new rulebook was loaded.
   Rewriting `source_mappings` is what clears it.
6. **Events routed correctly at every step** — including while the flag was set, and before the
   restart on the old rulebook.

So the required cycle is **sync → restart**. Re-attaching the event stream clears a flag; it is not
what makes the edit live. `scripts/eda_apply_rulebook_change.py` does both over the API in about 40
seconds and is documented in
[08 §6](08-routine-ops.md#6-apply-a-rulebook-change).

**The failure in the error text above is real, and still reachable.** Writing a deliberately wrong
`rulebook_hash` into the mapping was accepted by the API with `HTTP 200`, and the activation then
**refused to start**: `enable` returned `HTTP 400` and the activation went to `error`, routing
nothing. So a genuinely stale hash does stop the activation — it fails closed and loudly, rather
than misrouting quietly. What changed is that an ordinary edit no longer produces that state,
because step 1 above fixes the hash for you.

### 2.2 What was not tested

The change used above was **a comment only**, so the rulebook's `sources:` block was untouched and
the existing `__SOURCE_1` mapping stayed meaningful.

A rulebook edit that **adds, removes or renames a source** is a different case and was not
measured. There the source-to-stream binding itself — not just the hash — may genuinely need
rebuilding, and the re-attach advice may hold exactly as originally written. Treat a change to a
`sources:` block as requiring the manual re-attach until somebody measures it.

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

> ℹ️ **If it ever is reopened, two findings from the PDI build are worth not rediscovering.** The
> scriptable entry point is **`sn_dt.CachedDecisionTableAPI`**, and `executeDecisions(dt, input)` is
> the method that returns answers — every `sn_decision_table.*` Script Include is `package_private`
> and unusable from a scoped app. And calling it creates a `sys_scope_privilege` row **per method,
> not per class**, so `isEmptyDecisionTable` and `executeDecisions` are two separate grants. A
> background script auto-grants them; **a flow running in the background fails instead.** Pre-grant
> both.

### 3.5 If you ever need to route on more than the assignment group

**You almost certainly do not.** This applies only when **the team itself changes with record
content** — "P1 database incidents go to Team B even though the group says Team A". If the
destination is stable and only the *work* differs, that is a rulebook condition, not a routing
change, and §3.3 is why.

The concrete version of §3.3, because it is easy to agree with in the abstract and then build the
wrong thing: a team wanting different automation per priority needs **no ServiceNow change at all**.
The payload already carries `priority`, `state`, `urgency`, `impact`, `category`, `cmdb_ci` and
`short_description`, so the rulebook dispatches on its own:

```yaml
    - name: Launch Team A critical handler
      condition: >-
        event.meta.eda_event_stream_name == "sn-team-a" and
        event.payload.event_type == "servicenow.incident.created" and
        event.payload.priority == "1"
      action:
        run_job_template:
          name: "Team A Critical Incident Handler"
          organization: "Team A"
```

One row per team in ServiceNow, branching in a purpose-built rule engine, and changes shipping
through Git instead of Flow Designer.

**If the destination genuinely must vary**, the cheapest extension is extra match columns on
`EDA Team Route` — say `Priority` and `Category` (String) — with an empty column meaning *any value*.
It needs no script. Two details decide whether it works:

1. **Express each optional field as two OR'd condition rows, not an "is one of".** The pair is
   `Priority is empty` **OR** `Priority is <the record's priority>`. The `is empty` row is what makes
   a blank column behave as a wildcard.
2. **Add an `Order` column (Integer) and set the lookup's `Order by` to it, ascending.** Give specific
   rows a *lower* number than catch-all rows.

> 🔴 **Point 2 is not optional, and skipping it produces a bug that looks like flakiness.** With
> wildcards, **more than one row matches** — a `Priority = 1` row and a `Priority` empty row both
> satisfy a critical incident. *Return only the first record* then picks whichever the sort puts
> first, so with no explicit `Order by` the winner is **effectively arbitrary and appears to change
> for no reason.**

A third shape exists — a **Conditions**-type column on each row, giving every route row its own
condition builder, resolved by a script step that walks rows in `Order` and returns the first match.
It is more flexible and costs a script step. It was designed and never built; the working draft is in
git history in `docs/servicenow-dynamic-team-routing.md` §10 (removed 2026-10-07) if it is ever
wanted.

---

## 4. Open questions — genuinely unsettled

These are recorded as unknown rather than guessed at.

| Question | Status | How to settle it |
|---|---|---|
| ~~Does a bad token return `401` or `403`?~~ | **SETTLED 2026-10-07: `403`.** A missing header is `400`, and so is an unknown UUID — `404` is never returned | Measured; commands recorded in [07 §2.1](07-end-to-end-test.md) |
| ~~Is `spec.api` the right Custom Resource path?~~ | **SETTLED 2026-10-07 — yes, on AAP 2.7.** `K explain ansibleautomationplatform.spec.api` describes it as *"The gateway api deployment"*, and it patches the **`api` container of the gateway Deployment** — so the verification output reads `api=2Gi`, not `gateway=2Gi` | Verified against the live CR — [01 §4](01-provision-aap.md) |
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
