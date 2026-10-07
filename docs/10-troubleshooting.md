# 10 — Troubleshooting

**This document covers how to find the cause when the pipeline does not work, organised by where the
failure happens rather than by what the error says.**

> **How to use this.** Don't read it top to bottom. Find your symptom in §1, which tells you which
> section to jump to.
>
> **Previous stage:** [08 — Routine ops](08-routine-ops.md) · **Related:**
> [09 — Reconnect after an AAP rebuild](09-reconnect-after-aap-rebuild.md)

> **Any unfamiliar word?** Every term and acronym used in these guides is defined in the
> [Glossary](glossary.md) — including AAP, EDA, PDI, SCTASK, data pill, dot-walk, work note
> and `extra_vars`.

---

## 0. The four places to look

There is **no central log table**. These four surfaces are everything you have, and knowing which
one went quiet tells you roughly where the failure is.

| Surface | Where | What it tells you |
|---|---|---|
| **Flow Executions** | ServiceNow → Workflow Studio → the flow → *Executions* tab | Every step, with its inputs and outputs. **Start here.** If there is no execution at all, ServiceNow never tried |
| **The work note on the record** | The incident / SCTASK / problem itself | What the flow's failure branch wrote, carrying the action's `Error Message` |
| **Event stream counter** | AAP → Automation Decisions → Event Streams | Whether the POST arrived |
| **Activation log** | AAP → Automation Decisions → Rulebook Activations → the activation | Whether a rule matched, and whether a job launched |

> 🔴 **The stream's `events_received` counter increments even for rejected requests.** A rising
> counter is **not** proof of success. Check the HTTP status, not the counter.

> 🔴 **Events are not queued.** Event streams use PostgreSQL `LISTEN`/`NOTIFY`, which is broadcast
> and **non-durable** — meaning it has no stored backlog. An event posted while the activation is
> down is **dropped silently**, with no retry and no record. Before any test, confirm the activation
> is `Running`.

---

## 1. Symptom index

Find your symptom, go to that section.

| Symptom | Section |
|---|---|
| No flow execution at all; nothing anywhere | [§2.1](#21-no-flow-execution-at-all) |
| Flow ran, exited early, no work note | [§2.2](#22-flow-ran-then-stopped-with-no-work-note) |
| Work note shows `403` (or `401`) | [§3.1](#31-work-note-shows-401-or-403) |
| Work note or curl shows `400 Authorization header is missing` | [§3.1](#31-work-note-shows-401-or-403) |
| Work note shows `400` **or** `404` | [§3.2](#32-work-note-shows-400-or-404--the-event-stream-uuid) |
| Work note shows `Unable to load connection with alias ID:` | [§3.3](#33-unable-to-load-connection-with-alias-id) |
| Work note shows `Request not sent and the REST step reported no error.` | [§3.4](#34-request-not-sent-and-the-rest-step-reported-no-error) |
| Stream counter moves, no job launches | [§4.1](#41-counter-moves-but-no-job-launches) |
| Counter moves, no job, nothing in ServiceNow either | [§4.2](#42-counter-moves-no-job-and-nothing-in-servicenow-either) |
| `Object of type StrictUndefined is not JSON serializable` | [§4.3](#43-object-of-type-strictundefined-is-not-json-serializable) |
| Both teams' rules fire on one event | [§4.4](#44-both-teams-rules-fire-on-one-event) |
| Job runs but variables are empty | [§5.1](#51-job-runs-but-variables-are-empty-or-undefined) |
| Playbook fails `401 "User is not authenticated"` | [§5.2](#52-playbook-fails-with-401-user-is-not-authenticated) |
| Playbook fails on undefined `SN_USERNAME` / `SN_PASSWORD` | [§5.3](#53-playbook-fails-on-undefined-sn_username--sn_password) |
| EDA project stuck on "Pending" | [§6.1](#61-eda-project-stuck-on-pending) |
| `HTTP 503 "Project workers unavailable"` | [§6.2](#62-http-503-project-workers-unavailable) |
| Project syncs but no rulebooks appear | [§6.3](#63-project-syncs-but-no-rulebooks-appear) |
| AAP UI shows a "provisioning" screen, API returns 503 | [§6.4](#64-aap-ui-shows-a-provisioning-screen-and-the-api-returns-503) |
| `Missing container for running activation` | [§6.5](#65-missing-container-for-running-activation) |
| Publishing fails with `Invalid pharmacy compound uuid` | [§7.1](#71-publishing-fails-with-invalid-pharmacy-compound-uuid) |
| `Invalid or missing incident record` | [§7.2](#72-invalid-or-missing-incident-record) |
| A step reports failure but REST returned 200 | [§7.3](#73-a-step-reports-failure-but-the-rest-step-returned-200) |
| `GlideEncrypter is deprecated and now returns null` | [§7.4](#74-glideencrypter-is-deprecated-and-now-returns-null) |
| Flow built but nothing ever runs — **did you Activate it?** | [§2.1](#21-no-flow-execution-at-all) |
| A fix had no effect — **did you Publish the action?** | [§7.5](#75-a-change-had-no-effect--save-is-not-publish) |
| `ERROR! 'sources' is not a valid attribute for a Play` | [§5.4](#54-error-sources-is-not-a-valid-attribute-for-a-play) |
| Activation log says `ansible.eda.webhook`, not `pg_listener` | [§6.6](#66-activation-log-says-ansibleedawebhook-instead-of-pg_listener) |
| Jobs launching for records that should be out of scope | [§4.5](#45-jobs-launch-for-records-that-should-be-out-of-scope) |
| `Rulebook has changed since the sources were mapped` | [§6.7](#67-a-rulebook-edit-appears-to-have-done-nothing) |
| A rulebook edit appears to have done nothing | [§6.7](#67-a-rulebook-edit-appears-to-have-done-nothing) |
| AAP is unreachable and every Deployment has **no pods** | [§6.8](#68-aap-is-completely-down-and-every-deployment-has-no-pods) |
| Events show `ReplicaSetCreateError` or `exceeded quota` | [§6.8](#68-aap-is-completely-down-and-every-deployment-has-no-pods) |

---

## 2. ServiceNow never sent anything

### 2.1 No flow execution at all

**This is the most common failure.** There is no execution to inspect and nothing reports an error,
because as far as ServiceNow is concerned nothing was supposed to happen.

There are three causes. Check them in this order — the first two take seconds and are what a
first-time builder usually hits:

1. **Is the flow Activated?** Open it and check the status reads **Active**, not Draft. A
   saved-but-inactive flow does not run, and nothing warns you. See
   [06 §7](06-servicenow-flow.md).
2. **Is the action Published?** The flow runs the **last published** version of an action. If you
   only saved, see [§7.5](#75-a-change-had-no-effect--save-is-not-publish).
3. **Does the record match the trigger condition?**
   - Open the flow in Workflow Studio and read its **trigger condition**.
   - Open your test record and compare it field by field.
   - If the condition names a **Caller**, an **Assignment group** or any other field, your test
     record must actually have that value. Creating a record "the normal way" usually will not — on
     the Incident flow the Caller must be `Event Management`.

> ℹ️ **Why cause 3 bites beginners specifically.** The build guides tell you to create a record
> "matching your trigger", but a trigger condition set weeks earlier is invisible from the record
> form. When in doubt, temporarily widen the trigger, confirm the flow fires, then narrow it again.

> ℹ️ **Why this bites beginners specifically.** The build docs tell you to create a record "matching
> your trigger", but a trigger condition set weeks earlier is invisible from the record form. When in
> doubt, temporarily widen the trigger, confirm the flow fires, then narrow it again.

### 2.2 Flow ran, then stopped with no work note

Open the **Executions** tab and find where it stopped. Two legitimate possibilities:

- **It exited at the enrollment gate.** The record's catalog item is not enrolled. This is *correct
  behaviour* — most records are not EDA records, and a quiet exit is the design.
- **It exited at the route gate.** The record's assignment group has no matching route row. This is a
  **misconfiguration** and should be noisy. If your flow exits quietly here, see
  [06 — The Flow](06-servicenow-flow.md) for the separate error path this case needs.

A third, less pleasant possibility: the `Success` pill is wired to the wrong step's output, so the
failure branch never runs. Executions will show the step succeeding with the work-note step skipped.

---

## 3. ServiceNow tried and the POST failed

All of these appear in the **work note** on the record.

### 3.1 Work note shows `401` or `403`

**Treat these as the same problem.** The token in ServiceNow and the token in the AAP Event Stream
credential are not identical.

> ✅ **Measured on this build, 2026-10-07.** A POST carrying a **present but wrong** token returns
> **`403`**. The older guidance hedged between `401` and `403` because nobody had tested it; it is
> `403`. Treat a `401` as the same problem and work the same list — the cause is identical.
>
> Two neighbouring codes, both measured at the same time, mean something different:
>
> | Code | What it actually means |
> |---|---|
> | **`403`** | A token was sent and does **not** match the stream's stored token |
> | **`400`** | **No `Authorization` header at all** — usually a shell variable that expanded to empty, see step 1 |
> | **`400`** | **Or the UUID in the path is not a real stream.** Same code as the missing header, so do not read `400` as "header problem" until you have checked the UUID — see [§3.2](#32-work-note-shows-400-or-404--the-event-stream-uuid) |

Check in this order, cheapest first:

1. **Compare lengths.** `openssl rand -hex 32` always produces **64 characters**. If either side is
   not 64, the paste was truncated.
2. **Check for a prefix.** The ServiceNow API Key value must be the **bare token** — no `Bearer `, no
   scheme, nothing. **Nothing adds a scheme for you**, and nothing should: AAP compares the incoming
   header value against the stored token *verbatim*, so any prefix makes it not match. There is a
   separate **API Key Prefix** field on the credential form; leave it empty. See
   [04 §5](04-servicenow-app.md).
3. **Check for trailing whitespace or a newline** from the copy.
4. **Check the header key** on the AAP credential reads exactly `Authorization`.
5. **Check you are posting to the right team's stream.** Each stream accepts only its own token.

### 3.2 Work note shows `400` or `404` — the event stream UUID

The URL is wrong. Either:

- the `resource_path` pill resolved **empty** — check the matched route row has a value in
  `event_stream_uuid`; or
- the UUID in the route row is **stale**. Rebuilding an event stream or moving it between
  organizations regenerates its UUID. See [09](09-reconnect-after-aap-rebuild.md).

> ✅ **Measured on this build, 2026-10-07: an unknown UUID returns `400`, not `404`.** Posting to a
> well-formed UUID that belongs to no stream, with a **valid** token, returns `400` — and so does a
> path segment that is not a UUID at all.
>
> **This is the trap.** `400` is also what a missing `Authorization` header returns
> ([§3.1](#31-work-note-shows-401-or-403)), so the code alone cannot tell you which you have. After
> an AAP rebuild the UUID is the far more likely cause, because a rebuild regenerates every one of
> them — so **check the route row's `event_stream_uuid` against the live stream before you touch the
> token.** `scripts/verify_team.py` compares those two directly ([08 §5](08-routine-ops.md)).
>
> `404` is kept in this heading because the older guidance predicted it and you may have read that;
> it is not what this build returns.

### 3.3 `Unable to load connection with alias ID:`

Look at what follows `sys_id=` in the message.

- **Nothing after it** — the Connection alias pill is unresolved, or it was **dot-walked to Sys ID**
  instead of fed as a bare reference. Feed the bare pill.
- **A sys_id is present** — that alias exists but could not be loaded; check it has a connection and
  a credential attached.

### 3.4 `Request not sent and the REST step reported no error.`

The request never left the instance, because the connection alias was empty. On a record type with no
enrollment gate, this also means an unrouted record reached the action — the gate is missing.

---

## 4. The event arrived but no job ran

### 4.1 Counter moves but no job launches

The rulebook's condition did not match your payload. Confirm it in the activation log:

```
Event { ... } didn't match any rule and has been immediately discarded
```

Compare two things between payload and rulebook:

- **`event_type`** — the exact string. This is the single most common mismatch; a payload sending
  `incident_created` will never match a rule testing `servicenow.incident.created`.
- **`eda_event_stream_name`** — must equal the event stream's name exactly, e.g. `sn-team-a`.

### 4.2 Counter moves, no job, and nothing in ServiceNow either

The rule matched and tried to launch a job template **that does not exist**. This is silent from the
ServiceNow side — the only evidence is the activation log.

The rulebook finds the template **by name, not by ID**. Compare `run_job_template.name` in the
rulebook against the job template's name in AAP, character for character.

### 4.3 `Object of type StrictUndefined is not JSON serializable`

The rule matched, but the payload is missing a field that the rulebook's `job_args.extra_vars`
references, so the launch request cannot be built. **No job is launched.**

Two fixes, either works:

- send every field the rulebook maps; or
- add `| default('')` to each mapping in the rulebook.

### 4.4 Both teams' rules fire on one event

Both activations are mapped to the **same** event stream. Event streams are **fan-out**, not a queue
— every activation mapped to a stream receives every event. Give each team its own stream.

---

### 4.5 Jobs launch for records that should be out of scope

Automation is running for catalog tasks nobody enrolled. **This fails *open*, so it looks like it is
working** — which is why it can run for a long time before anyone notices.

Two causes, both in the enrollment gate ([06 §2](06-servicenow-flow.md)):

1. **The gate tests `Records is empty` instead of `Count > 0`.** Comparing a record-list object to
   "empty" is a string comparison that is **always false**, so the gate silently never fires and
   every record goes through. This exact bug has shipped in a production build.
2. **A condition set is missing its `is not empty` guard.** A record with no catalog item resolves
   that pill to empty, generating the query `catalog_item=` — which matches **every row whose catalog
   item is empty**, i.e. all the order-guide rows. The gate then passes everything.

**How to confirm which:** open a recent execution for a record that should not have been sent, and
look at the enrollment lookup's actual query and result count in the execution details.

> ⚠️ **Not to be confused with [§4.4](#44-both-teams-rules-fire-on-one-event).** There, *one* event
> reaches several activations. Here, records that should never have produced an event produce one.

---

## 5. A job ran but failed

### 5.1 Job runs but variables are empty or undefined

**Prompt on launch** is not ticked on the job template. Without it the controller silently discards
the `extra_vars` the rulebook sent. See [03 §2.5](03-aap-eda-setup.md).

> ℹ️ A blank `target_team` in the job's `extra_vars` specifically means step 1 of the ServiceNow
> action is missing its `team_code` input — a different problem from this one.

### 5.2 Playbook fails with `401 "User is not authenticated"`

The username or password in the **controller's** ServiceNow credential is wrong or stale. The request
reached the PDI, so the URL and connectivity are fine.

### 5.3 Playbook fails on undefined `SN_USERNAME` / `SN_PASSWORD`

You attached the **built-in** ServiceNow credential type, which injects *environment* variables. This
playbook needs the **custom** type from [03 §1](03-aap-eda-setup.md), which injects *extra vars*.

---

### 5.4 `ERROR! 'sources' is not a valid attribute for a Play`

The job template's **Playbook** field is pointing at a **rulebook** instead of a playbook.

```
ERROR! 'sources' is not a valid attribute for a Play
The error appears to be in '/runner/project/rulebooks/team_c_rulebook.yml'
```

A rulebook is not a playbook — `sources:` and `rules:` are not play keywords. The dropdown offers
both, because the controller project is the same repository that holds the rulebooks, and on a
template you have just named `Team C Incident Handler` the team-named file looks like the obvious
choice.

**Fix:** set **Playbook** to `servicenow_incident_handler.yml`. Every team runs the same playbook;
the per-team file is the *rulebook*, selected on the activation. See
[03 §2.5](03-aap-eda-setup.md) and [Rulebook anatomy §0](rulebook-anatomy.md).

> ⚠️ **Nothing is wrong with your rulebook, your event or your token.** This error names a rulebook
> file, which sends most people to debug the rulebook. It is one field on the job template.

---

## 6. AAP platform problems

### 6.1 EDA project stuck on "Pending"

Also appears as *"Task was stuck in pending state"*.

**Your project configuration is not the problem.** The worker pod that performs the git clone is
being killed for exceeding its memory limit.

> ℹ️ **OOMKilled** means "Out Of Memory, Killed" — the cluster terminates a container that exceeds
> its memory ceiling, instantly and with no error from the program itself. That is why nothing
> mentions memory.

**The fix is the sizing patch in [01 §4](01-provision-aap.md).** Apply that and re-sync. The same
patch with the full mechanism, the API-level checks and the verification sequence is
[AAP platform troubleshooting §3](aap-platform-troubleshooting.md#3-an-eda-project-never-finishes-syncing).

<details>
<summary>Confirming the diagnosis first (read-only, four steps)</summary>

These require cluster access — see [01 §3](01-provision-aap.md) for the `K` shortcut.

**1. Read the project's real error.** Prompt for the password rather than typing it inline, so it
does not land in your shell history:

```bash
read -rsp "AAP admin password: " AAPPW; echo
curl -sk -u "admin:$AAPPW" "https://<your-aap-host>/api/eda/v1/projects/" | python3 -m json.tool
```

Look at `import_state` and `import_error`. An **empty `git_hash`** confirms no clone ever completed.

**2. Find the worker pod** and note its `RESTARTS` count:

```bash
K get pods | grep eda-default-worker
```

**3. Prove it was OOMKilled.** Paste your pod name in place of the example:

```bash
K get pod sandbox-aap-eda-default-worker-7c9f8b6d54-x2kqp -o json | python3 -c "
import sys, json
p = json.load(sys.stdin)
for c in p['spec']['containers']:
    print('container:', c['name'], 'limits:', c.get('resources', {}).get('limits'))
for cs in p['status']['containerStatuses']:
    print('restarts:', cs['restartCount'])
    print('lastState:', json.dumps(cs.get('lastState'), indent=2))
"
```

Expected output when this is the problem:

```
container: eda-default-worker limits: {'cpu': '500m', 'memory': '400Mi'}
lastState: { "terminated": { "reason": "OOMKilled", "exitCode": 137, ... } }
```

`reason: OOMKilled` is the proof.

**4. Watch the clone die.** `--previous` reads the log of the *killed* container, not the running one:

```bash
K logs sandbox-aap-eda-default-worker-7c9f8b6d54-x2kqp --previous | tail -20
```

The log **ends mid-clone** with nothing after it — no error, no stack trace:

```
INFO aap_eda.tasks.project Task started: Sync project
INFO aap_eda.services.project.scm Cloning repository: https://github.com/...
   <nothing after this -- the container was killed>
```

**Before patching, check you have room:**

```bash
K get resourcequota
```

Look at the `compute-deploy` row. On Developer Sandbox `limits.memory` is typically **30Gi** with
plenty unused. The constrained one is usually **`requests.cpu`** — which is why the patch in
[01 §4](01-provision-aap.md) raises memory and leaves CPU requests alone.

</details>

### 6.2 `HTTP 503 "Project workers unavailable"`

**Not a failure.** AAP checks worker health before queuing work, and you asked before the worker
finished starting. Wait for this line in the worker log, then retry:

```
dispatcherd.brokers.pg_notify  Set up pg_notify listening on channel 'default'
```

### 6.3 Project syncs but no rulebooks appear

`import_error` will say *"This project contains no rulebooks."*

Your rulebook is not in `rulebooks/` or `extensions/eda/rulebooks/` **at the repository root**. The
search is **not** recursive — a rulebook in any other directory is invisible.

### 6.4 AAP UI shows a "provisioning" screen and the API returns 503

Two possible causes, and it is worth trying them in this order:

1. **The Developer Sandbox idled your workload.** Retry once or twice — if it comes back, nothing was
   wrong.
2. **The gateway pod is out of memory.** Same class of problem as §6.1, fixed by the same patch —
   `spec.api` is the component involved. See [01 §4](01-provision-aap.md).

### 6.5 `Missing container for running activation`

The Developer Sandbox idled the activation's pod. Restart the activation. This is a sandbox
behaviour, not a fault in your build.

---

### 6.6 Activation log says `ansible.eda.webhook` instead of `pg_listener`

A healthy activation log contains:

```
ansible_rulebook.engine - INFO - load source eda.builtin.pg_listener
```

If it says `ansible.eda.webhook` instead, **the event-stream source mapping did not save.** The
activation is listening on a webhook port that nothing posts to, so events arrive at the stream and
reach nothing.

**Fix:** open the activation, click the **gear icon** beside *Event streams*, map
`ansible.eda.webhook` (left) to your stream (right), save, and restart the activation. See
[03 §2.12](03-aap-eda-setup.md), page 2.

> ℹ️ **Your rulebook is fine.** The source block in the rulebook is a placeholder by design and is
> *meant* to be replaced at run time — see [Rulebook anatomy §4](rulebook-anatomy.md). This is
> wiring, not content.

### 6.7 A rulebook edit appears to have done nothing

You changed a rulebook, pushed it, and the activation still behaves the old way. Or you see:

```
Rulebook has changed since the sources were mapped.
```

**Cause:** the event-stream source mapping is pinned to a specific Git commit. Any edit to the
rulebook changes that commit, so the mapping no longer matches.

**Fix — all four steps, in this order:**

1. **Push** the rulebook change.
2. **Sync** that team's EDA project.
3. **Re-attach** the event stream to the rulebook (§6.6 above).
4. **Restart** the activation.

Skipping step 3 is the usual omission, and it leaves the activation running the previous commit.

> ✅ **Confirm it took:** the activation detail page's **project git hash** matches your latest
> commit. If it still shows the old hash, step 3 or 4 did not apply.

> ℹ️ **Validate condition changes locally first.** This cycle takes minutes; a local run takes
> seconds — see [07 §1](07-end-to-end-test.md).

### 6.8 AAP is completely down and every Deployment has no pods

AAP does not load at all. On the cluster, every AAP Deployment wants one pod and has none, while the
database and cache pods look perfectly healthy.

> ℹ️ **A Deployment is the record saying "keep one copy of this container running".** AAP is made of
> about twelve of them. The database and cache survive because they are **StatefulSets**, which work
> differently — so seeing those two healthy is not evidence that the cluster is healthy. Both terms
> are in the [Glossary](glossary.md).

**Nothing in this one is a pipeline problem**, so it is not diagnosed here. Two strings confirm it,
both from the cluster rather than from AAP:

```bash
K get deploy                                          # every row reads 0/1
K get events --sort-by=.lastTimestamp | grep -i quota  # names the quota that is full
```

If the events mention `ReplicaSetCreateError` or `exceeded quota` naming `count/replicasets.apps`,
the namespace has run out of ReplicaSet slots and no Deployment can start a pod.

**Full diagnosis and the two-command fix:**
[AAP platform troubleshooting §4](aap-platform-troubleshooting.md#4-every-aap-pod-is-gone-and-rollouts-fail-on-quota).
It also explains why applying the §6.1 memory patch is a common trigger.

> ⚠️ **Try the §6.4 retry first if AAP is merely unreachable.** The Developer Sandbox idles workloads
> to zero, which looks identical from outside. §6.8 is for when you have looked at the cluster and the
> Deployments genuinely have no pods.

---

## 7. ServiceNow editing and publishing problems

### 7.1 Publishing fails with `Invalid pharmacy compound uuid`

**The message is meaningless.** It has nothing to do with pharmacies, compounds, or UUIDs. It is
ServiceNow's generic complaint about a **dangling data pill** — a pill referencing a step, input or
output that no longer exists, usually after you deleted or reordered a step.

1. **Check the Error Handler steps first.** They are collapsed by default and easy to forget, so a
   stale pill there survives every edit you made to the main path.
2. Then check any step you recently removed a variable from.
3. Fix the pill, or delete and re-add the affected step, then publish again.

### 7.2 `Invalid or missing incident record`

The action input's name case does not match what the script reads — `inputs.incident_record` versus
`inputs.Incident_record`. The canonical scripts in `docs/scripts/` handle both.

### 7.3 A step reports failure but the REST step returned 200

An output variable that the downstream logic reads was never **declared** on the step. Undeclared
outputs silently vanish — the script can assign to them without error, and nothing downstream ever
sees a value.

Declaring a variable is not the same as mapping a pill; check both.

### 7.4 `GlideEncrypter is deprecated and now returns null`

Expected on current releases. `password2` system properties can no longer be decrypted in script, and
existing values are unrecoverable. Use a Connection & Credential Alias instead — see
[04](04-servicenow-app.md).

---

### 7.5 A change had no effect — Save is not Publish

You edited an action or a flow, saved it, re-tested, and got the **old** behaviour.

| Artifact | Saving is enough? | What the flow actually runs |
|---|---|---|
| **Action** | No | The **last published** version |
| **Flow** | No | Only runs at all once **Activated** |

**Fix:** Publish the action; Activate the flow. Check the status reads **Published** / **Active**,
not Draft.

> 🔴 **This is worse than it sounds, because it wastes the next hour.** You conclude the fix did not
> work, so you go looking for a second bug that does not exist — and any further edits you make are
> also unpublished, so nothing you try appears to help.
>
> **Whenever a fix seems to have no effect, check Published/Active before changing anything else.**

---

## 8. When none of this helps

Work the chain from the start rather than from the error, because the error you can see is often
downstream of the real cause:

1. Is the activation **Running**? If not, every event posted since it stopped is gone.
2. Does the **flow execution** exist? If not, it is the trigger (§2.1).
3. Did the **stream counter** move? If not, ServiceNow never reached AAP (§3).
4. Does the **activation log** show a match? If not, it is the payload (§4.1).
5. Did a **job** start? If not, it is the template name (§4.2).

Each step narrows it to one surface. Guessing at the error message's wording does not.

---

## Self-check

**Did I skip any prerequisite steps?** This is a reference, not a build stage, so it has no steps
and deliberately has no checkpoint — you enter it at whichever section matches your symptom. The
diagnostic blocks that do need prerequisites say so: §6.1's four-step confirmation states that it
needs cluster access and links to [01 §3](01-provision-aap.md) for it.

**Is every command copy-paste ready with context?** Yes. §6.1 prompts for the AAP password with
`read -rsp` rather than putting it in a `curl -u`, so it does not land in shell history, and shows
the literal `reason: OOMKilled` output that confirms the diagnosis. Pod names are shown as examples
with an explicit instruction to substitute your own.

**Would a complete novice understand every single sentence?** The entry points are written for
someone already stuck and short of patience, so §0 names the four places to look before any symptom
is discussed, and §1 is a flat index rather than prose. Terms that a stuck reader meets here first —
pill, dot-walk, `extra_vars` — are in the [Glossary](glossary.md), linked at the top.
