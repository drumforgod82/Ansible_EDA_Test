# 07 — Testing end to end

**This document covers proving the pipeline works by testing one layer at a time, so that when
something fails you already know which layer to look at.**

> **Previous stage:** [06 — The Flow](06-servicenow-flow.md) · **Next stage:**
> [08 — Routine ops](08-routine-ops.md)
>
> **Time:** 15 minutes for the layers that matter, plus an optional hour if you set up local rulebook
> testing.

> **Any unfamiliar word?** Every term and acronym used in these guides is defined in the
> [Glossary](glossary.md) — including AAP, EDA, PDI, SCTASK, data pill, dot-walk, work note
> and `extra_vars`.

---

## 0. Why test in layers

The pipeline has five hops: ServiceNow flow → ServiceNow action → event stream → rulebook → job
template. A single end-to-end test that fails tells you only that *something* is wrong across all
five.

So test each hop separately, cheapest first. Each layer you pass eliminates everything below it.

| § | Layer | Needs |
|---|---|---|
| [1](#1-layer-1--rulebook-logic-on-your-laptop-optional) | Rulebook conditions | Your laptop only. **Optional** |
| [2](#2-layer-2--the-event-stream-and-token) | Stream URL + token | AAP only, no ServiceNow |
| [3](#3-layer-3--the-job-template-alone) | Job template | AAP only |
| [4](#4-layer-4--the-full-chain) | Everything | Both platforms |

> 🔴 **Before any test that involves AAP, confirm the activation is `Running`.** Event streams use
> PostgreSQL `LISTEN`/`NOTIFY`, which is broadcast and **non-durable** — it has no stored backlog. An
> event posted while the activation is down is **dropped silently**, with no retry and no record of
> it. A test against a stopped activation looks identical to a broken payload.

---

## 1. Layer 1 — rulebook logic on your laptop (optional)

**Skip this unless you are editing rulebook conditions.** It is the cheapest feedback loop *once set
up*, but setting it up is the most expensive step in this document. If you are following the build
for the first time, go to [§2](#2-layer-2--the-event-stream-and-token).

The value: changing a rulebook in AAP means push → sync → re-attach → restart, which takes minutes.
Locally it takes seconds.

### 1.1 Install a Java runtime

`ansible-rulebook` embeds a Java rule engine, so Java must be present before anything else works.
On macOS with Homebrew:

```bash
brew install openjdk@17
```

> ℹ️ **The path in the next step is Homebrew-on-Apple-Silicon specific.** On Intel macOS the prefix
> is `/usr/local` instead of `/opt/homebrew`. On Linux, install OpenJDK 17 with your package manager
> and use whatever `readlink -f "$(command -v java)"` reports. Any OpenJDK 17 works.

### 1.2 Set up the Python environment

Run this from anywhere; the example uses a directory beside the repo.

```bash
mkdir -p ~/eda-local-test && cd ~/eda-local-test
python3 -m venv venv
source venv/bin/activate
pip install ansible-core ansible-rulebook
ansible-galaxy collection install ansible.eda servicenow.itsm
export JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home
```

Confirm both pieces are in place:

```bash
ansible-rulebook --version
echo "$JAVA_HOME"
```

Expected output — a version line, then the path you exported:

```
ansible-rulebook [0.x.y]
  ...
/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home
```

An **empty second line** means `JAVA_HOME` did not take, and `ansible-rulebook` will fail with a Java
error rather than a clear message.

> ⚠️ **Use `source venv/bin/activate`; do not call the binary by its full path.**
> `ansible-rulebook` shells out to `ansible-galaxy` and finds it on `PATH`. Running
> `~/eda-local-test/venv/bin/ansible-rulebook` directly leaves `PATH` untouched and fails with
> *"ansible-galaxy is not installed"* — which sounds like a missing package rather than a `PATH`
> problem.

> ℹ️ **`export` and `source` last only for this terminal window.** Open a new one and you must re-run
> both the `source` and the `export`.

### 1.3 Use the harness shipped in this repo

Two files in [`local-test/`](../local-test/) are ready to run — you do not have to write them:

| File | What it is |
|---|---|
| [`local-test/rulebook_logic_only.yml`](../local-test/rulebook_logic_only.yml) | A copy of the incident rulebook with two changes, described below |
| [`local-test/inventory.yml`](../local-test/inventory.yml) | A five-line inventory with one host, `localhost`, connecting locally |

The rulebook differs from a real one in exactly two ways, and this is the pattern to copy if you
write your own:

- The source is **`ansible.eda.generic`** instead of `ansible.eda.webhook`, carrying two fixed
  ServiceNow-shaped payloads inline rather than listening on a port.
- The action is **`debug`** instead of `run_job_template`, so it prints the variables a job would
  have received instead of launching one.

**It carries two events on purpose:** one with `event_type: incident_created` that the condition
matches, and one with `event_type: incident_updated` that it must not. Without the second you cannot
tell a correct condition from one that passes everything.

> ⚠️ **Why the real rulebook will not work for this.** `ansible-rulebook` validates that
> `run_job_template` has controller credentials **before it emits any events**, so a run without
> credentials exits immediately and never exercises your rules. That looks like a silent pass.

### 1.4 Run it

```bash
cd /path/to/Ansible_EDA_Test
source ~/eda-local-test/venv/bin/activate
export JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home
ansible-rulebook --rulebook local-test/rulebook_logic_only.yml -i local-test/inventory.yml --print-events
```

Expected output — the `MATCHED` block once, listing the variables, and **nothing** for the second
event:

```
MATCHED - these are the extra_vars the job template would receive:
incident_number   = INC0010001
short_description = Disk space low on server
...
```

> ✅ **Verify:** the debug output appears **once**. If it appears twice, the condition is matching the
> `incident_updated` event too and is too loose — fix it here, where the loop is seconds rather than a
> push-sync-reattach-restart cycle.

### 1.5 Optional — the playbook against ServiceNow, with no AAP

You can run `servicenow_incident_handler.yml` straight at your instance to test the playbook and its
write-back in isolation. In AAP the credential supplies the three `SN_*` variables; running by hand,
you pass them yourself.

Prompt for the password so it does not land in your shell history, then run against a **real**
incident's `sys_id`:

```bash
cd /path/to/Ansible_EDA_Test
read -rsp "ServiceNow password: " SNPW; echo
ansible-playbook servicenow_incident_handler.yml \
  -i local-test/inventory.yml \
  -e SN_HOST="https://<your-pdi>.service-now.com" \
  -e SN_USERNAME="admin" \
  -e SN_PASSWORD="$SNPW" \
  -e incident_number="INC0010001" \
  -e sys_id="<a-real-incident-sys_id>"
```

Expected output: the debug tasks print the values back, and the write-back task reports `changed`.

> ⚠️ **`SN_HOST` must include `https://`.** The playbook builds URLs by string concatenation, so
> without the scheme you get a malformed URL rather than a clear error. Same rule as
> [03 §1](03-aap-eda-setup.md).

> ℹ️ **This does *not* close the incident by default.** The playbook sets `sn_close_incident: false`
> deliberately, because two organisations pointed at one instance would otherwise race to close the
> same ticket. The close only happens if you add `-e sn_close_incident=true` — and **then** it is
> destructive, so use a disposable ticket.

---

## 2. Layer 2 — the event stream and token

This proves the URL and the token with **no ServiceNow involvement at all**.

First make the token available without typing it:

```bash
export EDA_TOKEN="$(security find-generic-password -a "$USER" -s sandbox-eda-team-c -w)"
echo "${#EDA_TOKEN}"
```

Expected output: `64`. Anything else means the variable did not resolve, and the test below will fail
for that reason rather than for a token mismatch.

> 🔑 **Reference the token; never paste it.** Typing the literal hex into a command puts a live
> credential into your shell history — the one copy nobody remembers to rotate. The value is the
> **bare** token, with no `Bearer ` prefix.

Now post a test event. Substitute your own host and the UUID from the team's route row:

```bash
curl -sk -X POST -w '\nHTTP:%{http_code}\n' \
  -H 'Content-Type: application/json' \
  -H "Authorization: $EDA_TOKEN" \
  'https://<your-aap-host>/eda-event-streams/api/eda/v1/external_event_stream/<uuid>/post/' \
  -d '{"event_type":"incident_created","incident_number":"CURLTEST","short_description":"test","priority":"3","cmdb_ci":"host01","state":"New","assigned_to":"admin","category":"Inquiry","sys_id":"0000000000000000000000000000test"}'
```

Expected output:

```
HTTP:200
```

### 2.1 Reading the result

All four codes below were **measured against this build on 2026-10-07**, so they are what it really
returns rather than what the older guidance predicted:

| Result | Meaning |
|---|---|
| `200` | The token and URL are both correct. **This is a pass** |
| `403` | **Token mismatch** — a token was sent and is not byte-identical to the stored one. Includes the case where it carries a `Bearer ` prefix |
| `400` | **Either** no `Authorization` header was sent at all — most often `$EDA_TOKEN` was unset and expanded to empty — **or** the UUID in the path belongs to no stream. **One code, two causes** |
| `404` | **Not what this build returns.** The older guidance predicted it for a bad UUID; that case is a `400` |

> 🔴 **`400` is ambiguous and that is the thing to remember here.** A missing header and a dead UUID
> are the same code. Check `echo "${#EDA_TOKEN}"` prints `64` first, because that is the cheaper of
> the two to rule out; then check the UUID against the live stream.

> 🔴 **Expect `200` and *no job*. That is the correct result, not a half-failure.**
>
> The `event_type` in that payload is `incident_created`, and the live rulebooks match
> `servicenow.incident.created`. So the stream **accepts** the event and then **no rule matches it.**
> That is deliberate: it proves the token and URL without launching real automation against a fake
> `sys_id`.
>
> So you should also see no movement in the activation's `Last rule fired`. If you want the whole
> chain to fire, change `event_type` to `servicenow.incident.created` — and use a **real** incident
> `sys_id`, because the playbook will then try to write back to it.

> ⚠️ **Send every field the rulebook maps.** A minimal two-field payload will match the rule and then
> fail at launch with `Object of type StrictUndefined is not JSON serializable`, which is a different
> and more confusing failure than the one you are testing for.

> ✅ **SETTLED 2026-10-07 — this was an open question and is no longer.** A bad token returns
> **`403`**, not `401`. Measured with the three commands below against the live `sn-team-c` stream;
> you do not need to re-run them, but they are the cheapest way to re-confirm on a rebuilt instance.
>
> ```bash
> # 1. present but wrong token  -> 403
> curl -sk -X POST -o /dev/null -w 'HTTP:%{http_code}\n' \
>   -H 'Content-Type: application/json' -H "Authorization: deliberately-wrong-token" \
>   'https://<your-aap-host>/eda-event-streams/api/eda/v1/external_event_stream/<uuid>/post/' \
>   -d '{"event_type":"probe"}'
>
> # 2. no Authorization header at all  -> 400
> curl -sk -X POST -o /dev/null -w 'HTTP:%{http_code}\n' \
>   -H 'Content-Type: application/json' \
>   'https://<your-aap-host>/eda-event-streams/api/eda/v1/external_event_stream/<uuid>/post/' \
>   -d '{"event_type":"probe"}'
>
> # 3. valid token, UUID that belongs to no stream  -> 400  (NOT 404)
> curl -sk -X POST -o /dev/null -w 'HTTP:%{http_code}\n' \
>   -H 'Content-Type: application/json' -H "Authorization: $EDA_TOKEN" \
>   'https://<your-aap-host>/eda-event-streams/api/eda/v1/external_event_stream/00000000-0000-0000-0000-000000000000/post/' \
>   -d '{"event_type":"probe"}'
> ```
>
> All three are safe: none of them can launch automation, because a rejected request never reaches a
> rulebook. Note that case 1 **still increments the stream's `events_received` counter** — a rising
> counter is not proof of success.

> ℹ️ **The `-k` flag skips TLS certificate checking.** That is appropriate for a sandbox with
> self-signed certificates and should not be carried into anything real.

---

## 3. Layer 3 — the job template alone

This proves the template, its credentials and its prompt-on-launch setting, independently of EDA.

Go to **Automation Execution → Templates → `Team <X> Incident Handler` → Launch**, and supply extra
variables by hand:

```yaml
incident_number: SMOKETEST0001
short_description: disk space check
priority: "3"
cmdb_ci: none
state: New
assigned_to: admin
category: Inquiry
sys_id: 0000000000000000000000000000test
```

> ✅ **Verify:** the debug tasks print your values back. If they print nothing, **Prompt on launch**
> is not ticked on the template — see [03 §2.5](03-aap-eda-setup.md).

The ServiceNow write-back will fail with that fake `sys_id`. **That is the intended outcome** — it
proves nothing was written to your instance.

> ℹ️ **Templates are named per team *and* per record type**: `Team A Incident Handler`,
> `Team A SCTASK Handler`, `Team A Problem Handler`. There is no template called plain
> `ServiceNow Incident Handler`.

---

## 4. Layer 4 — the full chain

Create a record in ServiceNow that matches your flow's trigger, then check these four places **in
this order**. Each one that looks right eliminates everything before it.

1. **ServiceNow — Flow Designer → Executions → your run.** The REST step should show `200`.
2. **AAP — Automation Decisions → Rulebook Activations → your activation → History → the running
   instance.** With Log level **Debug** you see the exact JSON that arrived, logged as
   `received event {...}`.
3. **The same activation log** should then show `run_job_template` and a line of the form:

   ```
   Job Launched, url: /api/controller/v2/jobs/<n>/
   ```

4. **Automation Execution → Jobs.** The job appears, with `extra_vars` populated and an
   `ansible_eda` block recording the ruleset, the rule and the event UUID.

> 🔴 **Make sure your test record actually matches the trigger.** On the Incident flow the trigger
> also requires the **Caller** to be `Event Management`, so an incident raised the ordinary way never
> starts the flow — and there is no execution to inspect and no error anywhere. See
> [06 §1.2](06-servicenow-flow.md).

> ℹ️ **If forwarding is turned off** on the event stream, events are stored on the stream's **Events**
> tab instead, where you can read the raw JSON — but **no rulebook runs and no job launches**. The two
> modes are mutually exclusive. See [03 §2.11](03-aap-eda-setup.md).

---

## 5. Reading the activation counters

The activation log emits periodic `SessionStats`. These four numbers localise a failure faster than
reading the log itself.

| Counter | Meaning |
|---|---|
| `eventsProcessed` | Events the rule engine received |
| `eventsMatched` | Events that satisfied a condition |
| `eventsSuppressed` | Events discarded because no rule matched |
| `rulesTriggered` | Actions that actually fired |

How to read them:

- **`eventsProcessed: 0` after a successful POST** — the event never reached the rulebook. Check the
  event stream mapping on the activation ([03 §2.12](03-aap-eda-setup.md), page 2).
- **`eventsProcessed` rising but `rulesTriggered` stays 0** — the event arrived and matched nothing.
  That is a payload-versus-condition problem; check `event_type` first
  ([05 §7](05-servicenow-action.md)).
- **`rulesTriggered` rising but no job in AAP** — the rule fired and the job template it names does
  not exist. The name is matched exactly, character for character.

---

## 6. What "nothing happened at all" means

If no counter moved, no execution exists and nothing logged anywhere, work the chain from the
**start**, not from the error — because there is no error.

1. Is the activation **Running**? If not, everything posted since it stopped is gone (§0).
2. Does a **flow execution** exist? If not, the record did not match the trigger.
3. Did the **stream counter** move? If not, ServiceNow never reached AAP.
4. Did `eventsProcessed` move? If not, the stream is not mapped to the activation.

Full symptom catalogue in [10 — Troubleshooting](10-troubleshooting.md).

---

## Checkpoint

- [ ] The activation is **Running** before you test anything
- [ ] Layer 2 returns `HTTP:200`
- [ ] You understand why layer 2 launches **no job**, and that this is a pass
- [ ] Layer 3 prints your extra variables back
- [ ] Layer 4 shows `200` in Executions, `received event` in the activation log, a `Job Launched`
      line, and a job with populated `extra_vars`
- [ ] A work note appeared on the record

**Next:** [08 — Routine ops](08-routine-ops.md).

---

## Self-check

**Did I skip any prerequisite steps?** No. The activation-must-be-Running precondition is in §0
rather than buried, because every later layer silently depends on it. §1 now carries real setup
commands — the older version described a virtualenv, two collections and a `JAVA_HOME` without
giving a single command, while calling itself the cheapest step.

**Is every command copy-paste ready with context?** Yes. Each shows its working directory where it
matters, each states expected output, and the token is referenced through a variable with a length
check so an unset variable is distinguishable from a wrong token. Placeholders are limited to
`<your-aap-host>` and `<uuid>`, both defined where they appear.

**Would a complete novice understand every single sentence?** The counterintuitive part is §2's
deliberately-wrong `event_type`, where success means "accepted and ignored". That is stated three
times — in the warning, in the result table, and in the checkpoint — because a beginner's instinct is
to treat a missing job as a failure and start debugging a pipeline that is working.
