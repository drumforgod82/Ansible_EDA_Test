\
# Adding a record type — SCTASK and Problem

**Written for someone who has not done this before.** Every step names the exact menu path. Do the
phases in order: each needs something the previous one made.

This adds **catalog tasks (SCTASK)** and **problems** alongside incidents, for teams that already
exist. It does not add a team — for that, see
[§9 of the routing guide](servicenow-dynamic-team-routing.md#9-adding-a-team-worked-example-team-c).

---

## What you are building, and what you are not

**Nothing about routing changes.** An SCTASK assigned to `Team-A` resolves through the *same*
`EDA Team Route` row as a Team-A incident — same stream, same alias, same UUID. The route table is
keyed on team code, and the team has not changed. **No new route rows, no schema change.**

| | Incidents (today) | SCTASK (new) | Problem (new) |
|---|---|---|---|
| ServiceNow flow | `Trigger EDA remediation on Incident-EDA` | **new** | **new** |
| ServiceNow action | `Send Incident to Ansible EDA` | **new** | **new** |
| Enrollment table | — | **new** (catalog-item filter) | not needed |
| AAP job template | `Team X Incident Handler` | **new** per team | **new** per team |
| Playbook | `servicenow_incident_handler.yml` | **new** | **new** |
| Rulebook | existing file | **+1 rule** | **+1 rule** |
| Event stream / activation | unchanged | unchanged | unchanged |

> 🔴 **Do not edit `Trigger EDA remediation on Incident-EDA` or `Send Incident to Ansible EDA`.**
> Incidents work. A copy that breaks costs you nothing; an edit that breaks takes production
> incident handling with it.

**Why SCTASK needs an enrollment table and Problem does not.** You do not want *every* SCTASK
assigned to a team — only ones for specific catalog items. That is a second filter, and it belongs in
a ServiceNow table rather than the rulebook: enrolling an item then costs one row instead of a
rulebook edit plus a project sync plus an activation restart. Problems have no catalog item, so
assignment group is the only filter and the route table already provides it.

---

## Before you start

### Decide two things

1. **Items only, or also order guides?** Items only is the right default — see [1.3](#13-optional--also-enrol-by-order-guide). This instance has only two active guides, so the extra column earns nothing here.
2. **One team first.** Build Team A end to end before creating Team B and C job templates. A broken pattern replicated three times is three times the unpicking.

### Take a baseline

```bash
python3 scripts/verify_team.py --team team-a
```

Note the **event stream counters** it reports. When something looks wrong in Phase 7 you will want to
know what "before" was — the counters are how you tell *"the event never arrived"* from *"it arrived
and did not match"*, and that distinction is most of the debugging.

### Values for this build, already confirmed on this instance

Everything below is verified, not assumed. Substitute your own if you are following this elsewhere.

| Thing | Value |
|---|---|
| Catalog item | **James Test** |
| — its sys_id | `81c1c517c32b8314b08b9b377d0131c3` |
| — its class | `sc_cat_item`, so it passes the reference qual in 1.2 |
| — its fulfilment | **Step based**, with a Task step assigning `Team-A` |
| Assignment group | **Team-A** — sys_id `77b8a622c3ef4bd0b08b9b377d0131fe` |
| Route row | `team-a` / `Team-A` / `sn-team-a` — **already exists, do not add one** |
| A task already on Team-A | **SCTASK0010002**, sys_id `39e50917c36b8314b08b9b377d0131e5` |
| A task on the wrong group | `SCTASK0010001`, sys_id `7d144d5fc32b8314b08b9b377d0131c1` — useful for the 5.3 action test, which does not care about the group |

> ⚠️ **`SCTASK0010002` cannot be used for the end-to-end test.** It was created *before* the flow
> existed, and the trigger is **Record Created** — it has already been and gone. Use it to confirm the
> group is right (done), then order the item again once the flow is built.

---

## Phase 1 — The enrollment table (ServiceNow)

Set the **application picker** to **James EDA Test** before you start. Everything in this phase must
be created inside the scoped app.

### 1.1 Create the table

**All → System Definition → Tables → New**

| Field | Value |
|---|---|
| Label | `EDA Enabled Catalog Items` |
| Name | *(auto-fills to* `x_661661_james_tes_eda_enabled_catalog_items` *— leave it)* |
| Extends table | **leave empty** |
| Create module | ✅ ticked, so it appears in the app menu |
| Application | `James EDA Test` |

> ⚠️ **Do not tick "Auto-number".** Rows here are configuration, not tickets.

### 1.2 Add the columns

On the table's **Columns** related list, add these three:

| Column label | Type | Reference / Max length | Notes |
|---|---|---|---|
| `Catalog item` | **Reference** | `Catalog Item [sc_cat_item]` | The item to enrol |
| `Active` | **True/False** | default **true** | Lets you disable a row without deleting it |
| `Description` | **String** | 200 | Free text — why this item is enrolled |

On the **Catalog item** column, open it and set **Reference qual → Advanced**, with:

```
sys_class_name!=sc_cat_item_guide
```

> ⚠️ **Use `!=sc_cat_item_guide`, not `=sc_cat_item`.** `sc_cat_item_guide` *extends* `sc_cat_item`,
> so a reference field can hold either. Qualifying with `=sc_cat_item` looks right but hides
> Hardware, Software and Record Producer items, which are also subclasses — you would silently be
> unable to enrol most of the catalogue.

### 1.3 Optional — also enrol by order guide

**Skip this if you only ever enrol individual items.** The single `Catalog item` column above already
covers every individual item, including Hardware, Software and Record Producer subclasses.

Add this only if you want *"anything ordered through guide X is eligible"* as well. It is a second,
independent way in — a task passes the gate if **either** its item is enrolled **or** its order guide
is.

Add one more column:

| Column label | Type | Reference | Reference qual |
|---|---|---|---|
| `Order guide` | Reference | `Order Guide [sc_cat_item_guide]` | *(none needed)* |

A row then uses **one or the other**, never both: either name an item, or name a guide.

**The two columns match different source fields, and this is the part that goes wrong:**

| Enrol by | Compare the row's column against |
|---|---|
| `Catalog item` | `Trigger → Catalog Task Record → Item` |
| `Order guide` | `Trigger → Catalog Task Record → Request item → Order Guide` |

> 🔴 **A guide can never be matched against the item field.** `cat_item` always holds the *individual*
> item — even for a guide-ordered task — and guide identity lives only in `sc_req_item.order_guide`.
> An earlier production implementation wrote the condition as `Item → Name is <guide name>`, which compares
> `cat_item.name` to a guide name, returns zero records, and meant **EDA never fired for
> guide-ordered items at all** — silently, for months. Match `order_guide`, never `cat_item`.

If you add this column, the gate in **6.2** becomes two condition sets OR'd together:

```
( Catalog item  is  Trigger → Catalog Task Record → Item
  AND Catalog item is not empty )
OR
( Order guide   is  Trigger → Catalog Task Record → Request item → Order Guide
  AND Order guide is not empty )
```

> 🔴 **Each set needs its own `is not empty` guard, and this is the trap that fails *open*.** A task
> not ordered through a guide resolves the guide pill to empty. Without the guard that set generates
> `order_guide=`, which matches **every row whose Order guide is empty** — that is, all of your item
> rows. Result: every catalog task passes the gate. The guard makes the set self-contradictory when
> the pill is empty (`order_guide ISNOTEMPTY ^ order_guide=` matches nothing), which is exactly what
> you want. The mirror guard applies to the item set.

> ⚠️ **This is also why you must not use For Each.** An item enrolled *both* directly and via a guide
> matches two rows, and iterating would launch two AAP jobs for one task. `Count > 0` is
> duplicate-proof.

Your PDI has only two active order guides (`Request Developer Project Equipment`, `New Hire`), so this
is low value here — but the mechanism is what a real catalogue needs, and one guide row beats
maintaining a list of its members.

> ⚠️ **Governance note if you do use guides:** guide membership is owned by the catalog team, so their
> additions silently expand what your automation fires on. There is no technical control for that —
> review the guide's contents periodically instead.

### 1.4 Turn off update-set syncing

**All → System Definition → Tables →** open your table **→** right-click the header **→ Configure →
Table**. Find **Update synch** and make sure it is **unticked**.

> ⚠️ **`update_synch = true` is a trap.** It drags row changes into update sets, so enrolling an item
> becomes a code promotion instead of a data change — which defeats the entire reason for having this
> table.

### 1.5 Seed one row for testing

Open the new module (**James EDA Test → EDA Enabled Catalog Items → New**) and create one row:

| Field | Value |
|---|---|
| Catalog item | pick any active item — e.g. **Standard Laptop** |
| Active | ✅ true |
| Description | `Test enrolment for EDA SCTASK routing` |

Write down the item name — you will set it on the test task in Phase 7.

> ✅ **Verify:** the list shows one row, the Catalog item reference resolves to a real item name, and
> Active is true. Then open the **Catalog item** field's magnifier and confirm you can see Hardware
> and Software items in the picker — if you can only see a handful, your reference qual is wrong.

---

## Phase 2 — The playbooks (Git)

An SCTASK is not an incident: different table, different close semantics. The incident playbook
closes with `close_code` / `close_notes`; a catalog task closes by setting **state 3, Closed
Complete**.

Create `servicenow_sctask_handler.yml` in the repo root, modelled on
`servicenow_incident_handler.yml`. The differences that matter:

| | Incident | SCTASK |
|---|---|---|
| Table | `/api/now/table/incident/{sys_id}` | `/api/now/table/sc_task/{sys_id}` |
| Close | `close_code` + `close_notes` | `state: 3` (Closed Complete) + `close_notes` |
| Gate variable | `sn_close_incident` | `sn_close_task` |

Reference — the `sc_task` state values on your instance:

```
1   Open              2   Work in Progress    3   Closed Complete
4   Closed Incomplete 7   Closed Skipped     -5   Pending
```

Do the same for `servicenow_problem_handler.yml` when you get to Phase 8.

> ⚠️ **Keep `| default('')` on every mapped variable**, exactly as the incident playbook does. One
> missing key fails the whole action with `Object of type StrictUndefined is not JSON serializable`
> and launches nothing.

**Commit and push.** The EDA project can only offer a rulebook the remote already has, and the
controller project can only offer a playbook it has synced.

> ✅ **Verify:** `python3 -c "import yaml;yaml.safe_load(open('servicenow_sctask_handler.yml'))"`
> exits silently, and the file is on your branch on GitHub.

---

## Phase 3 — Job templates (AAP)

One per record type **per team**. Start with Team A only; repeat once it works.

**Automation Execution → Templates → Create template → Create job template**

| Field | Value |
|---|---|
| Name | `Team A SCTASK Handler` |
| Job type | Run |
| Organization | `Team A` |
| Inventory | `Team A Inventory` |
| Project | `EDA ServiceNow - Team A` |
| **Playbook** | **`servicenow_sctask_handler.yml`** |
| Credentials | `ServiceNow PDI - Team A` |
| **Variables → Prompt on launch** | ✅ **REQUIRED** |

First **sync the controller project** (`EDA ServiceNow - Team A` → **Sync**) or the new playbook will
not appear in the dropdown.

> 🔴 **Pick the playbook, not a rulebook.** The dropdown lists everything in the repo, including
> `rulebooks/team_a_rulebook.yml`. Choosing a rulebook fails at event time with
> `ERROR! 'sources' is not a valid attribute for a Play`, which sends you debugging the rulebook
> instead of this field.

> ✅ **Verify:** reopen the template. **Prompt on launch** ticked, **Playbook** is
> `servicenow_sctask_handler.yml`, and the name matches character-for-character what you will put in
> the rulebook in Phase 4.

---

## Phase 4 — Add a rule to the team's rulebook (Git + AAP)

Edit `rulebooks/team_a_rulebook.yml` and add a **second rule** alongside the existing one. Do not
create a second rulebook file: one activation runs one rulebook, and a second activation on the same
stream would receive **every** event twice because stream delivery is fan-out.

```yaml
    - name: Launch Team A SCTASK handler
      condition: >-
        event.meta.eda_event_stream_name == "sn-team-a" and
        event.payload.event_type == "servicenow.sctask.created"
      action:
        run_job_template:
          name: "Team A SCTASK Handler"
          organization: "Team A"
          job_args:
            extra_vars:
              task_number: "{{ event.payload.task_number | default('') }}"
              short_description: "{{ event.payload.short_description | default('') }}"
              sys_id: "{{ event.payload.sys_id | default('') }}"
              catalog_item: "{{ event.payload.catalog_item | default('') }}"
              assignment_group: "{{ event.payload.assignment_group | default('') }}"
              event_version: "{{ event.payload.event_version | default('') }}"
              source: "{{ event.payload.source | default('') }}"
              target_team: "{{ event.payload.target_team | default('') }}"
              source_stream: "{{ event.meta.eda_event_stream_name | default('') }}"
              sn_close_task: true
```

**Both rules test the stream name** — that stays your tenant proof, and it is platform-injected so it
cannot be forged. `event_type` only has to distinguish *record type*, and your own flow is the only
thing that sets it.

> 🔴 **Condition on an explicit `event_type` value. Never on "this field exists".** Presence-matching
> works with one record type and silently starts cross-matching the moment a second one shares the
> stream — an SCTASK would fire the incident rule as well.

**Commit and push**, then in AAP:

1. **Automation Decisions → Projects →** `Ansible EDA Test - Team A` **→ Sync**
2. **Automation Decisions → Rulebook Activations →** `team-a-incidents` **→** gear icon **→
   re-attach** the `sn-team-a` event stream mapping
3. **Restart** the activation

> ⚠️ **Step 2 is not optional.** The source mapping is pinned to a SHA256 of the rulebook file. Any
> edit changes it, and skipping the re-attach fails with *"Rulebook has changed since the sources were
> mapped."* Even a whitespace-only change invalidates it.

> ✅ **Verify:** `python3 scripts/verify_team.py --team team-a` reports **29/29**, including
> *"source mapping matches the synced rulebook (not stale)"*. The activation shows **Running** and its
> log ends with `Waiting for events`.

---

## Phase 5 — The SCTASK action (ServiceNow)

Application picker on **James EDA Test**.

### 5.1 Copy the working action

**All → Process Automation → Workflow Studio →** find **`Send Incident to Ansible EDA`** **→** the
**⋯** menu **→ Copy**. Name the copy **`Send SCTASK to Ansible EDA`**.

Copying gets you the REST step and the response handler already wired, which are the fiddly parts.
You will only replace the first step's script.

### 5.2 Action inputs

The copy inherits four inputs. Rename the record one so it reads correctly, and keep the rest —
they are what make one REST step serve every team:

| Input | Type | Notes |
|---|---|---|
| `Catalog Task Record` | Reference → `Catalog Task [sc_task]` | was `Incident Record` |
| `Team Code` | String | |
| `Event Stream UUID` | String | |
| `Connection Alias` | Reference → Connection & Credential Aliases | |

### 5.3 Replace the payload-builder script

Open **step 1** and paste your SCTASK script. It must satisfy the same contract the incident one
does, or the later steps have nothing to send:

| Must set | Why |
|---|---|
| `outputs.payload` | JSON string — the REST step's body |
| `outputs.is_valid` | `true` on success |
| `outputs.error_message` | populated on failure |
| `payload.event_type` | **exactly** `servicenow.sctask.created` — must match the rulebook |
| `payload.event_version`, `payload.source`, `payload.target_team` | the reserved routing keys |
| `payload.sys_id`, `payload.task_number` | the playbook needs these to write back |

`target_team` comes from the **`team_code`** action input — declare that input *and* map its pill, or
every payload ships `target_team` empty with no error at all.

> 🔴 **Step input names are case-sensitive, and declaring a variable is separate from mapping a pill
> into it.** The incident action declares `Incident_record` (capital I) while its action input is
> `incident_record`; those are *different variables*. An unmapped input is silently empty at run
> time. Make your script's guard clause list the keys of `inputs` so a mismatch is one line to
> diagnose instead of a bisection.

> ✅ **Verify:** **Test** the action with a real `sc_task` sys_id and confirm step 1 outputs a
> populated `payload` with `event_type` reading `servicenow.sctask.created`, and `target_team`
> **not** empty.

---

## Phase 6 — The SCTASK flow (ServiceNow)

**Workflow Studio → New → Flow.** Name it `Trigger EDA remediation on SCTASK`. Set
**Flow properties → Run as: System user** — a non-admin caller may be unable to read the credential,
which surfaces as an empty token rather than a permission error.

### 6.1 Trigger

| Field | Value |
|---|---|
| Trigger | **Record Created** |
| Table | `Catalog Task [sc_task]` |
| Condition | `Assignment group` **is not empty** |

Keep the trigger condition coarse. It only has to be a *superset* — the enrollment gate below is the
authoritative filter. A narrow trigger that disagrees with the table is two sources of truth.

### 6.2 Step 1 — the enrollment gate

**Add an Action → ServiceNow Core → Look Up Records**

| Field | Value |
|---|---|
| Table | `EDA Enabled Catalog Items` |
| Conditions | `Catalog item` **is** `Trigger → Catalog Task Record → Item` **AND** `Active` **is** true |

Then **Add Flow Logic → If**, with the condition:

```
1 - Look Up Records → Records → Count   greater than   0
```

Everything else in the flow goes **inside this If's true branch**. That is fail-closed: if anything
stops the If evaluating, nothing is sent.

> 🔴 **Branch on `Count`, never on `Records is empty`.** The latter compares a record-list object to
> a string, is always false, and the gate **silently never fires** — every SCTASK reaches EDA. That
> exact bug shipped in a production build.

> 🔴 **Guard the compared column.** Add `Catalog item` **is not empty** as well. A task with no
> catalog item resolves the pill to empty, generating `catalog_item=`, which matches every row whose
> catalog item is empty — so the gate passes everything. This one fails *open* and looks like it is
> working.

> ⚠️ **Do not use For Each on this lookup.** If an item is ever enrolled twice you would launch two
> AAP jobs for one task. The `Count > 0` test is duplicate-proof; iteration is not.

> ⚠️ **Keep the lookup out of the action.** It belongs here in the flow. Inside the payload builder,
> "not enrolled" becomes indistinguishable from "failed" and fires the Error Handler and its email on
> every unenrolled task.

### 6.3 Step 2 — the route lookup

Inside the true branch, **Look Up Record** (singular) on `EDA Team Route`:

| Field | Value |
|---|---|
| Conditions | `Assignment group` **is** `Trigger → Catalog Task Record → Assignment group` **AND** `Active` is true |

Tick **Don't fail on error**, then add an **If**: `EDA Team Route Record → Sys ID` **is not empty**.

> ⚠️ Gate on a **scalar field** like Sys ID, never on the Record pill itself — comparing a record
> object to Empty is a string compare and is always false.

### 6.4 Step 3 — call your action

Add **`Send SCTASK to Ansible EDA`** and map its four inputs:

| Input | Pill |
|---|---|
| Catalog Task Record | `Trigger → Catalog Task Record` |
| Team Code | `2 → EDA Team Route Record → Team code` |
| Event Stream UUID | `2 → EDA Team Route Record → Event stream UUID` |
| Connection Alias | `2 → EDA Team Route Record → Connection alias` |

> 🔴 **Feed the Connection alias the bare reference pill. Do not dot-walk to Sys ID.** A dot-walked
> or empty pill produces `Unable to load connection with alias ID:  <a href="/sys_alias.do?sys_id=">`
> — and the blank after `sys_id=` is the signature of an unresolved pill, not a bad route row.

On the action's REST step, confirm **If this step fails → "Don't stop the action and go to the next
step"**. Without it a non-2xx aborts the action and the flow goes silent.

### 6.5 Step 4 — write a work note

Optional but worth it, and it is how you will see the result without opening AAP. **Update Record**
on `Trigger → Catalog Task Record`, setting **Work notes** to a success message plus the action's
**HTTP Status** pill.

**Save**, then **Activate** the flow.

> ✅ **Verify:** the flow shows **Activated**, and `Run as` reads **System user**.

---

## Phase 7 — Test

### 7.0 First, make the task land on your team

> 🔴 **The assignment group on a catalog task comes from fulfilment configuration, not from you.**
> This is the single most surprising thing about wiring SCTASKs, and it is worth understanding before
> you test rather than after.
>
> Ordering `James Test` produced `REQ0010001 → RITM0010001 → SCTASK0010001` correctly — but the task
> was assigned to **`Procurement`**. At that point the item was still on the legacy
> `Service Catalog item request` flow with its **Fulfillment group** empty, so fulfilment fell back to a
> default group. (It has since been moved to step-based fulfilment — see the table below.) Your route
> table only knows
> `Team-A/B/C`, so that task resolves **no route row** and is dropped by the gate in 6.3. The flow is
> working; the group is wrong.

**How you set the group depends on which fulfilment model the item uses**, and this is the part that
wastes time — the two models read *different* configuration and silently ignore each other's.

Open the item: **All → Service Catalog → Catalog Definitions → Maintain Items →** `James Test`, and
look at its **Fulfilment** / flow setting.

| If the item uses | Set the group here | The other field is **ignored** |
|---|---|---|
| **Step based request fulfillment** *(newer, Flow Designer)* | The item's **fulfilment steps** — add or edit a **Task** step and set its **Assigned group** to `Team-A` | `sc_cat_item.group` stays empty and does nothing |
| `Service Catalog item request` *(legacy, workflow-driven)* | The item's **Fulfillment group** field (`sc_cat_item.group`) | the step config, which does not exist |

> ⚠️ **`Fulfillment group` being empty is not evidence the group is unset.** On a step-based item that
> field is *expected* to be empty — the real value lives in `sc_service_fulfillment_task_step.assigned_group`.
> Checking the wrong one leads you to "fix" something that was never broken.

`James Test` on this instance is **step based**, with a Task step titled `Assign to Team A` whose
assigned group is `Team-A`. Every future order creates its catalog task on `Team-A`, which the existing
route row already handles — no new route row, no hand-created records.

> ⚠️ **Step-based fulfilment creates one task per configured step.** Add a second step and you get a
> second SCTASK, and **both** reach your flow, route, and launch a job. The enrollment gate cannot
> separate them — it keys on catalog item and they share one. Filter on the task's short description
> or step in the flow's trigger condition if that is not what you want.

> ⚠️ **Changing the group does not fix the task you already have.** Your flow triggers on **Record
> Created**, so editing `SCTASK0010001`'s group will not re-fire it. Order the item again to get a
> fresh task. Do not "fix" this by switching the trigger to Created-or-Updated — that would re-fire on
> every subsequent edit to the task, including the work note your own playbook writes back, which is a
> loop.

**The alternative, if you cannot change fulfilment:** add a route row for the group fulfilment
*actually* assigns (`team_code = procurement`, `assignment_group = Procurement`, pointing at whichever
team's stream should own it). That is the realistic production shape — in a real catalogue the
fulfilment groups already exist and are owned by other teams, so **your route table must be keyed on
the groups fulfilment assigns**, not on names you invent.

**You can still use `SCTASK0010001` right now** for the Phase 5.3 action test — testing the action in
isolation does not care about the assignment group:

```
sys_id = 7d144d5fc32b8314b08b9b377d0131c1
```

### 7.1 The end-to-end test — order the item

With the Fulfillment group set, order it for real. This is the better test because it exercises the
whole chain, including the trigger firing on a task *you* did not create.

**Service Portal or the Service Catalog → find `James Test` → Order Now**

That produces `REQ… → RITM… → SCTASK…`. If the RITM stops on an approval, approve it
(**All → Service Desk → My Approvals**, or open the RITM's Approvers related list and set the
approval to Approved as admin).

> ✅ **Before going further, check the new task's Assignment group reads `Team-A`.** If it still says
> `Procurement`, the Fulfillment group did not take effect — see the fallback in 7.0 rather than
> pressing on, because nothing downstream can work until the group matches a route row.

<details>
<summary>Fallback: create the task by hand</summary>

If ordering is inconvenient, **All → Catalog Task → New** (table `sc_task`) with:

| Field | Value |
|---|---|
| Assignment group | `Team-A` |
| Item | the catalog item you enrolled in 1.5 |
| Short description | `EDA SCTASK routing test` |

Save. This fires the same trigger, so every check below still applies.

</details>

### 7.2 What to check, in this order

| # | Check | Where | Expect |
|---|---|---|---|
| 1 | Flow ran | the flow's **Executions** | Enrollment If = **true**, route If = **true** |
| 2 | Action result | expand step 3 | `http_status = 200`, `success = true` |
| 3 | Event arrived | AAP → Event Streams | `sn-team-a` incremented; **`sn-team-b` and `sn-team-c` unchanged** |
| 4 | Job ran | AAP → Jobs | `Team A SCTASK Handler`, **Successful** |
| 5 | Routing correct | that job → Extra variables | `target_team: team-a`, `source_stream: sn-team-a` |
| 6 | Write-back | the task | Work note added, state **Closed Complete** |

**Then test the negative case, which matters more.** Create a second task with Assignment group
`Team-A` but an item you did **not** enrol. Expect: the flow runs, the enrollment If is **false**,
nothing is sent, and `sn-team-a` does **not** increment. If it does increment, your gate is one of
the two fail-open bugs above.

---

## Phase 8 — Problem, and the other teams

**Problem is the same shape minus Phase 1.** Problems have no catalog item, so there is no enrollment
table and no gate — the route lookup on assignment group is the only filter.

1. `servicenow_problem_handler.yml`, pushed
2. `Team A Problem Handler` job template
3. A third rule in the rulebook on `event.payload.event_type == "servicenow.problem.created"` — then
   sync, **re-attach**, restart again
4. `Send Problem to Ansible EDA` action, copied, with your Problem script
5. `Trigger EDA remediation on Problem` flow — trigger on `problem`, route lookup, action, work note
6. Test, including the isolation check

**For Teams B and C**, repeat Phases 3, 4 and 8.2–8.3 only. The flows, the actions and the enrollment
table are **shared across all teams** — that is the same property that makes adding a team cheap, and
it holds for adding a record type too.

> ✅ **Final verify:** `verify_team.py` at **29/29** for every team, and one incident, one SCTASK and
> one problem each landing on their own job template with only their own team's stream counter moving.

---

## If it does not work

| Symptom | Cause |
|---|---|
| Nothing happens at all | Trigger condition — is Assignment group empty on the task? |
| Every SCTASK reaches EDA, enrolled or not | The gate. Either `Records is empty` instead of `Count`, or the missing `is not empty` guard on Catalog item |
| Enrollment If is false for an enrolled item | The reference qual hid the item, or `Active` is false on the row |
| `Unable to load connection with alias ID:` | Connection alias pill dot-walked to Sys ID, or unresolved |
| Stream counter moves, no job | Rulebook mismatch — compare `event_type` in the script against the rulebook condition, character for character |
| `ERROR! 'sources' is not a valid attribute for a Play` | The job template's Playbook field is a rulebook |
| Job fails on undefined variables | *Prompt on launch* is off on the job template |
| `Rulebook has changed since the sources were mapped` | You skipped the re-attach in Phase 4 |
| `target_team` empty | The action's `team_code` input is declared but its pill was never mapped |
