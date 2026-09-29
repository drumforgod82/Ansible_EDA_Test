# ServiceNow → EDA Dynamic Team Routing

One flow, one action, one REST step. Routing comes from a config table, so adding a team is a
row — no flow or action edits.

- **Instance:** `dev211593.service-now.com` (PDI)
- **Scoped app:** `James EDA Test` / `x_661661_james_tes`
- **AAP:** sandbox 2.7, gateway `sandbox-aap-jdrebel2-dev.apps.rm1.0a51.p1.openshiftapps.com`
- **Language mode:** ES5 (`var` only — no `const`, `let`, or arrow functions)

---

## 0. Before you start

### What you are building, in one sentence

When an incident is created, a flow looks up which team owns it, reads that team's event stream
address and credential from a config table, and POSTs the incident to that stream — so Ansible
Event-Driven Automation can react.

### Vocabulary

| Term | What it actually is |
|---|---|
| **Flow** | The automation that runs when something happens. Yours starts when an incident is created. |
| **Action** | A reusable bundle of steps a flow calls. Think of it as a function. |
| **Step** | One thing inside an action — run a script, make a REST call. |
| **Pill** | A little draggable token representing a value from an earlier step. Wherever you see a pill picker, you can feed in live data instead of typing a fixed value. **This is the whole trick behind this design.** |
| **Connection & Credential Alias** | A named pointer to *where* to call (base URL) and *how* to authenticate (the secret). The secret lives here so it never appears in your flow. |
| **Scoped app** | A container that keeps your work separate from the rest of the instance. Yours is `James EDA Test`. |
| **Event stream** | The AAP endpoint that accepts your POST. Each team has its own, identified by a UUID in the URL. |

### The one idea that makes this scale

A REST step normally has a fixed address and a fixed credential. **Yours can take pills for both.**
So instead of one REST step per team, you have *one* REST step whose address and credential are
looked up per incident. Adding a team becomes adding a table row.

### Order of work

Build bottom-up so nothing references something that does not exist yet:

```
groups  →  credentials/aliases  →  tables  →  table rows  →  action  →  flow  →  test
  5.1          5.2                5.3/5.4       5.3          5.5-5.8     5.9     8
```

Budget roughly 2–3 hours for a first pass. Steps 5.2 and 5.7 are where mistakes happen.

---

## 1. Why this works: both REST step fields accept pills

Verified in the PDI 2026-09-28. The existing REST step stores these as separate fields:

| Field | Current value | Pill? |
|---|---|---|
| `connection_alias` | `14a6516a…` (Ansible EDA Token Alias) | **yes** |
| `resource_path` | `eda-event-streams/api/eda/v1/external_event_stream/25c68345…/post/` | **yes** |
| `base_url` | gateway host | static is fine — one gateway for all teams |
| `headers` | `User-Agent`, `Content-Type` — **no `Authorization`** | — |

Two consequences:

1. **The credential stays out of script and out of flow data.** The connection alias injects it at
   call time, so no token appears in a step output, a pill, or the flow execution log. This is the
   preferred pattern in `references/integration-and-secrets.md` and the step already does it — do
   **not** replace it with a scripted `RESTMessageV2` and a hand-built `Authorization` header,
   which that reference lists as *not permitted*.
2. **Because both fields take pills, one REST step serves every team with that team's own
   credential.** No shared token, no If/Else per team, no `sn_cc`.

> `resource_path` currently hardcodes stream 1's UUID (`25c68345…`), which is why real incidents
> have only ever reached `ServiceNow Event Stream`. Replacing it with a pill is the core change.

---

## 2. Architecture

```
Incident created  (trigger condition: Assignment group is not empty)
  │
  ├─ 1. Look Up Record ── EDA Team Route        ← singular action, returns one Record
  │        Assignment group = Trigger→Incident→Assignment group
  │        Active = true
  │        If multiple records are found = Return only the first record
  │        Don't fail on error = checked
  │
  ├─ 2. If  1 → EDA Team Route Record → Sys ID  is not empty
  │     │      (the no-route gate — see §5.9 for why it is on Sys ID
  │     │       and not on the Record pill itself)
  │     │
  │     ├─ 3. Action: Send Incident to Ansible EDA
  │     │       inputs — route pills come straight off step 1's record:
  │     │         Incident Record    = Trigger → Incident Record
  │     │         Team Code          = 1 → EDA Team Route Record → Team code
  │     │         Event Stream UUID  = 1 → EDA Team Route Record → Event stream UUID
  │     │         Connection Alias   = 1 → EDA Team Route Record → Connection alias
  │     │       ├─ step 1  Script    build sanitised payload
  │     │       ├─ step 2  REST      connection_alias + resource_path = pills
  │     │       └─ step 3  Script    normalise status → outputs
  │     │
  │     └─ 4. If  Action → Success  is false
  │              └─ 5. Create Record ── EDA Publish Log   (all pills)
  │
  └─ Else
        └─ 6. Create Record ── EDA Publish Log, "no route for group"
```

One route row per assignment group, so one record, so no loop. If you ever need one incident to
fan out to **several** EDA endpoints, switch to the plural `Look Up Records` action and a
`For Each Item` loop — that variant is in §5.9a, and it is the only case that needs a loop.

Only **one** script step contains logic, and it touches no credentials.

### Why there is still one script step

Building ~25 sanitised fields into JSON cannot be done safely with pills. You *can* type a JSON
body with pills inline, but one apostrophe or newline in `short_description` produces invalid JSON
and the POST fails with a confusing 400. `cleanFieldValue` exists to prevent exactly that.

The standard prohibits **credentials** in script, not scripting. This step handles no credentials.

---

## 3. Design decision: key the table on `team_code`

Two different questions hide inside "which stream?":

| Question | Changes over time? | Owner |
|---|---|---|
| Which team owns this incident? | **yes** — later priority, category, CI class | process |
| What are Team A's stream coordinates? | no | platform |

Keying the table on **assignment group** would mean re-keying it when a Decision Table takes over
the first question. Keying on **`team_code`**, with assignment-group matching isolated in the Look
Up Records step, means a Decision Table later replaces **only step 1** of the flow. Steps 2–6 and
the whole action stay untouched.

So the table carries both: `team_code` (stable key) and `assignment_group` (swappable input).

---

## 4. AAP prerequisites

| # | Item | Why |
|---|---|---|
| 1 | Move stream 3 `sn-team-b` from org `Default` to **Team B** | Everything else Team B is in Team B. Experiments 1–3 measure org isolation, so a Default-org stream measures the wrong thing. **PATCH the org — do not recreate**, or the UUID changes and the table row goes stale. |
| 2 | Keep `additional_data_headers` **empty** on streams 2 and 3 | Forwarding `Authorization` copies the stream token into `meta.headers`, job `extra_vars`, and the AAP database in cleartext. |
| 3 | Confirm activations 3 and 4 `running`, mappings intact | A stale `source_mappings` name silently stops the rule firing. |

| Team | Stream | UUID |
|---|---|---|
| Team A | `sn-team-a` | `<team-a-stream-uuid>` |
| Team B | `sn-team-b` | `<team-b-stream-uuid>` |

> **UUIDs are deliberately not committed.** This repo is public, and a stream UUID plus the gateway
> hostname is the complete POST endpoint — the only remaining control is the stream token. Read the
> real values from AAP when you need them:
>
> ```bash
> tok=$(security find-generic-password -a "$USER" -s sandbox-aap -w)
> gw="<your-aap-gateway>"
> curl -sS -H "Authorization: Bearer $tok" "$gw/api/eda/v1/event-streams/?page_size=50" \
>   | python3 -c "import sys,json;[print(s['name'], s['uuid']) for s in json.load(sys.stdin)['results']]"
> ```

---

## Screenshots to capture

This guide has none yet. The README's existing images are all from the **single-team** build and
several are now wrong — `50-sn-action-inputs.png` is captioned "Action inputs — Incident Record"
when the action has four inputs, and the event-stream and activation shots show one of each.

Capture these into `docs/images/` using the existing numbering convention, then replace the
matching placeholder below. Naming: `7N-sn-routing-<what>.png` for ServiceNow, `8N-aap-<what>.png`
for AAP.

| # | Filename | What to show | Section |
|---|---|---|---|
| 1 | `70-sn-route-table-columns.png` | `EDA Team Route` table — the six columns and their types | §5.3 |
| 2 | `71-sn-route-table-rows.png` | The two route rows. **Blur or crop the Event stream UUID column.** | §5.3 |
| 3 | `72-sn-action-inputs-four.png` | All four action inputs with types — replaces the stale `50-sn-action-inputs.png` | §5.5 |
| 4 | `73-sn-step1-input-vars.png` | Step 1's two input variables, `Incident_record` and `team_code`, with their pills mapped | §5.6 |
| 5 | `74-sn-step3-input-vars.png` | Step 3's three lowercase input variables and four outputs | §6.2 |
| 6 | `75-sn-lookup-record-step.png` | The **Look Up Record** step — singular action, conditions, "Return only the first record" | §5.9 |
| 7 | `76-sn-flow-action-pills.png` | The flow's four action-input pills, incl. the **bare** Connection alias pill | §5.9 |
| 8 | `77-sn-action-outputs.png` | Action outputs, showing `payload` wired to **step 1** not step 3 | §6.2 |
| 9 | `80-aap-two-event-streams.png` | Both event streams with per-team orgs. **Crop the UUID column.** | §4 |
| 10 | `81-aap-two-activations.png` | Both activations running, each mapped to its own stream | §4 |
| 11 | `82-aap-job-extra-vars.png` | A job's `extra_vars` showing `target_team` populated and `sn_close_incident: true` | §8 |

> ⚠️ **Two of these show secrets-adjacent data.** Crop or blur the **Event stream UUID** in #2 and
> #9 — this repo is public, and a stream UUID plus the gateway hostname is the complete POST
> endpoint. The UUIDs are deliberately redacted from the text for the same reason (§4).

Placeholder syntax used below, so a missing image is obvious rather than silently absent:

```markdown
<!-- SCREENSHOT: 73-sn-step1-input-vars.png - step 1's two input variables with pills mapped -->
_Screenshot pending: step 1 input variables._
```

---

## 5. Build steps

### 5.1 Two groups

**User Administration → Groups → New**: `Team-A`, `Team-B`. The name is what the route rows
reference, so spelling matters.

### 5.2 One alias + connection + credential per team

Do this twice, inside the `James EDA Test` scope. This is what lets each team keep its own token.

**Credential** — *Connections & Credentials → Credentials → New → API Key Credentials*

| Field | Team A | Team B |
|---|---|---|
| Name | `Ansible EDA Team A Token` | `Ansible EDA Team B Token` |
| API Key Header | `Authorization` | `Authorization` |
| API Key | Team A stream token | Team B stream token |

Tokens are in the macOS keychain:

```bash
security find-generic-password -a "$USER" -s sandbox-eda-team-a -w
security find-generic-password -a "$USER" -s sandbox-eda-team-b -w
```

> **Unresolved: `Bearer ` prefix or not.** `references/integration-and-secrets.md` says store
> `Bearer <token>` with the prefix *inside* the API Key value, verified 2026-09-18 against an
> AAP 2.7 event stream. But a direct `curl` on 2026-09-28 got **HTTP 200 with the bare token**, and
> the `Bearer ` form was never tested. Both may be accepted. Start bare; if the POST returns 401,
> add the prefix inside the credential value. Record which one works and fix whichever note is
> wrong.

**Alias** — *Connection & Credential Aliases → New*: `Ansible EDA Team A Alias` /
`Ansible EDA Team B Alias`, type **Connection and Credential**, connection type **HTTP**.

**Connection** — from the alias, *HTTP Connections* related list → New

| Field | Value |
|---|---|
| Name | `Ansible EDA Team A Connection` / `…Team B…` |
| Connection alias | the alias above |
| Credential | the credential above |
| Connection URL | `https://sandbox-aap-jdrebel2-dev.apps.rm1.0a51.p1.openshiftapps.com` |

> Base URL only. The resource path is supplied by the REST step.

### 5.3 Route table

*System Definition → Tables → New*, `James EDA Test` scope selected.
Label **`EDA Team Route`** → `x_661661_james_tes_eda_team_route`

| Column label | Type | Len | Notes |
|---|---|---|---|
| Team code | String | 40 | lookup key — `team-a`, `team-b` |
| Assignment group | Reference → `sys_user_group` | | swappable mapping input |
| Event stream name | String | 100 | must equal the rulebook's expected name |
| Event stream UUID | String | 36 | becomes the `resource_path` pill |
| Connection alias | Reference → `sys_alias` | | becomes the `connection_alias` pill |
| Active | True/False | | switch a team off without deleting |

Optional: add **Base URL** (String, 255) if a team ever lives on a different gateway, and pill it
into the REST step's `base_url`. Not needed today — one gateway.

> **Creating a table in a scoped app auto-creates a role and nobody holds it.**
> `EDA Team Route` got `user_role = x_661661_james_tes.eda_team_route_user`, granted to zero users.
> Its ACLs have `admin_overrides = true`, so **an admin sees the rows and a non-admin sees nothing**.
>
> That matters twice:
>
> 1. **Flow Designer's table picker only lists tables the current user can read.** If the table does
>    not appear when adding a Look Up Record step, check the Workflow Studio **application scope**
>    first — a scoped table is filtered out of pickers when the session context is Global — then
>    search by the **label** (`EDA Team Route`), not the internal name.
> 2. **At run time the flow must be able to read it.** With the flow set to `run_as: user` and
>    nobody holding the role, the lookup returns **zero records silently** — no error, just no
>    routing. §5.10's "Run as System user" is what prevents this. Granting the role to a group is
>    the alternative.
>
> This is a trap because it fails *differently* for you than for everyone else: it works while you
> build and test as admin, then returns nothing in normal use.

Rows:

| Team code | Assignment group | Event stream name | Event stream UUID | Connection alias | Active |
|---|---|---|---|---|---|
| `team-a` | Team-A | `sn-team-a` | `<team-a-stream-uuid>` | Ansible EDA Team A Alias | true |
| `team-b` | Team-B | `sn-team-b` | `<team-b-stream-uuid>` | Ansible EDA Team B Alias | true |

Substitute the real UUIDs from AAP (see §4) — they are not committed.

<!-- SCREENSHOT: 70-sn-route-table-columns.png - the EDA Team Route table columns and types -->
_Screenshot pending: the EDA Team Route table columns and types._

<!-- SCREENSHOT: 71-sn-route-table-rows.png - the two route rows, UUID column cropped -->
_Screenshot pending: the two route rows, UUID column cropped._

### 5.4 Failure log table

Label **`EDA Publish Log`** → `x_661661_james_tes_eda_publish_log`

| Column label | Type | Len |
|---|---|---|
| Incident | Reference → `incident` | |
| Team code | String | 40 |
| Event stream name | String | 100 |
| HTTP status | String | 10 |
| Success | True/False | |
| Error message | String | 4000 |
| Payload | String | 8000 |

Populated entirely with pills by a **Create Record** step — no script. Closes the gap where a
failed POST set `error_message` and nothing ever read it.

### 5.5 Action inputs

Open **`Send Incident to Ansible EDA`** and declare four inputs:

| Input | Type |
|---|---|
| `incident_record` | Reference → Incident |
| `team_code` | String |
| `event_stream_uuid` | String |
| `connection_alias` | **Connection & Credential Aliases** (not a plain `sys_alias` reference) |

The `connection_alias` type matters: the REST step's Connection Alias field expects this type and
must be fed the **bare pill**. See §5.7.

<!-- SCREENSHOT: 72-sn-action-inputs-four.png - all four action inputs with their types -->
_Screenshot pending: all four action inputs with their types._

### 5.6 Action step 1 — build payload (script)

1. Add a **Script** step named `Build EDA Payload`.
2. Declare **two input variables**. The **Name** must match exactly — ServiceNow auto-fills it from
   the Label, so check it before saving:

   | Name | Type | Drag this pill into it |
   |---|---|---|
   | `Incident_record` | Reference → Incident | action input **Incident Record** |
   | `team_code` | String | action input **Team Code** |

3. Declare four **output variables**: `payload`, `is_valid`, `incident_number`, `error_message`.
4. Paste the script from §6.1.
5. Publish the action, then confirm `target_team` is populated in AAP's job `extra_vars`.

> **Declaring a variable and mapping a pill into it are two separate actions.** Miss the mapping and
> the input is empty at run time with no warning. Miss the name and the script reads `undefined`.
> Neither produces an error, and `'use strict'` does not catch either. §6.1 has the full account of
> how this shipped an empty `target_team` for days.

<!-- SCREENSHOT: 73-sn-step1-input-vars.png - step 1's Incident_record and team_code variables with pills mapped -->
_Screenshot pending: step 1's Incident_record and team_code variables with pills mapped._

### 5.7 Action step 2 — REST step

Keep the existing step. Change three things:

| Field | Set to |
|---|---|
| Connection Alias | pill → **Action input → Connection alias** |
| Resource Path | `eda-event-streams/api/eda/v1/external_event_stream/` + pill **Event stream UUID** + `/post/` |
| Request Body | pill → **Step 1 → Payload** |

Leave `headers` alone — `User-Agent` and `Content-Type` only. **Never add an `Authorization`
header**; the alias supplies it.

Keep the existing `retry_policy`.

### 5.8 Action step 3 — normalise the response (script)

See §6.2. Outputs: `success`, `http_status`, `response_body`, `error_message`.

### 5.9 Flow

Rebuild **`Trigger EDA remediation on Incident-EDA`** (or create a new flow and deactivate this
one) per the §2 diagram.

**Trigger:** Incident → Created, with condition **Assignment group is not empty**. Filtering at
the trigger keeps the flow from starting for incidents that can never route.

**Step 1 — Look Up Record** on `x_661661_james_tes_eda_team_route`:

| Setting | Value |
|---|---|
| Action | **Look Up Record** — the singular one |
| Table | `EDA Team Route` |
| Conditions | `Assignment group` is `Trigger → Incident → Assignment group` **AND** `Active` is `true` |
| If multiple records are found action | `Return only the first record` |
| Don't fail on error | checked |

> **Pick the singular action deliberately.** Flow Designer ships both `Look Up Record` and
> `Look Up Records`, and which one you choose decides the whole shape of the flow:
>
> | Action | Output pill | Type | Loop needed? |
> |---|---|---|---|
> | `Look Up Record` | `EDA Team Route Record` | **Record** | No — pill its fields directly |
> | `Look Up Records` | `Records` | **Array** | Yes — `For Each Item` |
>
> Use the singular action here. One assignment group maps to one active route row, so there is
> nothing to iterate.

**Step 2 — If**, gating on `1 → EDA Team Route Record → Sys ID` **is not empty**.

Because **Don't fail on error** is checked, a group with no route row does not fail the step — it
returns an empty record and the flow carries on. Without this gate you would hand an empty
connection alias to the REST step and get:

```
Unable to load connection with alias ID:   <a href="/sys_alias.do?sys_id=">…
```

The blank after `sys_id=` is the signature of an unresolved alias pill.

> **Gate on a scalar field, never on the Record pill itself.** `EDA Team Route Record is empty`
> compiles to a string comparison that is always false, so the branch silently never fires. `Sys ID`
> is a String, so it compares correctly. The same trap applies to `Records is empty` on the plural
> action — there you branch on `Count`.
>
> If you would rather let a missing route row hard-fail, leave **Don't fail on error** unchecked and
> drop this If — the step errors and your flow's **Error Handler** picks it up. That is a valid
> design; it just gives you a flow error instead of a clean log row, and it cannot distinguish
> "no route configured" from "the lookup itself broke".

**Step 3 — the action**, with every route pill taken off step 1's record:

| Action input | Pill |
|---|---|
| Incident Record `[Incident]` | `Trigger → Record Created → Incident Record` |
| Team Code | `1 → EDA Team Route Record → Team code` |
| Event Stream UUID | `1 → EDA Team Route Record → Event stream UUID` |
| Connection Alias `[Connection & Credential Aliases]` | `1 → EDA Team Route Record → Connection alias` |

**Steps 4–5 — failure logging**, as in §2.

### 5.9a Variant — fanning out to several endpoints

Only if one incident must reach **more than one** EDA endpoint. Then:

1. Change step 1's Action to **Look Up Records** (plural). Its output becomes a `Records` pill of
   type Array. Leave **Maximum records** empty, or set it to the fan-out ceiling you want.
2. Replace the §5.9 step 2 If with a **For Each Item** loop, `Items` = `1 → Look Up Records → Records`.
3. Move the action inside the loop and rewire all three route pills to **Current Item → …**.

No count gate is needed in this shape: zero matching rows means the loop body never runs, which is
already the "no route" behaviour. Add an `If Count is 0` branch only if you want a log row for it.

> **Why the Items field looks broken when you get this wrong.** `Items` is typed **Array**, and the
> pill picker disables every pill whose type is not an Array. If step 1 is the singular
> `Look Up Record`, its outputs are Record / Table / Choice / String — so the entire picker tree
> greys out and nothing is clickable. That grey-out is not a permissions problem or a UI bug; it is
> a type mismatch telling you the loop does not belong in this flow.

<!-- SCREENSHOT: 75-sn-lookup-record-step.png - the Look Up Record step: singular action, conditions, return-first -->
_Screenshot pending: the Look Up Record step: singular action, conditions, return-first._

<!-- SCREENSHOT: 76-sn-flow-action-pills.png - the flow's four action-input pills, Connection alias as a bare pill -->
_Screenshot pending: the flow's four action-input pills, Connection alias as a bare pill._

### 5.10 Flow properties

**⋮ → Flow properties → Run as: System user.**

Currently `run_as: user`, so it runs with the incident creator's rights. A non-admin caller may be
unable to resolve the credential, which surfaces as a confusing auth failure rather than a
permission error.

Record-triggered flows run in their own transaction, so incident creation is not waiting on AAP.
Confirm the trigger is not set to run in the foreground.

### 5.11 Disable the old path

In AAP, **stop activation 1** (`ServiceNow Event Stream Rulebook`).

Leave stream 1 and credential 4 until both teams fire end to end. `my_eda_rulebook.yml` expects
the old `incident_created` value and will not match the new payload, so it is already dead — but
keeping it costs nothing and preserves a rollback.

Delete later **in this order**: activation 1 → stream 1 → credential 4. The activation holds a
mapping to the stream, so the stream cannot go first.

---

## 6. Scripts

Both are ES5, IIFE-wrapped, `'use strict'`, every output initialised before the first branch, and
every failure logged with a prefix and thrown so the action's error path fires.

### 6.1 Step 1 — build payload

Declare **two** input variables on this step, with these exact names:

| Declared variable name | Type | Mapped from |
|---|---|---|
| `Incident_record` | Reference → Incident | action input **Incident Record** |
| `team_code` | String | action input **Team Code** |

> **An action input is not visible to a step's script.** Each step is its own scope: `inputs.*`
> resolves only against variables declared *on that step*. Forwarding an action input takes two
> separate actions — declare the step variable, then map the action's pill into it. Miss either and
> the value is silently `undefined`.
>
> `team_code` was missing here until 2026-09-29. The action received `team-b` correctly — it was
> visible in the execution details — but it was never handed down to this script, so
> `inputs.team_code` was `undefined`, `cleanFieldValue` returned `''`, and **every payload shipped
> with `target_team` empty**. Nothing errored. Routing still worked, because routing is carried by
> the event stream UUID, not by `target_team` — so the only symptom was a blank field arriving in
> AAP's `extra_vars`, which all three rulebooks read
> (`target_team: "{{ event.payload.target_team | default('') }}"`).
>
> Fixed and verified on INC0010017 (AAP job 38): `target_team = team-b`.
>
> `Incident_record` keeps its capital `I` because that is how it was originally created; the script
> reads `inputs.incident_record || inputs.Incident_record` to tolerate either. Do not rely on that
> tolerance for new inputs — match the name exactly.

```javascript
(function execute(inputs, outputs) {
    'use strict';

    var LOG = 'EDA SendIncident/buildPayload: ';

    // event_type is a contract with the rulebooks. Both team rulebooks test
    // payload.event_type == 'servicenow.incident.created'. Changing this string
    // silently stops every rule from firing.
    var EVENT_TYPE = 'servicenow.incident.created';
    var EVENT_VERSION = '1.0';

    outputs.payload = '';
    outputs.is_valid = false;
    outputs.incident_number = '';
    outputs.error_message = '';

    // Step input names are CASE-SENSITIVE and need not match the action input.
    // This step declares 'Incident_record' (capital I) while the action input is
    // 'incident_record'. Accept either rather than depending on which one you are in.
    var record = inputs.incident_record || inputs.Incident_record;

    var incidentSysId = (record && typeof record === 'object' && record.getUniqueValue)
        ? record.getUniqueValue()
        : String(record || '');

    if (!incidentSysId) {
        // Name the inputs that actually arrived - this turns a name mismatch or an
        // unmapped pill from a guessing game into a one-line diagnosis.
        var present = [];
        for (var key in inputs) {
            if (inputs.hasOwnProperty(key)) {
                present.push(key + '=' + (inputs[key] ? 'set' : 'empty'));
            }
        }
        outputs.error_message = 'No incident record supplied. Step inputs present: ' +
            (present.length ? present.join(', ') : '(none)');
        gs.error(LOG + outputs.error_message);
        throw new Error(outputs.error_message);
    }

    var incident = new GlideRecord('incident');
    if (!incident.get(incidentSysId)) {
        outputs.error_message = 'Incident not found: ' + incidentSysId;
        gs.error(LOG + outputs.error_message);
        throw new Error(outputs.error_message);
    }

    outputs.incident_number = incident.getValue('number');

    function cleanFieldValue(value) {
        if (!value) {
            return '';
        }
        return String(value)
            .replace(/<[^>]*>/g, ' ')        // HTML tags
            .replace(/\r\n/g, ' ')
            .replace(/[\n\r\t]/g, ' ')
            .replace(/[\x00-\x1F\x7F]/g, '') // control characters
            .replace(/\\/g, '/')
            .replace(/\s+/g, ' ')
            .trim();
    }

    function displayValue(field) {
        return cleanFieldValue(field ? field.getDisplayValue() : '');
    }

    function rawValue(field) {
        return cleanFieldValue(field ? field.getValue() : '');
    }

    // Instance identity is configuration, not a literal.
    var sourceId = gs.getProperty('x_661661_james_tes.eda.source_id', '');
    if (!sourceId) {
        sourceId = gs.getProperty('instance_name', 'unknown');
    }

    var emAlert = null;
    var originTable = rawValue(incident.origin_table);
    var originId = rawValue(incident.origin_id);

    if (originTable === 'em_alert' && originId) {
        var alertRecord = new GlideRecord('em_alert');
        if (alertRecord.get(originId)) {
            emAlert = alertRecord;
        } else {
            gs.warn(LOG + 'origin is em_alert but alert not found: ' + originId);
        }
    }

    var payload = {
        event_type: EVENT_TYPE,
        event_version: EVENT_VERSION,
        source: sourceId,
        target_team: cleanFieldValue(inputs.team_code),

        incident_number: displayValue(incident.number),
        sys_id: rawValue(incident.sys_id),
        caller: displayValue(incident.caller_id),
        requester: displayValue(incident.u_requester),
        contact_type: displayValue(incident.contact_type),
        short_description: displayValue(incident.short_description),
        description: displayValue(incident.description),

        // Display values keep the original behaviour ("3 - Moderate", "In Progress").
        // The *_value pairs carry raw codes ("3", "2") for numeric comparison.
        priority: displayValue(incident.priority),
        priority_value: rawValue(incident.priority),
        state: displayValue(incident.state),
        state_value: rawValue(incident.state),
        urgency: displayValue(incident.urgency),
        impact: displayValue(incident.impact),

        cmdb_ci: displayValue(incident.cmdb_ci),
        business_service: displayValue(incident.business_service),
        service_offering: displayValue(incident.service_offering),
        application_service: displayValue(incident.u_application_service),
        assigned_to: displayValue(incident.assigned_to),
        assignment_group: displayValue(incident.assignment_group),
        category: displayValue(incident.category),
        origin_table: originTable,
        origin_id: originId,
        root_cause: displayValue(incident.u_root_cause),
        event_issue: displayValue(incident.u_event_issue),
        event_id: displayValue(incident.u_event_id),

        em_alert_node: emAlert ? displayValue(emAlert.node) : '',
        em_metric_name: emAlert ? displayValue(emAlert.metric_name) : '',
        em_resource: emAlert ? displayValue(emAlert.resource) : '',
        em_type: emAlert ? displayValue(emAlert.type) : ''
    };

    outputs.payload = JSON.stringify(payload);
    outputs.is_valid = true;

})(inputs, outputs);
```

### 6.2 Step 3 — normalise the response

> **Paste from the file, not from here:** `docs/scripts/step3_process_response.js`.
> It is the canonical copy, pure ASCII, and verified with `node --check`. Copying out of a
> rendered document can convert straight quotes to curly ones, which breaks the script
> silently. This block is a mirror of that file - if they ever disagree, the file wins.

```javascript
(function execute(inputs, outputs) {
    'use strict';

    var LOG = 'EDA SendIncident/handleResponse: ';
    var BODY_IN_OUTPUT = 500;
    var BODY_IN_ERROR = 200;

    outputs.success = false;
    outputs.http_status = '';
    outputs.response_body = '';
    outputs.error_message = '';

    // Input names must match the step declared variable names exactly.
    // A mismatch reads as undefined with no error.
    var status = String(inputs.status_code || '');
    var body = String(inputs.response_body || '');
    var restError = String(inputs.rest_error_message || '');

    outputs.http_status = status;
    outputs.response_body = body.substring(0, BODY_IN_OUTPUT);

    // 202 counts as success. The event stream may acknowledge asynchronously.
    if (status === '200' || status === '201' || status === '202') {
        outputs.success = true;
        return;
    }

    // An empty status means the request never left the instance: a connection,
    // alias, or credential problem rather than an endpoint rejection.
    if (status === '') {
        if (restError) {
            outputs.error_message = 'Request not sent: ' + restError.substring(0, BODY_IN_ERROR);
        } else {
            outputs.error_message = 'Request not sent and the REST step reported no error.';
        }
    } else {
        outputs.error_message = 'HTTP ' + status + ': ' + body.substring(0, BODY_IN_ERROR);
    }

    gs.error(LOG + outputs.error_message);

})(inputs, outputs);
```

Declare this step's input variables with these **exact names**, then map step 2's outputs into them:

| Declared variable name | Mapped from |
|---|---|
| `status_code` | step 2 → Status Code |
| `response_body` | step 2 → Response Body |
| `rest_error_message` | step 2 → Error Message |

Declare exactly four outputs — `success`, `http_status`, `response_body`, `error_message` — and no
`payload` output. `rest_error_message` is deliberately *not* called `error_message`: that name is
already taken by this step's **output**, and an input and output sharing a name in one step is how
these mismatches start.

> **The names must match the script character for character, casing included.** Flow Designer's
> script-step input variables are case-sensitive properties on `inputs`. Declaring `StatusCode`
> while the script reads `inputs.status_code` yields `undefined` — **silently**, and `'use strict'`
> does not catch it, because strict mode only errors on *writing* an undeclared variable, never on
> *reading* a property that isn't there.
>
> This failed on 2026-09-29 with a 200 from AAP. `StatusCode` held `200`, the pill was mapped
> correctly, and the script still produced `http_status = ''`, `success = false`, and the error
> message `HTTP :` — the concatenation on the last line with both holes empty. The step reported
> **Completed**, `If Successful` took the false branch, and nothing anywhere said "name mismatch".
>
> Two signatures worth memorising: **an error message with empty interpolation holes** (`HTTP :`),
> and **an output that stays blank while its source input is visibly populated** in execution
> details. Both mean a name mismatch, not an endpoint problem. The *Variable Name* column in
> execution details shows the real declared name — read it there, not off the label.

Also check the **action's own output wiring**: `payload` must come from **step 1's** Payload output.
This script never assigns `outputs.payload`, so pointing the action's `payload` output at step 3
leaves it permanently blank and the log table never records what was sent.

> This step deliberately does **not** throw. A non-2xx is a routing/endpoint problem to be recorded
> in the log table and reviewed, not a reason to abort the flow. Bad *input* throws (§6.1);
> a bad *response* is logged.

---

## 7. Cross-scope privileges

A scoped script touching a global table needs a `sys_scope_privilege` record with status
**Allowed**, or it fails at runtime with an error that reads like a bug.

| Touched | Privilege | Needed by |
|---|---|---|
| `incident` | Table, **read** | §6.1 `GlideRecord('incident')` |
| `em_alert` | Table, **read** | §6.1 alert enrichment |
| `sys_user_group` | Table, **read** | route table reference field |

Because the HTTP call is a REST step rather than scripted, **no `sn_ws.RESTMessageV2` privilege is
required** — one of several reasons to keep it that way.

Record this list in the app README so promotion can verify it per instance.

---

## 8. Verification

Before each test, confirm the target activation is `running`. Event streams use Postgres
`LISTEN`/`NOTIFY`, which is broadcast and **non-durable** — an event posted while an activation is
down is dropped silently, with no queue and no retry.

1. Create an incident with **Assignment group = Team-A**.
2. Check the counters:

```bash
tok=$(security find-generic-password -a "$USER" -s sandbox-aap -w)
gw="https://sandbox-aap-jdrebel2-dev.apps.rm1.0a51.p1.openshiftapps.com"
curl -sS -H "Authorization: Bearer $tok" "$gw/api/eda/v1/event-streams/?page_size=50" \
  | python3 -m json.tool | grep -E '"name"|events_received'
```

Expect `sn-team-a` to increment and `sn-team-b` to stay flat. Then repeat with **Team-B** and
expect the mirror image — that is Experiment 1 (isolation).

| Symptom | Most likely cause |
|---|---|
| No stream counter moves | Flow did not run — check the trigger condition and the Sys ID gate (§5.9) |
| `EDA Publish Log` row with 401 | Credential value: try the `Bearer ` prefix (§5.2) |
| `EDA Publish Log` row with 404 | `resource_path` pill resolved empty, or a stale UUID in the route row |
| Counter moves, no job launches | Rulebook mismatch — compare `event_type` and `eda_event_stream_name` |
| Both teams' rules fire on one event | Both activations mapped to the same stream — fan-out, not a queue |
| Nothing in the log table on failure | `Success` pill wired to the wrong step output |

---

## 9. Adding Team C later

1. Group `Team-C`.
2. Credential, alias, connection for Team C.
3. In AAP: org, event stream `sn-team-c` + credential, rulebook, activation.
4. One row in `EDA Team Route`.

No flow or action changes.

## 10. Making routing smarter later

Today routing is "assignment group → team". Eventually you may want "P1 database incidents go to
Team B regardless of group". There are three ways to get there. **Read all three before picking** —
most people reach for the Decision Table when option 1 would have done the job.

Everything below replaces **flow step 1 only**. The action, the REST step, both scripts, and the
log table never change.

### What I verified in your PDI first

| Finding | Consequence |
|---|---|
| All 26 existing decision tables use `answer_type: reference` with an `answer_table` | A decision table can return **a record**, so it can hand you back an `EDA Team Route` row directly |
| **No out-of-box Flow Designer action for decision tables exists in this instance** (searched `sys_hub_action_type_base` for anything named/interned "decision" — zero rows) | A flow cannot call a decision table by drag-and-drop here. It needs a script step. |
| The scriptable API is `sn_dt.DecisionTableAPI` (confirmed — `global.DecisionTableUtils` calls it internally) | That is the namespace to use, but see the caveat below |
| `api_user` holds `decision_table_admin` | You can read and build them |

That second row is the important one: a Decision Table **costs you a script step**, which is
exactly what you said you wanted to avoid. So it is not automatically the right answer.

---

### Option 1 — More columns, wider lookup condition ★ recommended first

**No script. No new concepts. Fifteen minutes.**

The `Look Up Record` step already has a full condition builder. To route on more than group, add
columns to the route table and widen the condition.

1. Open the `EDA Team Route` table, add columns for whatever you want to match on — for example
   **Priority** (String, 40) and **Category** (String, 40). Leave them empty to mean "any".
2. In the flow's **Look Up Record** step, add conditions:

   ```
   Assignment group  is  Trigger → Incident → Assignment group
   Active            is  true
   Priority          is one of  (empty)  OR  Trigger → Incident → Priority
   ```

3. Add an **Order** column (Integer) and sort the lookup by it ascending, so a specific row can win
   over a general one.

Covers the large majority of "route on more than one thing" needs. Reach past it only when the
logic genuinely needs OR-of-ANDs across many fields.

---

### Option 2 — A Conditions column on each row

**One short script step. Very flexible. Still one row per rule.**

ServiceNow has a field type called **Conditions** that renders a full condition builder *inside a
record*. Each route row then carries its own rule, editable in the UI by anyone.

1. Add a column to `EDA Team Route`: label **Match condition**, type **Conditions**, and set its
   dependent table to `incident`. The row now shows a condition builder.
2. Add an **Order** column (Integer) so rules evaluate most-specific first.
3. Replace flow step 1 with a script step that walks the rows in order and returns the first whose
   condition matches:

```javascript
(function execute(inputs, outputs) {
    'use strict';

    var LOG = 'EDA RouteMatch: ';
    var TABLE = 'x_661661_james_tes_eda_team_route';

    outputs.route_sys_id = '';
    outputs.team_code = '';
    outputs.event_stream_uuid = '';
    outputs.connection_alias = '';
    outputs.found = false;

    var record = inputs.incident_record;
    var incidentSysId = (record && typeof record === 'object' && record.getUniqueValue)
        ? record.getUniqueValue()
        : String(record || '');

    if (!incidentSysId) {
        gs.error(LOG + 'no incident record supplied');
        throw new Error('No incident record supplied');
    }

    var incident = new GlideRecord('incident');
    if (!incident.get(incidentSysId)) {
        gs.error(LOG + 'incident not found: ' + incidentSysId);
        throw new Error('Incident not found: ' + incidentSysId);
    }

    var route = new GlideRecord(TABLE);
    route.addQuery('active', true);
    route.orderBy('order');
    route.query();

    while (route.next()) {
        var condition = route.getValue('match_condition') || '';

        // An empty condition is a catch-all, which is why order matters.
        if (condition && !GlideFilter.checkRecord(incident, condition)) {
            continue;
        }

        outputs.route_sys_id = route.getUniqueValue();
        outputs.team_code = route.getValue('team_code');
        outputs.event_stream_uuid = route.getValue('event_stream_uuid');
        outputs.connection_alias = route.getValue('connection_alias');
        outputs.found = true;
        return;
    }

    gs.info(LOG + 'no matching route for ' + incident.getValue('number'));

})(inputs, outputs);
```

`GlideFilter.checkRecord(record, encodedQuery)` returns true when the record satisfies the query.
That one line is what turns a stored condition into a live decision.

Then gate the flow on this step's **Found** output instead of a record count, and pill the other
three outputs into the action.

> Requires a cross-scope privilege for `GlideFilter` (Scriptable API, execute) on top of those in §7.

---

### Option 3 — A real Decision Table

**Choose this when non-technical process owners must own the routing logic**, or you want Decision
Builder's versioning and test harness. It costs a script step, because this instance has no flow
action for it.

#### 3a. Create the decision table

1. Navigate to **Decision Tables** (or **Decision Builder**) in the Application Navigator.
   Make sure the application picker shows **James EDA Test**.
2. **New**, and name it. Everything else can stay at its default.

A new table arrives as:

```
answer_type       = reference
answer_table      = sys_decision_multi_result     <- the default
status            = draft
active            = false
enable_publishing = true
```

`answer_table = sys_decision_multi_result` is the **multiple-results** mode, and it is the right one
to keep. Rather than returning one record from one fixed table, you define **named answer
elements** — output fields you invent — and each decision row fills them in. Same idea as declaring
a function's return values.

> A decision table has **three** parts, and a new one has none of them. That is why it looks blank:
> **inputs** (facts in) → **answer elements** (values out) → **decisions** (rows mapping one to the
> other).

> **`status: draft` and `active: false` mean it will not evaluate.** There is a publish step.
> An unpublished table returning nothing looks exactly like a table whose conditions do not match —
> check `status` first when debugging.

#### 3b. Add inputs

Inputs are the facts the table reasons about. Add one:

| Label | Type | Reference |
|---|---|---|
| `Incident` | Reference | `incident` |

You can dot-walk from a reference input in conditions (`Incident → Priority`), so one input is
usually enough. Add scalar inputs only when a value is not reachable from the record.

> Name inputs explicitly. Several stock tables on your instance have auto-generated element names
> like `global_4060c5fe7f330210674d91fadc86650a`, which are unreadable six months later.

#### 3b-2. Add the answer element

Define one output:

| Label | Type | Reference |
|---|---|---|
| `Route` | Reference | `x_661661_james_tes_eda_team_route` |

One element of type Reference pointing at the route table gives you the UUID, alias, stream name,
and team code in a single answer — and keeps that configuration in the route table where the
platform team owns it, rather than duplicating it into the decision logic.

> Build the route table (§5.3) **before** this step, or there will be nothing to reference.
> To explore the feature first with no dependencies, make the element a plain **String** called
> `Team code` and have decisions return `team-a` / `team-b`. Swap it to the reference later.

Stock examples of both shapes exist on your instance: `Deployment Migration to ReleaseOps` uses a
`reference → sys_hub_flow` element alongside a `boolean` element.

#### 3c. Add decisions (the rows)

Each decision is **condition → answer**. They evaluate in `order`, and **the first match wins**.

| Order | Label | Condition | Answer |
|---|---|---|---|
| 100 | P1 database → Team B | `Incident → Priority` is `1` AND `Incident → Category` is `database` | the `team-b` route row |
| 200 | Group Team-A | `Incident → Assignment group` is `Team-A` | the `team-a` route row |
| 300 | Group Team-B | `Incident → Assignment group` is `Team-B` | the `team-b` route row |
| 999 | Default — no routing | *(leave empty)* | *(leave empty)* |

Two conventions worth copying from the tables already on your instance:

- **Leave gaps in `order`** (100, 200, 300) so you can insert a rule later without renumbering.
- **Finish with an empty-condition, empty-answer row at the highest order.** An empty condition
  matches everything, so it is your explicit "nothing matched" case. `SRM: Service management
  approval policy` does exactly this at order 100.

Most specific rules go first. Put the P1-database rule *above* the plain group rules, or the group
rule will win and the special case will never fire.

#### 3d. Call it from the flow

Replace flow step 1 with a script step:

```javascript
(function execute(inputs, outputs) {
    'use strict';

    var LOG = 'EDA RoutingPolicy: ';

    outputs.route_sys_id = '';
    outputs.found = false;

    var policyId = gs.getProperty('x_661661_james_tes.eda.routing_policy_id', '');
    if (!policyId) {
        gs.error(LOG + 'property x_661661_james_tes.eda.routing_policy_id is not set');
        throw new Error('Routing policy not configured');
    }

    // Verify the method name against sn_dt.DecisionTableAPI on your instance
    // before trusting this - see the caveat below.
    var api = new sn_dt.DecisionTableAPI();
    var result = api.getDecision(policyId, { incident: inputs.incident_record });

    if (result && result.answer) {
        outputs.route_sys_id = String(result.answer);
        outputs.found = true;
        return;
    }

    gs.info(LOG + 'no routing decision matched');

})(inputs, outputs);
```

Then add a **Look Up Record** on `EDA Team Route` by that sys_id, and pill its fields into the
action exactly as before.

Store the decision table's sys_id in the scoped property
`x_661661_james_tes.eda.routing_policy_id` rather than pasting it into the script — §7's
"no hardcoded sys_ids" rule.

> **Caveat, stated plainly:** I confirmed the namespace `sn_dt.DecisionTableAPI` exists, because
> `global.DecisionTableUtils` calls `new sn_dt.DecisionTableAPI().getDecisionTable(...)`
> internally. I did **not** confirm the *evaluation* method is `getDecision(id, inputs)` or that
> the result exposes `.answer`. Verify before relying on it: open the Script Include
> `sn_decision_table.DecisionTableUtil`, or use Decision Builder's built-in **Test** button to
> evaluate the table against a real incident and inspect the returned shape. ServiceNow's published
> docs would settle this, but the docs site renders article bodies with JavaScript and returns only
> its navigation shell to a fetcher, so I could not read them from this machine.

---

### Choosing

| | Script? | Who edits rules | Best when |
|---|---|---|---|
| **1. Wider lookup condition** | none | you, in the flow | routing is a handful of field matches — **start here** |
| **2. Conditions column** | one small step | anyone, per table row | many rules, each independently editable |
| **3. Decision Table** | one step + unverified API | process owners, in Decision Builder | logic is governed, audited, or owned outside the platform team |

Whichever you pick, the route table stays keyed on `team_code`, the action is untouched, and adding
a team is still a row plus its AAP objects (§9).
