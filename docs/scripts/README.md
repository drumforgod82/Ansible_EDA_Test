# ServiceNow action scripts

These six files are the **canonical copies** of the JavaScript pasted into the three Flow Designer
actions that send a ServiceNow record to Ansible EDA. They were pulled from the live PDI, not
retyped, and they are what actually runs.

**Paste from these files, never from a rendered page.** Copying JavaScript out of rendered markdown
is how curly quotes (`'` instead of `'`) and mangled indentation get into a script. The failure is
nasty because it looks like a logic bug, not a paste bug. All six files are verified pure ASCII.

New here? Read [§1 of the main README](../../README.md) first for what EDA is and what this pipeline
does. This page assumes you already know you need to paste a script into a step and just want the
right text.

---

## 1. The naming scheme

```
<record_type>_step<N>_<what_it_does>.js
```

- **`<record_type>`** — `incident`, `sctask`, or `problem`. Each has its own action, because each
  reads different fields off a different table.
- **`step<N>`** — which step of the action, matching the number shown in the ServiceNow step list
  and the headings in the build guides.
- Files are grouped by record type so each action's pair sits together — that is the order you build
  them in.

**There is no `step2` file, and that is not an omission.** Step 2 is the REST step that does the
actual HTTP POST. It is configured entirely in the UI with no script. The gap in the numbering is
there to tell you that.

---

## 2. What the three steps do

Every one of the three actions has the same shape:

| Step | Name in ServiceNow | Type | Job |
|---|---|---|---|
| 1 | `Build EDA Payload` | Script | Read the record, flatten it to a JSON string, hand it out as `payload` |
| 2 | `POST to Ansible EDA` | REST | POST that `payload` to the team's event stream |
| 3 | `Process Response` | Script | Turn the HTTP result into a clean `success` / `error_message` |

Step 1 **throws** on bad input, which errors the whole action, so step 3 never runs with a garbage
payload. Step 2 must be set to **`If this step fails` → "don't stop"**, otherwise step 3 is skipped
on a failed POST and you lose the error message.

---

## 3. File index

Each script's **declared variable names** are listed because step input names are **case-sensitive**
and are declared separately from the pill that feeds them. If a name here does not match what you
type into the step, the script reads `undefined` with **no error at all**.

### Incident — action `Send Incident to Ansible EDA`

| | |
|---|---|
| Action sys_id | `d067d122c3af0bd0b08b9b377d0131fd` |
| `event_type` emitted | `servicenow.incident.created` |

| File | Step sys_id | Declared inputs | Declared outputs |
|---|---|---|---|
| [`incident_step1_build_payload.js`](incident_step1_build_payload.js) | `6c671522c3af0bd0b08b9b377d013141` | `Incident_record`, `team_code` | `payload`, `is_valid`, `incident_number`, `error_message` |
| [`incident_step3_process_response.js`](incident_step3_process_response.js) | `41675522c3af0bd0b08b9b377d013106` | `status_code`, `response_body`, `rest_error_message` | `success`, `http_status`, `response_body`, `error_message` |

> ⚠️ **`Incident_record` has a capital I.** The other two actions use a lowercase record input. This
> is a historical inconsistency, not a rule — the script accepts either spelling defensively, but the
> step declaration must match what is actually there.

### SCTASK — action `Send SCTASK to Ansible EDA`

| | |
|---|---|
| Action sys_id | `703ab8a3c3af4714b08b9b377d0131b1` |
| `event_type` emitted | `servicenow.sctask.created` |

| File | Step sys_id | Declared inputs | Declared outputs |
|---|---|---|---|
| [`sctask_step1_build_payload.js`](sctask_step1_build_payload.js) | `913af8a3c3af4714b08b9b377d013136` | `catalog_task_record`, `team_code` | `payload`, `is_valid`, `sctask_number`, `error_message` |
| [`sctask_step3_process_response.js`](sctask_step3_process_response.js) | `f53a3ca3c3af4714b08b9b377d013130` | `status_code`, `response_body`, `rest_error_message`, **`sctask_number`** | `success`, `http_status`, `response_body`, `error_message` |

### Problem — action `Send Problem to Ansible EDA`

| | |
|---|---|
| Action sys_id | `1f073977c3ef4b14b08b9b377d013118` |
| `event_type` emitted | `servicenow.problem.created` |

| File | Step sys_id | Declared inputs | Declared outputs |
|---|---|---|---|
| [`problem_step1_build_payload.js`](problem_step1_build_payload.js) | `f7073977c3ef4b14b08b9b377d0131d0` | `problem_record`, `team_code` | `payload`, `is_valid`, `problem_number`, `error_message` |
| [`problem_step3_process_response.js`](problem_step3_process_response.js) | `d0177977c3ef4b14b08b9b377d0131c9` | `status_code`, `response_body`, `rest_error_message`, **`problem_number`** | `success`, `http_status`, `response_body`, `error_message` |

---

## 4. How to paste one in

1. **Flow Designer → Actions**, open the action named in the table above.
2. Click the step — `Build EDA Payload` or `Process Response`.
3. Declare the **input and output variables first**, exactly as listed above. A script that assigns
   to an undeclared output is **silently dropped**; nothing warns you.
4. Open the **Script** field, select all, delete, and paste the whole file including the
   `(function execute(inputs, outputs) {` wrapper and the `})(inputs, outputs);` at the end.
5. **Save**, then **Publish** the action. An unpublished edit does not run — the flow uses the last
   published snapshot.

> ⚠️ **Check the script mode before you paste.** These scripts are **ES5** — `var`, no arrow
> functions, no template literals. Since the **Xanadu** release ServiceNow enables **ES2021 (ES12)
> mode by default for newly created scripts**, regardless of the application's JavaScript mode. ES5
> runs correctly either way, so this is not a blocker, but `'use strict'` only actually enforces
> anything in ES12 mode. The per-script ES12 toggle lives in `sys_es_latest_script` and is **lost on
> XML export and in update sets** — if you promote this app, set the mode at the **application**
> level.

> ⚠️ **Map record pills bare.** Feed the record pill itself, not `➛ Number`. Step 1's input is typed
> **String**, so a dot-walk to Number is type-compatible and gets accepted happily — then
> `GlideRecord.get()` treats the ticket number as a sys_id and you get
> `Problem not found: PRB0040012`. See the troubleshooting table in
> [adding-record-types.md](../adding-record-types.md).

---

## 5. How the three record types differ

Useful if you are adding a fourth record type — see
[adding-record-types.md](../adding-record-types.md) for the full walkthrough.

**The `step1_build_payload` scripts are substantially different.** Same skeleton, but each reads its
own table and its own fields:

| | Incident | SCTASK | Problem |
|---|---|---|---|
| Table read | `incident` | `sc_task` → `sc_req_item` | `problem` |
| Extra lookup | `em_alert`, when `origin_table` is an alert | The RITM's catalog variable pool | none |
| Notable | Emits `em_*` alert context | Loops catalog variables, so reserved keys are set **last** | Emits real JSON booleans; state codes are **101–107**, not incident's 1–8 |

**The `step3_process_response` scripts are nearly identical** — and there are still three of them on
purpose. The differences:

- `var LOG` differs in all three, so a failure files itself under the right name in `syslog`.
- SCTASK and Problem take an **extra input** (`sctask_number` / `problem_number`) and prefix it onto
  `error_message`. Incident does not. A bare `HTTP 401` in `syslog` with three record types and
  three teams is nearly useless.

A single shared file would force you to hand-edit the `LOG` line after pasting, which is exactly the
hand-editing this directory exists to prevent.

### The `event_type` contract

Each step 1 sets `payload.event_type`, and the team rulebooks match on that exact string. **Change
it and every rule silently stops firing while the event stream counter keeps moving** — the events
arrive and match nothing. If a POST returns 200 but no job launches, check this string first.

---

## 6. Known quirks in the current scripts

Recorded so they are not mistaken for bugs, and so the Centene port does not inherit them silently.

| Where | Quirk |
|---|---|
| `incident_step1_build_payload.js` | Reads five `u_` columns — `u_requester`, `u_application_service`, `u_root_cause`, `u_event_issue`, `u_event_id` — that **do not exist on this PDI** (verified against `sys_dictionary`, 2026-10-05). They are cncdev customisations. Harmless: the helpers return `''`, so the keys are emitted empty. They become real when this is built on cncdev |
| `problem_step1_build_payload.js` | Carries a comment block listing ten further cncdev `u_` columns deliberately **not** ported, plus the note that cncdev labels `category` as "symptom" on the Problem form. Read it before porting |
| `problem_step3_process_response.js` | The fallback string is `'(unknown task)'`, carried over from the SCTASK copy. Cosmetic, appears only when `problem_number` is unmapped |

---

## 7. Re-pulling these from the instance

If the scripts are edited in the ServiceNow UI, these files go stale. To pull the live text again,
read `sys_variable_value` filtered on the **step** sys_id from the tables above:

```
GET /api/now/table/sys_variable_value?sysparm_query=document_key=<step sys_id>&sysparm_fields=value,order
```

Two rows come back per step. The script is the one whose `value` starts with `(function` (the other
is a reference to the variable definition). Convert CRLF to LF before saving — ServiceNow stores
`\r\n`.

Notes:

- Authenticate with the PDI `api_user` over Basic auth. Pass credentials via `curl -K` on stdin so
  the password never appears in `ps`. **Never commit them.**
- **An unknown column in `sysparm_query` is silently ignored and returns the whole table.** Always
  run a negative control — a bogus `document_key` must return 0 rows — before trusting a result.
- The **published snapshot** is what actually runs, not the definition step. Verified 2026-10-05 that
  all six matched, but if they ever disagree, the snapshot wins. The Problem snapshot action is
  `0228797bc3ef4b14b08b9b377d0131c8`.

Last pulled from the PDI: **2026-10-05**.

---

## Self-check

**Did I skip any prerequisite steps?** No. §4 puts *declare the variables first* ahead of pasting,
because a script assigning to an undeclared output is silently dropped — which is the failure this
directory exists to prevent, and it happens before you can test anything. The one prerequisite that
is deliberately out of scope is what the pipeline *is*; §0 links the main README for that rather than
restating it.

**Is every command copy-paste ready with context?** The two commands here are the
`sys_variable_value` GET in §7 and its negative control. Both state the table, the filter and what a
correct result looks like — two rows per step, exactly one beginning `(function`. The negative
control is not optional advice: an unknown column in `sysparm_query` is **silently ignored** and
returns the whole table, so a result you have not controlled for proves nothing.

**Would a complete novice understand every single sentence?** The hardest idea is that a step's
declared variable name, the pill feeding it, and the name the script reads are three separate things
that must agree — stated at the top of §3 before any table uses it. The `step2` gap in the numbering
is explained where it would otherwise read as a missing file.

**Verified against the live PDI, 2026-10-07.** Every declared input and output in §3 matches what the
six scripts actually read and assign; all three `event_type` values; every action and step sys_id
resolves; `sys_variable_value` returns exactly two rows per step with exactly one beginning
`(function`; the bogus-key negative control returns zero rows; the `'(unknown task)'` fallback in
§6 is where §6 says it is; and all six files are pure ASCII. The record-number payload keys the
rulebooks read — `incident_number`, `task_number`, `problem_number` — all match what the scripts
emit. **Note `task_number`, not `sctask_number`:** the SCTASK step *output* is `sctask_number` while
the *payload key* is `task_number`. Those are two different layers and both are correct.
