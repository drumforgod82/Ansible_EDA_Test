# 08 — Routine operations

**This document covers the four jobs you do repeatedly once the pipeline works: enrolling an item,
adding a team, adding a record type, and rotating a token.**

> **Previous stage:** [07 — End-to-end test](07-end-to-end-test.md) · **Next:**
> [10 — Troubleshooting](10-troubleshooting.md) is the reference you will reach for from here on;
> there is no further build stage.

> **Any unfamiliar word?** Every term and acronym used in these guides is defined in the
> [Glossary](glossary.md) — including AAP, EDA, PDI, SCTASK, data pill, dot-walk, work note
> and `extra_vars`.

---

## 0. Pick your job

| Job | How often | Effort | Go to |
|---|---|---|---|
| Enrol a catalog item | Most often | One table row | [§1](#1-enrol-a-catalog-item) |
| Add a team | Occasionally | ~45 minutes across Git, AAP and ServiceNow | [§2](#2-add-a-team) |
| Add a record type | Rarely | Several hours | [§3](#3-add-a-record-type) |
| Rotate a token | On a schedule, or after exposure | Two edits | [§4](#4-rotate-an-event-stream-token) |

---

## 1. Enrol a catalog item

This is the smallest and most frequent change. **One row, no publish, no restart.**

1. In ServiceNow, open the **EDA Enabled Catalog Items** table.
2. Click **New**.
3. Fill in **either** `Catalog Item` **or** `Order Guide` — never both.
4. Tick **Active**.
5. Save.

That is the whole job. The flow reads this table on every run, so the change takes effect
immediately.

> ℹ️ **Prefer an order guide row when one applies.** One guide row covers every item orderable
> through that guide, instead of a row per item. See [04 §4.2](04-servicenow-app.md).

> ⚠️ **Enrolling an item both directly and via a guide is harmless but pointless.** It matches two
> rows; the flow's `Count > 0` gate is duplicate-proof, so it still sends exactly one event. Do not
> "fix" it by adding a `For Each` loop — that *would* send two.

> ✅ **Verify:** create a test record for that item and confirm a work note appears. If nothing
> happens, check the record matched the flow's **trigger** before suspecting the table —
> see [06 §1.2](06-servicenow-flow.md).

---

## 2. Add a team

Worked example: adding **Team C** to an instance that already has Team A and Team B.

### 2.0 By hand, or with the provisioning script?

There are two ways to do this, and the recommendation depends on whether you have done it before.

| | By hand (§2.1 onward) | `scripts/provision_team.py` |
|---|---|---|
| Effort | ~45 minutes | A few minutes |
| What it builds | You create each object | All of the AAP objects, and renders the rulebook |
| ServiceNow | You do all five objects | Prints a checklist with resolved values; `--servicenow-apply` inserts them |
| Safety | Yours to get right | **Dry run by default** — nothing is written without `--apply` |

> ℹ️ **Build your first team by hand.** The script removes four silent failure modes *by
> construction* — the token is generated once and used on both sides so there is no paste to get
> wrong, the stream UUID is known rather than copied, the playbook-versus-rulebook choice is a
> constant, and prompt-on-launch is a constant. That is exactly why a successful scripted run
> **teaches you nothing about them** — and those four are the failures you will spend your time on
> when something breaks later.
>
> Do one by hand to learn where the traps are, then script every team after that.

<details>
<summary>Using the script</summary>

It is **check-then-create** at every step, so re-running after a partial failure resumes rather than
duplicating, and everything it creates is recorded in a manifest — which is what makes `--destroy`
exact rather than approximate.

```bash
cd /path/to/Ansible_EDA_Test
export AAP_GATEWAY="https://<your-aap-host>"

# 1. render this team's rulebook from an existing one, then stop
python3 scripts/provision_team.py --team team-c --template a --render-rulebook

# 2. commit and push -- the EDA project can only offer a rulebook the remote has
git add rulebooks/team_c_rulebook.yml && git commit -m "Add Team C rulebook" && git push

# 3. preview everything. writes nothing
python3 scripts/provision_team.py --team team-c

# 4. build it
python3 scripts/provision_team.py --team team-c --apply

# 5. check it
python3 scripts/verify_team.py --team team-c
```

Useful flags: `--aap-only` skips the ServiceNow section, `--no-activate` skips creating the
activation pod, `--force-render` overwrites an existing rulebook, and `--destroy` removes exactly
what the manifest records.

**Environment it needs:** `SANDBOX_AAP_PAT_TOKEN`, `SN_PDI_HOST`, `SN_PDI_PROVISION_USERNAME`,
`SN_PDI_PROVISION_PASSWORD`, plus `AAP_GATEWAY` or `--gateway`. Secrets are never printed; payload
previews mask them.

> ⚠️ **Step 2 is not optional and not reorderable.** The script renders the rulebook locally, but
> AAP clones from the remote — so an unpushed rulebook cannot be selected for the activation.

</details>

If you are building by hand, carry on.

### 2.1 The names, decided once

Copy these exactly. A typo in either **bold** name fails silently.

| Where | Object | Name for Team C |
|---|---|---|
| Git | Rulebook file | `rulebooks/team_c_rulebook.yml` |
| AAP | Organization | `Team C` |
| AAP | Inventory | `Team C Inventory` |
| AAP | ServiceNow credential | `ServiceNow PDI - Team C` |
| AAP | Source control credential (Automation Execution) | `Team C Source control` — omit for a public fork |
| AAP | Controller project | `EDA ServiceNow - Team C` |
| AAP | Job template | **`Team C Incident Handler`** |
| AAP | AAP Controller credential | `Team C AAP Controller` |
| AAP | Decision environment | `DE Supported RHEL9 - Team C` |
| AAP | EDA project | `Ansible EDA Test - Team C` |
| AAP | Red Hat registry credential | `Team C Red Hat Registry` |
| AAP | Source control credential (Automation Decisions) | `Team C Source control` — omit for a public fork |
| AAP | Event stream credential | `Team C Event Stream Token` |
| AAP | Event stream | **`sn-team-c`** |
| AAP | Rulebook activation | `team-c-incidents` |
| ServiceNow | Assignment group | `Team-C` |
| ServiceNow | API Key credential | `Ansible EDA Team C Token` |
| ServiceNow | Alias | `Ansible EDA Team C Alias` |
| ServiceNow | HTTP connection | `Ansible EDA Team C Connection` |
| ServiceNow | Route table row | one row, with `team_code` = `team-c` |

> 🔴 **Two names are matched as strings at run time**, and those are the bold ones:
> - the rulebook finds the **job template by name**, and
> - the rulebook's condition tests the **event stream name**.
>
> Get either wrong and nothing fires, with no error naming the mismatch. Everything else in this
> table is a naming *convention* — consistency helps you, but nothing breaks if it differs.

> ℹ️ **The alias has two written forms, and both are correct.** You type the name with spaces when
> creating it; ServiceNow then refers to it internally with underscores and your scope prefixed:
>
> | Form | Example | Where you see it |
> |---|---|---|
> | Record **name** | `Ansible EDA Team C Alias` | What you type in §2.5, and the alias list |
> | Scoped **reference** | `x_661661_james_tes.Ansible_EDA_Team_C_Alias` | The route table's rendered value, and quoted in `Unable to load connection with alias ID:` errors |
>
> Seeing the underscored form in an error message does **not** mean you named it wrongly.

> ℹ️ **The assignment group is *not* matched by name.** The route table's `assignment_group` column is
> a **reference** holding the group's sys_id, so renaming the group later is safe. What *does* break
> routing is deleting and recreating a group, which mints a new sys_id — the new one has a different
> sys_id and the route row still points at the old one.

### 2.2 Phase 0 — the rulebook, first

The EDA project can only offer a rulebook that is **already pushed to the remote**, so this comes
before anything in AAP.

1. Copy an existing rulebook:

   ```bash
   cd /path/to/Ansible_EDA_Test
   cp rulebooks/team_b_rulebook.yml rulebooks/team_c_rulebook.yml
   ```

2. Change **five** values. They sit on four lines, which is exactly how one gets missed.

   > ℹ️ **If you have never opened a rulebook, read
   > [Rulebook anatomy](rulebook-anatomy.md) first.** It walks through a real one and shows where
   > each of these five values lives — including why two of them are matched as exact strings at run
   > time and the other three are not.

   | What | New value |
   |---|---|
   | `name:` at the top | `Team C - ServiceNow event automation` |
   | the rule's `name:` | `Launch Team C incident handler` |
   | the condition's stream name | `"sn-team-c"` |
   | `run_job_template.name` | `"Team C Incident Handler"` |
   | `run_job_template.organization` | `"Team C"` |

3. Leave the `extra_vars` block alone, including `sn_close_incident: true`.
4. Commit and push.

> ✅ **Verify — both checks, not just the first:**
>
> ```bash
> python3 -c "import yaml;yaml.safe_load(open('rulebooks/team_c_rulebook.yml'))"
> grep -n 'Team B\|team-b\|team_b' rulebooks/team_c_rulebook.yml
> ```
>
> Expected output: nothing from either command. Silence from the first means the YAML parses.
> Silence from the second means no Team B leftovers.
>
> **Why the second check matters.** A rulebook still carrying Team B's *rule name* is valid YAML and
> still fires, so the parse cannot catch it. Rule names are never matched on, so nothing breaks — but
> `Last rule fired` on the activation, and the rule name inside the job's event payload, then both
> name the wrong team. That is precisely the signal the isolation test in §2.6 depends on, so a wrong
> name here makes a **passing test unreadable** rather than making it fail. It was missed on the real
> Team C build.

### 2.3 Phase 1 — the token

```bash
openssl rand -hex 32
```

Put it in your password vault now. You will paste this same value into **two** places: AAP in
Phase 2, ServiceNow in Phase 3.

> ✅ **Verify:** it is exactly **64** characters.

Optional, on macOS — store it in the Keychain, one item per team:

```bash
security add-generic-password -a "$USER" -s sandbox-eda-team-c -w -U
```

> 🔑 **Leave `-w` with no value** so it prompts instead of taking the token as a command argument,
> which would record it in your shell history. Details in [03 §2.9](03-aap-eda-setup.md).

### 2.4 Phase 2 — AAP

Follow [03 §2.1–§2.12](03-aap-eda-setup.md) with the Team C names above, in that order:
organization → inventory → credentials → controller project → job template → EDA credentials →
decision environment → EDA project → event stream credential → event stream → activation.

Three points specific to adding a team:

- **The event stream credential takes the Phase 1 token, bare** — no `Bearer ` prefix.
- **When the EDA project syncs it lists every rulebook in the repo.** Pick `team_c_rulebook.yml`.
  Nothing filters the list for you.
- **After creating `sn-team-c`, copy its generated URL.** The UUID inside it goes into the route row
  in Phase 3.

> 🔴 **Do not forget *Prompt on launch* on the job template.** Without it the controller discards the
> variables the rulebook sends, and the job fails on undefined variables with nothing explaining why.

> 🔴 **The job template's `Playbook` is `servicenow_incident_handler.yml`** — not
> `rulebooks/team_c_rulebook.yml`. The dropdown lists both, because the controller project is this
> same repository. **Every team runs the same playbook;** the per-team file is the *rulebook*, chosen
> on the activation. Pick wrong and it fails only when an event arrives, with
> `ERROR! 'sources' is not a valid attribute for a Play` — which sends you debugging the rulebook
> instead of this one field.

> ✅ **Verify:** the activation reaches **Running** and its log shows
> `load source eda.builtin.pg_listener` followed by `Waiting for events` naming the Team C ruleset.
> If it says `ansible.eda.webhook`, the stream mapping did not save.

### 2.5 Phase 3 — ServiceNow

Set the application picker to your scoped app first, **except** for step 1.

1. **Assignment group `Team-C`** — *User Administration → Groups → New*. Create this **in Global**,
   not the scoped app, because `sys_user_group` is a platform table. Add at least one member.
2. **API Key credential** `Ansible EDA Team C Token` — header `Authorization`, value is the Phase 1
   token **bare**, with the **API Key Prefix field left empty**.
3. **Alias** `Ansible EDA Team C Alias` — type *Connection and Credential*, connection type HTTP.
4. **HTTP connection** — create it from the **alias's HTTP Connections related list**, not from the
   Connections table. Connection URL is the AAP host, **base URL only**.
5. **One row in `EDA Team Route`:**

   | Column | Value |
   |---|---|
   | `assignment_group` | `Team-C` |
   | `team_code` | `team-c` |
   | `event_stream_name` | `sn-team-c` |
   | `event_stream_uuid` | the UUID from Phase 2 |
   | `connection_alias` | `Ansible EDA Team C Alias` |
   | `active` | true |

Full detail for steps 2–4 is in [04 §5](04-servicenow-app.md).

> ✅ **Verify:** open the alias — its **HTTP Connections** list has one row, and that connection has
> a **Credential** attached. An alias with no child connection produces
> `Unable to load connection with alias ID:` at run time.

### 2.6 Phase 4 — test, including isolation

Create an incident with **Caller** = `Event Management` and **Assignment group** = `Team-C`.

| Check | Where | Expect |
|---|---|---|
| Flow ran | ServiceNow → the flow's Executions | the `If Successful` branch is **true** |
| Action outputs | same, expand the action | `http_status = 200`, `success = true` |
| Event arrived | AAP → Event Streams | `sn-team-c` **Events received** incremented; **`sn-team-a` and `sn-team-b` unchanged** |
| Job ran | AAP → Jobs | `Team C Incident Handler`, status **Successful** |
| Routing correct | that job → Details → Extra variables | `target_team: team-c`, `source_stream: sn-team-c` |
| Write-back | the incident | a work note was added, and the state is **Closed** |

> 🎯 **The "unchanged" row is the one worth pausing on.** It proves per-team streams actually
> *isolate*, not merely that Team C works. If all three counters move, both activations are mapped to
> the same stream — event streams are fan-out, not a queue.

---

## 3. Add a record type

Adding SCTASK or Problem support is a much larger job than adding a team — new playbooks, new job
templates, a new rulebook rule, a new action and a new flow.

**It has its own guide: [`adding-record-types.md`](adding-record-types.md).**

What it covers, in order: the enrollment table, the playbooks, the job templates, the rulebook rule,
the action, the flow, and testing. Phase 8 of that document covers Problem specifically, including
what Problem automation **cannot** do — `problem.state` is dictionary-read-only, so automation writes
findings and a human closes the record.

> 🔴 **Create every job template *before* you sync the EDA project.** The rulebook names its template
> by string, so a rule referencing a template that does not exist yet fails at event time with
> nothing useful in ServiceNow.

> ✅ **Reviewed in full and corrected 2026-10-07.** That guide was previously flagged here with two
> defects. Only one was real:
>
> - **Real, now fixed:** it stated the route table is "keyed on team code". It is keyed on
>   **assignment group**.
> - **Not a defect — this flag was wrong:** its Problem flow in §8.6 was described here as
>   **fail-open**. It is not. §8.6 builds `If Sys ID is empty → End Flow`, which is fail-*closed* —
>   an unrouted problem exits before the action. The gate is silent rather than absent, which is a
>   diagnosability gap and is now called out in §8.6 itself.
>
> Its substantive claims were verified against the live PDI and AAP: the `problem.state` read-only
> evidence, every job template id, and the catalog item's sys_id and step-based fulfilment group all
> check out exactly.

---

## 4. Rotate an event stream token

**Which of these you are doing depends on the choice made in
[03 §2.9](03-aap-eda-setup.md).** Under **one token per team** (the default) rotation is per team and
touches nobody else — that is most of the reason to prefer it. Under a **single shared token** every
team rotates at once, in lockstep.

> 🔴 **Shared-token rotation is an all-teams operation with a live failure window.** You are changing
> one value in two places, and between those two saves **every** team's events are rejected with
> `403`. Do the two edits back to back, out of hours if that matters, and re-test one team
> immediately ([07 §2](07-end-to-end-test.md)). There is no way to stage it per team — that is the
> cost the object-count saving buys you ([design decisions §1.5](design-decisions.md#15-tokens-one-per-stream-by-default-or-one-shared--a-real-choice)).

Per-team rotation, the default:

1. Generate a new token:

   ```bash
   openssl rand -hex 32
   ```

2. **AAP** — update that team's **Event Stream credential** with the new value.
3. **ServiceNow** — update that team's **API Key credential** with the same value, **bare**.
4. If you keep it in the Keychain, update the item. The `-U` flag updates in place:

   ```bash
   security add-generic-password -a "$USER" -s sandbox-eda-team-c -w -U
   ```

> ⚠️ **There is a brief window where the two sides disagree** and events are rejected with `403`.
> Change AAP and ServiceNow back to back, and re-test with [07 §2](07-end-to-end-test.md).

> ℹ️ **Nothing else needs touching.** The route row holds the UUID, not the token, so it is
> unaffected. No restart, no re-publish.

---

## 5. Verify mechanically before you test by hand

```bash
cd /path/to/Ansible_EDA_Test
export AAP_GATEWAY="https://<your-aap-host>"
python3 scripts/verify_team.py --team team-c
```

It is **read-only** — GETs only, no writes to AAP, ServiceNow or Git — and exits non-zero if any
check fails. Checks span three layers:

| Layer | What it checks |
|---|---|
| Repo | The rulebook exists and parses; **no other team's name is left in it**; the condition tests the right stream; `run_job_template.name` and `organization` are correct |
| AAP | Organization, controller project and whether it synced, job template; **Playbook is `servicenow_incident_handler.yml`**; **Prompt on launch is on**; the stream exists, does **not** forward `Authorization`, and has forwarding on; the activation is running on the right rulebook |
| ServiceNow | The assignment group exists and is active; the route row exists and is active; it names the right stream; it has a connection alias; the alias has a child connection; **exactly one active row is keyed on that group, and it is the row just checked** |

> 🎯 **The check nothing else can do:** it compares the `event_stream_uuid` in the ServiceNow route
> row against the **real UUID of the AAP stream**. Both sides look correct on their own screen and
> only disagree when compared — and a wrong UUID posts your records at another team's stream, or at
> nothing, while ServiceNow still reports a cheerful `2xx`. No amount of careful clicking finds that.

**Environment it needs:** `SANDBOX_AAP_PAT_TOKEN`, `SN_PDI_HOST`, `SN_PDI_USERNAME`,
`SN_PDI_PASSWORD`, plus `AAP_GATEWAY` or `--gateway`. Use `--route-table` if your scope prefix
differs, and `--json` for machine-readable output.

> ℹ️ **The check total is not a fixed number.** It scales with how many record types that team's
> rulebook handles, and deliberately reports a team's intentional gaps as **skipped** rather than
> failed — Team C has no SCTASK handler on purpose.

> ✅ **Fixed 2026-10-07.** The script finds a team's row by `team_code` — the only stable handle it
> has — but that is **not** how routing works, so it now re-runs the flow's own query
> (`assignment_group=<the group>^active=true`) and checks two more things:
>
> | Check | What it catches |
> |---|---|
> | *exactly one active route row keyed on group "Team-X"* | **Zero** rows: nothing assigned to that group can route, even though the `team_code` row looks perfect. **Two or more**: the flow returns only the first and which one is effectively arbitrary — the case [04 §4.1](04-servicenow-app.md) forbids and nothing previously tested |
> | *the row routing actually selects is the row checked above* | A row exists for this `team_code` **and** a different row wins the real lookup, so every check above it describes a row the flow will never use |
>
> Both were proven with a negative control that stubs the ServiceNow client and asserts they stay
> silent when the data is healthy and fire in each broken shape — including the subtle one where the
> count is right but the winning row is the wrong one.
>
> ℹ️ **`provision_team.py` does not share this defect.** It writes both `team_code` and
> `assignment_group`, and uses `team_code` only as a find-or-insert key, which is a legitimately
> different question from routing. It *can* still create a second active row for a group another team
> already serves — which is exactly what the first check above now catches.

> 🔴 **A clean run does not mean the team works.** It means nothing is misconfigured in a way a
> machine can see. The hand test in §2.6 is still required.

---

## Checkpoint — after adding a team

- [ ] The new rulebook parses, and a `grep` for the copied team's name returns nothing
- [ ] The rulebook is pushed to the remote **before** the EDA project is created
- [ ] The job template's name matches `run_job_template.name` character for character
- [ ] The job template runs `servicenow_incident_handler.yml`, with **Prompt on launch** ticked
- [ ] The activation is **Running** on the right rulebook, using `pg_listener`
- [ ] The token is 64 characters, stored bare on both sides
- [ ] The route row names the right group, stream and UUID, and is active
- [ ] `verify_team.py` exits zero
- [ ] The hand test passes, **and the other teams' counters did not move**

---

## Self-check

**Did I skip any prerequisite steps?** No. The ordering constraints that cause silent failures are
stated where they bite: the rulebook must be pushed before the EDA project exists (§2.2), and every
job template must exist before the project syncs (§3).

**Is every command copy-paste ready with context?** Yes. Each shows its working directory, and the
two verification commands in §2.2 state that **silence is the pass** — which is not obvious, since a
command printing nothing usually reads as a command that did not run.

**Would a complete novice understand every single sentence?** The subtlest point is why a wrong rule
name in §2.2 is dangerous even though nothing breaks: it corrupts the evidence the isolation test
relies on, so the test passes while telling you about the wrong team. That is spelled out rather than
left as "keep names tidy".
