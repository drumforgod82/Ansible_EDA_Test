\
# Phase 2b — The Two-Organization Topology (Team A / Team B)

**Historical record and reference.** Not a worklist — the build it described is finished. This
covers the personal lab (ServiceNow PDI `dev211593.service-now.com` + Red Hat Developer Sandbox AAP
**2.7**), not a Centene system. No SOX/change-control framing applies here.

**Gateway:** `https://sandbox-aap-jdrebel2-dev.apps.rm1.0a51.p1.openshiftapps.com`

> ### Read this first
>
> **Teams A and B are complete**, and Teams C and D have since been built on the same pattern. Each
> live team passes all 29 checks in [`scripts/verify_team.py`](../scripts/verify_team.py).
>
> **To build a team, do not use this page.** The click-through steps that used to live here were
> duplicated by, and drifted out of step with, the canonical versions:
>
> | To do this | Go here |
> |---|---|
> | Add a team, by hand or by script | [Routing guide §9](servicenow-dynamic-team-routing.md#9-adding-a-team-worked-example-team-c) |
> | Understand each object in detail | [README Part 2](../README.md#part-2--per-team-setup) |
> | See the whole build order | [README Build order](../README.md#build-order--do-these-in-this-exact-sequence) |
>
> What remains here is the part *not* recorded elsewhere: what the original two-org build produced,
> and what AAP was measured to isolate per organization.
>
> **Trimmed 2026-09-30.** 465 lines of step-by-step were removed because README Part 2 and §9 now
> cover them. They had already caused one real failure: this page told readers for five days that
> tokens, credentials, event streams and activations were still outstanding, long after they were
> done, because the steps lived here and the truth lived in the README. It also carried the last
> uncorrected copy of the `Bearer <token>` mistake (see below).

---

## What the original build produced (verified via API, 2026-09-25)

| Object | Team A | Team B |
|---|---|---|
| Organization | `Team A` (id 2) | `Team B` (id 3) |
| Controller inventory | `Team A Inventory` (id 2) | `Team B Inventory` (id 3) |
| Decision environment | `DE Supported RHEL9 - Team A` (id 3) | `- Team B` (id 4) |
| EDA project | `Ansible EDA Test - Team A` (id 2) | `- Team B` (id 3) |
| Controller project | `EDA ServiceNow - Team A` (id 9) | `- Team B` (id 10) |
| Job template | `Team A Incident Handler` (id 11) | `Team B Incident Handler` (id 12) |
| ServiceNow credential | `ServiceNow PDI - Team A` (id 8) | `ServiceNow PDI - Team B` (id 9) |
| Event stream | `sn-team-a` (id 2) | `sn-team-b` (id 3) |
| Activation | `team-a-incidents` (id 3) | `team-b-incidents` (id 4) |
| Credential type `ServiceNow` (id 33) | global — has `host` input + `SN_HOST` injector | |

Ids are recorded because they are not derivable and appear in API traces. **They are not stable
across a rebuild** — nothing in AAP survives one, so treat them as a snapshot rather than a contract.

Each per-org EDA project discovers **every** rulebook in the repo, not just its own team's. Nothing
filters that list; the right file is chosen by hand on the activation.

---

## Org isolation is weaker than it looks — measured, not assumed

AAP enforces organization scoping **inconsistently** between object types:

| Object | Cross-org reuse | Evidence |
|---|---|---|
| Credential | **Rejected** | `POST .../job_templates/11/credentials/ {"id":6}` → `HTTP 400 "Credential matching query does not exist."` |
| Inventory | **Allowed** | `PATCH .../job_templates/11/ {"inventory":1}` → `HTTP 200`. Team A's template happily used `Demo Inventory` from `Default` |

So an organization is a **hard boundary for secrets and a soft one for everything else**. Do not
present "it's in a different org" as a blanket isolation guarantee in the Centene design — the
guarantee holds for credentials specifically, which is the part that matters most, but it is not a
general property. The per-org inventories in this lab are a deliberate hygiene choice, not something
AAP forced.

A second, later finding in the same family: an organization created through the **controller** API
never propagates to EDA, and EDA refuses to create one directly
(`403 "Create should be done through the platform ingress"`). Organizations belong to the gateway.
Their controller-side and EDA-side ids can also differ. See
[README Part 8](../README.md#part-8--why-the-topology-is-this-way).

---

## What a correct two-org build looks like

Kept as a reviewer's checklist — useful for auditing an existing build, and as the pre-flight before
any cross-org experiment. [`scripts/verify_team.py`](../scripts/verify_team.py) now checks most of
this mechanically, per team; run that first and use this for the items it cannot see.

- [ ] Both organizations are visible in **both** Automation Execution and Automation Decisions org
      pickers — not just one. An org present in the controller but absent from EDA is a real state,
      and it fails later with `Organization with id N does not exist`.
- [ ] The `ServiceNow` credential type shows `username`, `password`, **and `host`** inputs, with an
      `SN_HOST` injector. The playbook asserts on `SN_HOST`.
- [ ] Each team's event stream token is a **distinct** 64-character hex string. One token per stream:
      a shared token means either team's compromise exposes both, and rotating one forces both.
- [ ] Each Event Stream Token credential stores the **bare token**, with no `Bearer ` prefix and the
      **API Key Prefix field empty**.

      > 🔴 **This line used to say the opposite** — "store the value as `Bearer <token>`, capital `B`,
      > one space". That was wrong, and this checklist was the last uncorrected copy of it in the repo.
      > The `ServiceNow Event Stream` credential type compares the `Authorization` header **verbatim**,
      > so a prefix produces a 403 that reads like a permissions problem. A `Bearer ` prefix anywhere
      > in this design is a bug.

- [ ] Each credential uses the `ServiceNow Event Stream` type, **not** `OAuth2 Event Stream` —
      ServiceNow has no RFC 7662 introspection endpoint, so EDA cannot validate tokens against it.
- [ ] Each stream shows **Forwarding: On** and a distinct UUID.
- [ ] No stream forwards the `Authorization` header. Forwarding it copies the live token into
      `event.meta.headers` and from there into the job's `extra_vars` in cleartext.
- [ ] Each EDA project shows **Completed** with a non-empty `git_hash`, and its Rulebooks list
      includes that team's file.
- [ ] Each job template has **Prompt on launch** ticked, and its **Playbook** is
      `servicenow_incident_handler.yml` — *not* a file under `rulebooks/`. Every team runs the same
      playbook; the per-team file is the rulebook, selected on the activation.
- [ ] Each activation is **Running** on its own team's rulebook, and its log shows
      `load source eda.builtin.pg_listener` then
      `Waiting for events, ruleset: Team <X> - ServiceNow incident automation`. If it names
      `ansible.eda.webhook`, the stream mapping did not save.
- [ ] `catchall_debug_rulebook.yml` is attached to **no** activation. It matches every event on
      purpose and exists only to instrument a fan-out test.
- [ ] Verified by observation, not by reading the config: send one event to one stream and confirm
      **only that stream's counter moves**. That is the whole claim of per-team streams, and the
      counters are the cheapest way to separate "never arrived" from "arrived but did not match".
