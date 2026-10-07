# 05 — The Action: build the payload, POST it, read the result

**This document covers building the one shared Workflow Studio action that turns a ServiceNow record
into a JSON message and posts it to a team's event stream.**

> **Previous stage:** [04 — The ServiceNow app](04-servicenow-app.md) · **Next stage:**
> [06 — The Flow](06-servicenow-flow.md)
>
> **Time:** about an hour for your first record type.

> **Any unfamiliar word?** Every term and acronym used in these guides is defined in the
> [Glossary](glossary.md) — including AAP, EDA, PDI, SCTASK, data pill, dot-walk, work note
> and `extra_vars`.

---

## 0. Before you click anything

### Words you'll need

| Term | What it means here |
|---|---|
| **Action** | A reusable sequence of steps in Workflow Studio. A flow calls it like a function |
| **Step** | One unit inside an action. Here: a script, an HTTP call, then another script |
| **Action input** | A value the *flow* passes **into** the action |
| **Step variable** | A value one *step* inside the action can read. **Separate from an action input** — see below |
| **Data pill** | A small rounded token representing a value from an earlier step, which you drag into a later field |
| **Payload** | The JSON message sent to AAP |
| **REST step** | A step that makes an HTTP request |
| **Publish** | Making your edits live. **Saving is not enough** — see §8 |

### The one concept that causes most silent failures

**Action inputs and step variables are two separate layers, and you must wire both.**

An action input is *not* automatically visible to `inputs.*` inside a script step. For a step to see
a value, two independent things must be true:

1. The step **declares its own variable** with a name.
2. The action's **pill is mapped into** that variable.

Miss either one and the value is `undefined` — with **no error at all**. Reading a missing property
is legal JavaScript, so nothing complains, and `'use strict'` does not help.

> 🔴 **Names are case-sensitive, and there is no warning on a mismatch.** Two real failures from
> exactly this:
> - Step 3 declared `StatusCode` and `ResponseBody` while the script read `inputs.status_code` and
>   `inputs.response_body`. Result: `success = false` and the error text `HTTP :` on a genuine
>   HTTP 200.
> - Step 1 never declared `team_code` at all, so every payload shipped with an empty `target_team`.
>
> **How to recognise this class of bug:** an error message with empty gaps where a value should be
> (`HTTP :`), or an output that is blank while its source input is visibly populated in the execution
> details. That is a name mismatch, not an endpoint problem. Stop checking the network.

---

## 1. Create the action

**All → Process Automation → Flow Designer** (or Workflow Studio) **→ New → Action**

> 🔴 **Scope check first.** Set the Workflow Studio application to your scoped app, not Global. See
> [04 §1](04-servicenow-app.md).

> ℹ️ **Build one action, not one per team.** Team-specific values arrive as the four inputs below.
> That is exactly what lets a single action serve every team.

Name it for its record type — this repo's three are `Send Incident to Ansible EDA`,
`Send SCTASK to Ansible EDA`, and `Send Problem to Ansible EDA`. Build **one record type first**, end
to end, before adding another.

### The four action inputs

| Label | Name | Type | Mandatory |
|---|---|---|---|
| Incident Record | `incident_record` | Reference → Incident | false |
| Team Code | `team_code` | String | false |
| Event Stream UUID | `event_stream_uuid` | String | false |
| Connection Alias | `connection_alias` | Connection & Credential Aliases | false |

The last three exist so the flow picks the team **at run time**. Without them you would need one
action per team.

![All four action inputs](images/72-sn-action-inputs-four.png)

> ℹ️ **For the other record types**, the first input changes to `catalog_task_record`
> (Reference → Catalog Task) or `problem_record` (Reference → Problem). The other three are
> identical.

---

## 2. What the three steps do

| # | Step name | Type | Job |
|---|---|---|---|
| 1 | `Build EDA Payload` | Script | Read the record, flatten it to a JSON string, output it as `payload` |
| 2 | `POST to Ansible EDA` | REST | POST that payload to the team's event stream |
| 3 | `Process Response` | Script | Turn the HTTP result into a clean `success` and `error_message` |

There is no script on step 2. It is configured entirely in the user interface.

---

## 3. Step 1 — `Build EDA Payload` (Script)

### 3.1 Declare the variables first

Declare these **before** pasting the script. A script that assigns to an **undeclared output is
silently dropped**, and nothing warns you.

For the Incident action:

| Direction | Variable name | Type |
|---|---|---|
| Input | `Incident_record` | String |
| Input | `team_code` | String |
| Output | `payload` | String |
| Output | `is_valid` | True/False |
| Output | `incident_number` | String |
| Output | `error_message` | String |

> ⚠️ **`Incident_record` has a capital I**, while the *action* input in §1 is lowercase
> `incident_record`. That is a historical inconsistency in this build, not a rule. The script accepts
> either spelling defensively, but **the declaration must match what is actually there.** The SCTASK
> and Problem actions use lowercase `catalog_task_record` and `problem_record`.

For the other two record types, the equivalents are in
[`docs/scripts/README.md` §3](scripts/README.md) — it lists every declared input and output name per
step, which is the detail this layer gets wrong most often.

![Script step output variables, which must be declared](images/51-sn-script-step-outputs.png)

### 3.2 Map the record pill — bare

Drag the record pill itself into the input. **Do not dot-walk it to `➛ Number`.**

> 🔴 **Why this one is nasty.** Step 1's input is typed **String**, so a dot-walk to Number is
> type-compatible and ServiceNow accepts it happily. Then `GlideRecord.get()` treats the ticket
> number as a sys_id and you get:
>
> ```
> Problem not found: PRB0040012
> ```
>
> The error names a record that plainly exists, which is why this costs time.

### 3.3 Paste the script

**Paste from the canonical file, not from this page or the README:**

- Incident — [`docs/scripts/incident_step1_build_payload.js`](scripts/incident_step1_build_payload.js)
- SCTASK — [`docs/scripts/sctask_step1_build_payload.js`](scripts/sctask_step1_build_payload.js)
- Problem — [`docs/scripts/problem_step1_build_payload.js`](scripts/problem_step1_build_payload.js)

> 🔴 **Never copy JavaScript out of rendered Markdown.** It converts straight quotes (`'`) to curly
> ones (`’`), which leaves an unterminated string. The error you get is `')' expected`, which reads
> like a logic bug rather than a paste bug. All six canonical files are verified pure ASCII.

Paste the **whole file**, including the `(function execute(inputs, outputs) {` wrapper and the
`})(inputs, outputs);` at the end.

> ⚠️ **Do not use the inline script in the old `README.md` Part 3.2.** It is superseded. It emits the
> flat `event_type` value `incident_created`, while every live rulebook matches
> `servicenow.incident.created` — so an action built from it can never fire any rule. It also omits
> the `team_code` input and declares a `success` output the real script does not have.

---

## 4. Step 2 — `POST to Ansible EDA` (REST)

| Field | Value |
|---|---|
| Connection | **Use Connection Alias** |
| Connection Alias | the **`Connection Alias` action-input pill** — not a fixed alias |
| Base URL | leave empty — it comes from the connection record |
| Build Request | `Manually` |
| Resource path | see §4.1 |
| HTTP method | `POST` |
| Header | `Content-Type: application/json` |
| Request type | `Text` |
| Request body | the `payload` pill from step 1 |
| **If this step fails** | **`Don't stop the action and go to the next step`** |

> 🔴 **"If this step fails" must be set to "don't stop".** It is what lets step 3 run after a failed
> POST, read the status code, and report `success = false`. Leave it on the default and a non-2xx
> response aborts the whole action — so the flow's success check never evaluates and the record gets
> **no work note explaining why.** You end up with a silent failure instead of a diagnosed one.

### 4.1 Building the resource path

Type the literal text, drag the pill in, then type the rest:

1. Type `eda-event-streams/api/eda/v1/external_event_stream/`
2. Drag the **`Event Stream UUID`** pill in
3. Type `/post/`

The finished field reads as the prefix, then a pill, then the suffix. For a team whose route row
holds `1a2b3c4d-5e6f-7890-abcd-ef1234567890`, it resolves at run time to:

```
eda-event-streams/api/eda/v1/external_event_stream/1a2b3c4d-5e6f-7890-abcd-ef1234567890/post/
```

> ⚠️ **No leading slash.** The base URL from the connection record supplies it. A leading slash gives
> you a double slash and a `404`.

> 🔴 **Feed the Connection Alias the bare reference pill.** Do not dot-walk it to `➛ Sys ID`. The
> dot-walked form fails at run time with `Unable to load connection with alias ID:` followed by the
> alias's *scoped name* — which reads as though the connection record is missing and sends you
> auditing alias records that are fine.

> ⚠️ **Do not add an `Authorization` header by hand.** The alias supplies it. Adding your own sends
> two, and the request is rejected.

**Both team-specific values are pills, and that is the whole trick.** Hardcoding either the alias or
the UUID would tie this action to one team.

![REST step using the connection alias](images/52-sn-rest-step.png)

> ℹ️ **About that screenshot:** it is an older single-team capture, so it shows a fixed alias and a
> literal UUID typed into the resource path. Yours should show the **`Connection Alias` pill** and
> the **`Event Stream UUID` pill** instead.

---

## 5. Step 3 — `Process Response` (Script)

### 5.1 Declare the variables

**Three inputs, all lowercase:**

| Variable name | Mapped from |
|---|---|
| `status_code` | Step 2 → Status Code |
| `response_body` | Step 2 → Response Body |
| `rest_error_message` | Step 2 → Error Message |

**Four outputs:** `success`, `http_status`, `response_body`, `error_message`.

> ⚠️ **No `payload` output on this step.** The action's `payload` output must come from **step 1**,
> which is the only step that assigns it.

> ℹ️ **SCTASK and Problem take a fourth input** — `sctask_number` or `problem_number` — which gets
> prefixed onto `error_message`. A bare `HTTP 401` in the system log, across three record types and
> three teams, is nearly useless; the record number is what makes it diagnosable.

### 5.2 Paste the script

- Incident — [`docs/scripts/incident_step3_process_response.js`](scripts/incident_step3_process_response.js)
- SCTASK — [`docs/scripts/sctask_step3_process_response.js`](scripts/sctask_step3_process_response.js)
- Problem — [`docs/scripts/problem_step3_process_response.js`](scripts/problem_step3_process_response.js)

> ⚠️ **If your step still declares CamelCase variables** — `StatusCode`, `ResponseBody`,
> `ErrorMessage`, `PayloadSuccess`, `PayloadErrorMessage`, `Payload` — it predates the current
> script. The current script reads `undefined` from all of them and reports `success = false` with
> the error text `HTTP :` even on a real HTTP 200. **Rename the variables; do not rename the
> script.**

![Process Response output variables](images/53-sn-result-script-outputs.png)

---

## 6. Map the action's own outputs

Map these from the step pills:

| Action output | Comes from |
|---|---|
| `payload` | **Step 1** — the only step that assigns it |
| `success` | Step 3 |
| `http_status` | Step 3 |
| `error_message` | Step 3 |
| `incident_number` | Step 1 |

![Action outputs mapped from step pills](images/77-sn-action-outputs.png)

---

## 7. The payload contract — four reserved keys

These four keys are not ServiceNow fields. They exist so a rulebook can decide **whether to act**
before the playbook ever sees the payload. The scripts set them; you do not type them anywhere.

| Key | Value the scripts actually send | Why it exists |
|---|---|---|
| `event_type` | `servicenow.incident.created` / `.sctask.created` / `.problem.created` | The string a rule's `condition` matches on |
| `event_version` | the **string** `"1.0"` | Lets a rulebook pin its condition to a known payload shape |
| `source` | a scoped system property, falling back to the instance name — see below | Distinguishes a dev-origin send from a production one |
| `target_team` | the `team_code` input, e.g. `team-a` | Tells apart two teams' events on a stream they share |

> 🔴 **All four are required.** An older note in `README.md` Part 4 exempts "the single-team
> reference script" from sending all four. **That exemption no longer applies** — it expires as soon
> as a second activation is attached to a stream, and this build has three teams with three
> activations.

> ⚠️ **`event_version` is a string, not an integer.** All three canonical scripts set
> `var EVENT_VERSION = '1.0';`. The old README described it as "Integer, currently always `1`", which
> is wrong. The rulebooks pass it through with `| default('')`, so they do not care about the type —
> but do not "correct" the script to match the old prose.

### 7.1 🔴 The payload must be flat

**Whatever JSON you POST becomes `event.payload` verbatim.** There is no unwrapping step. So a
rulebook condition reading `event.payload.event_type` requires `event_type` to be a **top-level key**
of the body you sent.

Correct — flat:

```json
{
  "event_type": "servicenow.incident.created",
  "incident_number": "INC0010001",
  "short_description": "Disk space low"
}
```

Wrong — nested under `extra_vars`:

```json
{
  "extra_vars": {
    "event_type": "servicenow.incident.created",
    "incident_number": "INC0010001"
  }
}
```

With the second shape every field lands one level too deep, at
`event.payload.extra_vars.event_type`. The condition reading `event.payload.event_type` finds
nothing, is never true, and **the event is silently discarded.**

> ⚠️ **Why anyone would send the nested form.** `{"extra_vars": {...}}` is the body shape for
> launching an AAP **job template** directly over its REST API — a different integration pattern
> entirely. Carry that habit into an event stream and you get a `200`, a moving stream counter, and
> no automation. The symptom is identical to a wrong `event_type`:
>
> ```
> Event { ... } didn't match any rule and has been immediately discarded
> ```

The canonical scripts build a flat payload, so this is only a trap when you hand-write a test body —
as [07 §2](07-end-to-end-test.md) has you do — or when porting a payload from a direct-launch
integration.

> ℹ️ **The rulebook's own `job_args.extra_vars` block is unrelated and stays.** That is the
> *outgoing* contract between the rulebook and the AAP controller. It has nothing to do with the
> *incoming* ServiceNow payload shape.

### 7.2 Set the reserved keys last

The SCTASK script loops over every catalog variable on the request and copies each into the payload.
A catalog variable can be named anything — including `event_type` or `sys_id`.

So the four reserved keys are assigned **after** that loop, deliberately. The canonical script says
so in both places — before the loop:

```javascript
// Catalog variables first, so the reserved keys below always win. There is no
// GlobalWorkflowHelper on this instance, so read the variable pool directly.
```

and after it:

```javascript
// Reserved routing keys. Set after the variable loop so a catalog variable
// called event_type or sys_id cannot overwrite them.
payload.event_type = EVENT_TYPE;
payload.event_version = EVENT_VERSION;
payload.source = sourceId;
payload.target_team = cleanFieldValue(inputs.team_code);
```

> 🔴 **If you reorder this, a catalog variable can silently overwrite a routing key.** A request with
> a variable called `event_type` would then set the event's own type, and the rule would never match.
> Assign reserved keys last in any payload builder that loops over user-supplied data.

### 7.3 The `source` key and its optional property

The scripts do **not** hardcode `source`. They read it like this:

```javascript
var sourceId = gs.getProperty('x_661661_james_tes.eda.source_id', '');
if (!sourceId) {
    sourceId = gs.getProperty('instance_name', 'unknown');
}
```

**Verified on this PDI, 2026-10-06:** the property `x_661661_james_tes.eda.source_id` **does not
exist**, so the fallback is in use and every payload currently sends:

```json
"source": "dev211593"
```

That is the instance name. It works, and nothing is broken.

**Creating the property is optional.** Do it if you want a stable, meaningful value — for example
`pdi` for a sandbox and `prod` for production — so a rulebook can tell a test event from a real one
even after an instance is renamed or rebuilt.

> 🔴 **The canonical scripts hardcode *this repository's* scope**, `x_661661_james_tes`. Your scope
> will be different ([04 §1](04-servicenow-app.md) — ServiceNow generates it and you cannot change
> it). So creating the property alone is not enough: you must also edit the script.
>
> **Do not type `x_661661_james_tes` into the property name.** ServiceNow auto-prepends your own
> scope to property names, so you would end up with `<your-scope>.x_661661_james_tes.eda.source_id`,
> which nothing reads. The symptom is silence — the fallback keeps working and nothing looks wrong.

Two steps, both required:

1. **Create the property.** Go to **All → System Properties → All Properties → New**, with your
   scoped app selected in the application picker.

   | Field | Value |
   |---|---|
   | Name | `eda.source_id` — your scope is prepended automatically |
   | Type | string |
   | Value | `pdi` |

2. **Change the one line in each step-1 script** that names the scope. It is one line per file, at
   these line numbers (verified 2026-10-07) — or find it with
   `grep -n "eda.source_id" docs/scripts/*.js`:

   | File | Line |
   |---|---|
   | `incident_step1_build_payload.js` | 73 |
   | `problem_step1_build_payload.js` | 82 |
   | `sctask_step1_build_payload.js` | **106** |

   ```javascript
   var sourceId = gs.getProperty('x_661661_james_tes.eda.source_id', '');
   ```

   Replace `x_661661_james_tes` with your own scope prefix, then re-paste and publish.

> ✅ **Verify:** in **All → Scripts - Background**, with your scoped app selected, run
> `gs.info(gs.getProperty('<your-scope>.eda.source_id', 'NOT SET'));`
>
> Expected output: `pdi`. If it prints `NOT SET`, the property name is wrong — most likely it has a
> doubled scope prefix.

> ⚠️ **The old `README.md` Part 4 shows `payload.source = 'pdi';` as a hardcoded assignment.** That
> is not what the live scripts do, and the property it actually reads is not mentioned there at all.

### 7.4 Why the stream name is the stronger check

The team rulebooks test **two** things, and the order matters:

```yaml
condition: >-
  event.meta.eda_event_stream_name == "sn-team-a" and
  event.payload.event_type == "servicenow.incident.created"
```

`event.meta.eda_event_stream_name` is injected by AAP itself, not by the sender, so **it cannot be
forged** — that makes it the primary tenant check. `event_type` then selects which automation family
the event belongs to.

> 🔴 **If you ever change the `event_type` string a script sends, search every rulebook for the old
> string before you ship it.** Nothing enforces the format — `event_type` is just a string and `==`
> is a literal comparison. Mix the forms and the condition is simply never true again, with no
> warning. The activation log shows the identical discard message it shows for a malformed payload:
>
> ```
> Event { ... } didn't match any rule and has been immediately discarded
> ```

---

## 8. Save, then Publish

**Save → Publish.** A flow runs the **last published** version of an action.

> 🔴 **If you only Save, your change has no effect** and you will re-test the old behaviour,
> conclude the fix did not work, and go looking for a second bug that does not exist.

> ✅ **Verify:** the action's status reads **Published**, not Draft.

---

## 9. A note on script mode

The canonical scripts are **ES5** — they use `var`, with no arrow functions and no template literals.

Since the **Xanadu** release, ServiceNow enables **ES2021 (ES12)** mode by default for newly created
scripts, regardless of the application's JavaScript mode. **ES5 runs correctly either way**, so this
is not a blocker. One consequence worth knowing: `'use strict'` only actually enforces anything in
ES12 mode.

> ⚠️ **The per-script ES12 toggle is lost on XML export and in update sets.** If you promote this
> app to another instance, set the script mode at the **application** level rather than per script.

---

## Checkpoint

- [ ] The action shows **four** inputs
- [ ] Step 1 declares its record input with the **exact** name and case that is actually there
- [ ] Step 1 declares `team_code`, and the pill is mapped into it
- [ ] The record pill is mapped **bare**, not dot-walked to Number
- [ ] Step 2's **If this step fails** is set to "don't stop"
- [ ] Step 2's Connection Alias is the **bare pill**; no hand-added `Authorization` header
- [ ] Step 2's resource path has no leading slash
- [ ] Step 3 declares three **lowercase** inputs and four outputs
- [ ] The action's `payload` output is mapped from **step 1**
- [ ] Status reads **Published**, not Draft

**Next:** [06 — The Flow](06-servicenow-flow.md).

---

## Self-check

**Did I skip any prerequisite steps?** No — and one that the old documentation did skip is now
covered: the `source` system property in [§7.3](#73-the-source-key-and-its-optional-property), which
the canonical script reads and the README never mentioned.

**Is every command copy-paste ready with context?** Yes. The only code here is the `gs.getProperty`
excerpt, shown to explain where `source` comes from rather than to be run, and it is labelled as
such. The scripts themselves are deliberately *not* inlined — pasting them from a rendered page is
the exact failure §3.3 warns about, so every one links to its canonical file.

**Would a complete novice understand every single sentence?** The two-layer wiring idea in §0 is the
hardest concept in this document, so it is stated before any step uses it, with both real failures it
caused. §0 defines the terms specific to this document; everything cross-cutting — including
**dot-walk**, which appears in two red warnings here — is in the [Glossary](glossary.md), linked at
the top. Pill, publish, and step-versus-action-input are the three a
beginner most often meets for the first time here.
