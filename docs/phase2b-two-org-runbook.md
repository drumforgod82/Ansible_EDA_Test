\
# Phase 2b — Building the Two-Organization Topology (Team A / Team B)

**Standalone click-through runbook.** Not part of `README.md` — keep it separate. This is for
the personal lab (ServiceNow PDI `dev211593.service-now.com` + Red Hat Developer Sandbox AAP
**2.7**), not a Centene system. No SOX/change-control framing applies here.

**Gateway:** `https://sandbox-aap-jdrebel2-dev.apps.rm1.0a51.p1.openshiftapps.com`

**Starting state, verified 2026-09-25:** only one organization exists — `Default`. `Team A`
and `Team B` do not exist yet. You are creating both from scratch, plus every object each one
needs, so that a ServiceNow event tagged for Team A can never launch Team B's automation and
vice versa.

> **Portability note:** every AAP-2.7-specific path below (decision environment image tag,
> gateway-mounted Organizations) is called out where it differs from Centene's production 2.6.
> Nothing here should be copied to a 2.6 environment without checking that note first.

---

## Dependency order

Do these in this exact sequence. Each step needs an object the previous step created.

| # | Step | Blocks |
|---|---|---|
| **P** | **Push the working-tree changes to `origin/main`** | **Steps 6 and 7 — both sync from GitHub, not from your disk** |
| 0 | Edit the custom `ServiceNow` credential type to add a `host` input | Step 7 (job template credential) |
| 1 | Generate two distinct event stream tokens | Step 3 (event stream credentials) |
| 2 | Create the `Team A` and `Team B` organizations | Everything below — every object is org-scoped |
| 3 | Create the EDA credentials (per team) | Step 4 (event stream), Step 8 (activation) |
| 4 | Create the event streams `sn-team-a` / `sn-team-b` | Step 8 (activation mapping) |
| 5 | Create the decision environments (per org) | Step 8 (activation) |
| 6 | Create the EDA projects (per org) | Step 8 (rulebook selection) |
| 7 | Create the controller project + job template (per org) | Step 8 (`run_job_template` target) |
| 8 | Create the rulebook activation (per org) and map the event stream | Experiment 1 |

---

## Step P — Push first. Nothing below works until you do

**Do this before Step 6 and Step 7.** Both AAP project syncs pull from **GitHub**, never from
your local disk. Every file this phase depends on is currently uncommitted:

```bash
cd ~/GitHub/Ansible_EDA_Test
git status --short
```

You should see the three new rulebooks as untracked (`??`) and three modified files (` M`):

| File | Needed by | If you skip the push |
|---|---|---|
| `rulebooks/team_a_rulebook.yml` | Step 8a | **Not in the Rulebook dropdown.** You cannot create the activation |
| `rulebooks/team_b_rulebook.yml` | Step 8a | same |
| `rulebooks/catchall_debug_rulebook.yml` | Experiment 4 | Experiment 4 has no instrument |
| `servicenow_incident_handler.yml` | Step 7 | **Silent wrong behaviour — see the warning below** |
| `collections/requirements.yml` | Step 6/7 sync | `ansible.eda` not installed, versions unpinned |
| `README.md` | documentation only | harmless |

Commit and push them, then confirm GitHub actually has them:

```bash
git log --oneline -1 origin/main          # must show your new commit
git ls-tree --name-only origin/main rulebooks/
# expect: catchall_debug_rulebook.yml  my_eda_rulebook.yml
#         team_a_rulebook.yml          team_b_rulebook.yml
```

> ⚠️ **This is the failure that costs you the most time, because it fails silently.**
>
> `origin/main` currently carries the **old** `servicenow_incident_handler.yml` — the version
> that hardcodes the PDI hostname and closes the incident with **no `sn_close_incident` gate**.
> If you sync the Step 7 controller project before pushing, the job template will run that old
> playbook. It looks fine: the debug output is normal and the job goes green. But `SN_HOST` is
> ignored entirely, so Step 0's whole purpose is defeated and the assert never runs — and once
> both teams' activations are live, **both orgs will race to close the same ticket**, which is
> exactly what the gate exists to prevent.
>
> There is no error message for this. The only way to catch it is to push first, or to read the
> synced job's output and confirm the `Assert the ServiceNow host was injected by the
> credential` task actually appears.

> **Note:** re-syncing the *existing* single-org EDA project changes `my_eda_rulebook.yml`'s
> content hash, so that activation's event-stream source mapping must be **re-attached** and the
> activation restarted (see Step 8b). Budget for it — it is not optional.

---

## Step 0 — One-time edit to the custom `ServiceNow` credential type

Both `servicenow_incident_handler.yml` and both team rulebooks now depend on `{{ SN_HOST }}`
being injected as an extra var. The custom `ServiceNow` credential type (README §1.1) currently
defines only `username` and `password` — there is no `host` input and no `SN_HOST` injector.
This is a global edit to the credential *type*, done once, before either team's credential can
carry a host value.

**Nav:** Automation Execution → Infrastructure → Credential Types → `ServiceNow` → Edit

Replace the input and injector configuration with:

```yaml
# Input configuration
fields:
  - type: string
    id: username
    label: Username
  - type: string
    id: password
    label: Password
    secret: true
  - type: string
    id: host
    label: ServiceNow Instance URL
required:
  - username
  - password
  - host
```

```yaml
# Injector configuration
extra_vars:
  SN_USERNAME: "{{ username }}"
  SN_PASSWORD: "{{ password }}"
  SN_HOST: "{{ host }}"
```

**Verification:** the credential type's Edit screen re-opens showing all three fields. Any
credential of this type created *before* this edit will show a blank `host` field — you will
re-create the two team credentials fresh in Step 7, so this is not a problem here, but if you
ever reuse the old single-org `ServiceNow PDI` credential remember it predates this edit.

> ⚠️ **This is now a loud failure, not silence.** `servicenow_incident_handler.yml` has an
> `assert` task that checks `SN_HOST is defined` before anything else runs. If you skip this
> step, both team job templates fail immediately with *"SN_HOST is not set..."* — annoying, but
> at least it tells you what's wrong. Before this assert existed, a missing `SN_HOST` would
> have surfaced deep inside a `uri` task as a raw undefined-variable error.

---

## Step 1 — Generate two distinct event stream tokens

Each team gets its **own** token. Do not reuse the token belonging to the existing single-org
`ServiceNow Event Stream` (UUID `25c68345-7022-48ce-976e-56bd1b4e5fb1`) for either team — that
stream is a separate, older object and is out of scope for this build.

```bash
openssl rand -hex 32   # run once — this is TEAM_A_TOKEN
openssl rand -hex 32   # run again — this is TEAM_B_TOKEN
```

Save both in a password manager, labeled clearly. You will paste `TEAM_A_TOKEN` into exactly
one AAP credential (Step 3) and `TEAM_B_TOKEN` into exactly one other. Nothing in ServiceNow
needs either token for this phase — Phase 2b stops at the AAP side; wiring the ServiceNow Flow
per team is a later phase.

**Verification:** `echo "$TEAM_A_TOKEN" | wc -c` reports 65 (64 hex characters + newline) for
each, and the two values are different from each other.

---

## Step 2 — Create the organizations

Organizations are gateway-level objects shared by Automation Execution and Automation
Decisions — you create each one once, not once per app.

**Nav:** Access Management → Organizations → Create organization

| Field | Team A | Team B |
|---|---|---|
| Name | `Team A` | `Team B` |
| Description | *(optional)* | *(optional)* |

**Verification:** both `Team A` and `Team B` appear in the Organizations list alongside
`Default`, and the Organization dropdown on *any* Automation Execution or Automation Decisions
"Create" form now offers all three.

> ⚠️ **Where you'll see SILENCE if you skip or mis-scope this step:** every object below has an
> Organization field. If you leave an object in `Default` when it should be in `Team A`, nothing
> errors — the object just won't appear in the org-scoped dropdown of a later step, and the
> later step's dropdown will simply look shorter than expected. There is no error message that
> says "wrong organization."

---

## Step 3 — EDA credentials, per team

Two credentials per team: the one that reaches the controller, and the one that authenticates
inbound events. Automation Decisions keeps its own credential store — these are new objects,
not reused from the existing single-org build.

### 3a. AAP Controller credential

**Nav:** Automation Decisions → Infrastructure → Credentials → Create

| Field | Team A | Team B |
|---|---|---|
| Name | `AAP Controller - Team A` | `AAP Controller - Team B` |
| Organization | `Team A` | `Team B` |
| Type | Red Hat Ansible Automation Platform | (same) |
| Host | `https://sandbox-aap-jdrebel2-dev.apps.rm1.0a51.p1.openshiftapps.com/api/controller/` | (same) |
| Username / Password | an account that can launch job templates | (same) |
| Verify SSL | off | off |

Both teams point at the same gateway — there is only one AAP instance in this lab. Creating a
separate credential object per org keeps the activation's org-scoped dropdown populated in
Step 8 without depending on cross-org RBAC visibility.

> ⚠️ The host must end at `/api/controller/`. Adding `/v2/` doubles the version segment and
> every job template lookup 404s.

**Verification:** the credential saves and lists under Automation Decisions → Credentials with
the correct Organization column.

### 3b. Event Stream Token credential

**Nav:** Automation Decisions → Infrastructure → Credentials → Create

| Field | Team A | Team B |
|---|---|---|
| Name | `Event Stream Token - Team A` | `Event Stream Token - Team B` |
| Organization | `Team A` | `Team B` |
| Type | `ServiceNow Event Stream` | `ServiceNow Event Stream` |
| Auth type | `token` | `token` |
| HTTP header key | `Authorization` | `Authorization` |
| Token | `Bearer TEAM_A_TOKEN` | `Bearer TEAM_B_TOKEN` |

> ⚠️ **Use the `ServiceNow Event Stream` type. Do not use the `OAuth2 Event Stream` type.** The
> OAuth2 type validates every inbound event against an RFC 7662 introspection URL. ServiceNow's
> OAuth provider does not expose one. If you pick OAuth2 here, every event is rejected — check
> the credential type on this screen before saving, not after the stream is live.
>
> **Token format is exact:** `Bearer TEAM_A_TOKEN` — capital `B`, one space, no trailing space.
> A lowercase `bearer`, a missing prefix, or two spaces all produce the identical symptom: a
> `403` on the ServiceNow side and an `events_received` counter on the AAP side that still
> climbs (rejected requests count too). A rising counter is not proof the token matched.

**Verification:** the credential saves. You cannot fully verify the token is *correct* until
Step 4's stream exists and you can send a test request — a save success only proves the field
accepted a string.

---

## Step 4 — Create the event streams `sn-team-a` / `sn-team-b`

**Nav:** Automation Decisions → Event Streams → Create event stream

| Field | Team A | Team B |
|---|---|---|
| Name | `sn-team-a` | `sn-team-b` |
| Organization | `Team A` | `Team B` |
| Event stream type | ServiceNow | ServiceNow |
| Credential | `Event Stream Token - Team A` | `Event Stream Token - Team B` |
| Forward events to rulebook activation | ✅ tick | ✅ tick |

> ⚠️ **The Name field is load-bearing, not cosmetic.** Both team rulebooks match on
> `event.meta.eda_event_stream_name == "sn-team-a"` (or `"sn-team-b"`) — a value the platform
> injects from this exact Name field and that a sender cannot forge. If you name the stream
> anything other than `sn-team-a` / `sn-team-b` — different case, a typo, a trailing space — the
> rule condition is false forever. The event stream will show a healthy `events_received` count,
> the activation log will show `Event {...} didn't match any rule and has been immediately
> discarded`, and no error will point you at the Name field. This is the single easiest way to
> get pure SILENCE out of this whole build.

> Forwarding must be ON to select the stream in Step 8's mapping page — a stream with forwarding
> off simply doesn't appear as an option there.

Copy the generated URL and the UUID from the stream's detail page (same page you just created
it on — the URL is displayed after Save):

```
https://sandbox-aap-jdrebel2-dev.apps.rm1.0a51.p1.openshiftapps.com/eda-event-streams/api/eda/v1/external_event_stream/<uuid>/post/
```

Record `<uuid>` for both streams — you'll need it if you ever rebuild either stream (the UUID
regenerates) or when you wire the ServiceNow side in the next phase.

**Verification:** each stream's detail page shows `Forwarding: On` and a `<uuid>` distinct from
`25c68345-7022-48ce-976e-56bd1b4e5fb1` (the existing single-org stream) and distinct from each
other.

---

## Step 5 — Decision environment per org

Same image for both teams — only the Name and Organization differ.

**Nav:** Automation Decisions → Infrastructure → Decision Environments → Create

| Field | Team A | Team B |
|---|---|---|
| Name | `DE Supported RHEL9 - Team A` | `DE Supported RHEL9 - Team B` |
| Organization | `Team A` | `Team B` |
| Image | `registry.redhat.io/ansible-automation-platform-27/de-supported-rhel9:latest` | (same) |
| Credential | Red Hat Registry credential, or leave empty if the cluster's global pull secret already covers `registry.redhat.io` — the existing single-org DE reached `Running` on this same image, per its activation log, which is a strong sign the pull is already covered in this sandbox, but that has not been separately re-confirmed for a brand-new org-scoped DE object | (same) |

> On AAP **2.6** (Centene production) the image path is `ansible-automation-platform-26/...`
> instead of `-27`. Do not carry the `-27` tag across environments.

**Verification:** the object saves with `Image: ...de-supported-rhel9:latest` visible. A
Decision Environment is not needed for a project sync to succeed — only for an activation to
run — so you cannot fully verify the image pulls until Step 8.

---

## Step 6 — EDA project per org

Both projects point at the **same** GitHub repo and branch as the existing single-org project —
only the Name and Organization are new.

**Nav:** Automation Decisions → Projects → Create project

| Field | Team A | Team B |
|---|---|---|
| Name | `Ansible EDA Test - Team A` | `Ansible EDA Test - Team B` |
| Organization | `Team A` | `Team B` |
| Source control type | Git | Git |
| Source control URL | `https://github.com/<you>/Ansible_EDA_Test.git` | (same) |
| Branch | `main` | `main` |
| Credential | empty (public repo) | empty (public repo) |

Wait for **Completed**, then check Automation Decisions → Rulebooks (filtered to this project).
You should see **all four** rulebook files in the repo's `rulebooks/` directory —
`my_eda_rulebook.yml`, `team_a_rulebook.yml`, `team_b_rulebook.yml`, and
`catchall_debug_rulebook.yml` — because discovery is per-project, not per-team. Nothing filters
the list to "your" rulebook for you; you pick the right file by hand in Step 8.

> ⚠️ `catchall_debug_rulebook.yml` matches **every** event on purpose (it's the Experiment 4
> instrument, marked for deletion after that experiment). Do not select it for either team's
> production-style activation in Step 8 — if it ends up attached to a real stream it fires
> forever, which is the opposite of silence but just as wrong.

If a project sticks at **Pending** or fails with *"Task was stuck in pending state,"* that's the
known OOMKilled worker pod issue, not a problem with these field values — see
`aap-eda-project-sync-fix.md` in this repo.

**Verification:** each project shows **Completed** with a non-empty `git_hash`, and its
Rulebooks list includes the team-specific file you'll select next.

---

## Step 7 — Controller project + job template, per org

### 7a. Controller project

> ⚠️ **Confirm [Step P](#step-p--push-first-nothing-below-works-until-you-do) is done first.**
> This project supplies the playbook the job template runs, and it syncs from GitHub. If the
> corrected `servicenow_incident_handler.yml` has not been pushed, you get the old one — which
> ignores `SN_HOST` and closes incidents with no gate — and **the job still goes green**.

**Nav:** Automation Execution → Projects → Create project

| Field | Team A | Team B |
|---|---|---|
| Name | `EDA ServiceNow - Team A` | `EDA ServiceNow - Team B` |
| Organization | `Team A` | `Team B` |
| Source control URL | `https://github.com/<you>/Ansible_EDA_Test.git` | (same) |
| Branch | `main` | `main` |
| Credential | empty (public repo) | empty (public repo) |

Sync it — `collections/requirements.yml` (`servicenow.itsm` 2.16.0, `ansible.eda` 2.13.0)
installs automatically, same as the existing single-org project.

**Verification:** Completed sync with a non-empty `git_hash`. Note this project's `git_hash`
will generally differ from the EDA project's `git_hash` in Step 6 unless you synced both at
literally the same commit — that mismatch is expected and matches the existing single-org build
(`EDA ServiceNow` at `798a684` vs `Ansible EDA Test` at `81a1695` today).

### 7b. ServiceNow credential (per org)

**Nav:** Automation Execution → Infrastructure → Credentials → Create

| Field | Team A | Team B |
|---|---|---|
| Name | `ServiceNow PDI - Team A` | `ServiceNow PDI - Team B` |
| Organization | `Team A` | `Team B` |
| Type | `ServiceNow` (the type edited in Step 0) | (same) |
| Host | `https://dev211593.service-now.com` (include `https://`) | (same) |
| Username / Password | your PDI admin credentials | (same) |

Both teams point at the same PDI in this lab — there's only one ServiceNow instance. Two
credential objects still matter because `sn_close_incident` defaults to `false` specifically so
two teams sharing one PDI don't race to close the same ticket; giving each team its own
credential object keeps that isolation intentional rather than accidental.

> ⚠️ If you create this credential *before* Step 0's edit, the `host` field won't exist on the
> form at all — you'll only see Username/Password. Go back and do Step 0 first.

**Verification:** the credential saves with all three fields populated, `host` included.

### 7c. Job template (per org)

**Nav:** Automation Execution → Templates → Create template → Create job template

| Field | Team A | Team B |
|---|---|---|
| Name | `Team A Incident Handler` — **must match the rulebook's `run_job_template.name` exactly** | `Team B Incident Handler` — same rule |
| Organization | `Team A` | `Team B` |
| Job type | Run | Run |
| Inventory | `Demo Inventory` (must contain `localhost`) | (same) |
| Project | `EDA ServiceNow - Team A` | `EDA ServiceNow - Team B` |
| Playbook | `servicenow_incident_handler.yml` | (same) |
| Execution environment | Default execution environment | (same) |
| Credentials | `ServiceNow PDI - Team A` | `ServiceNow PDI - Team B` |
| **Prompt on launch** (next to Extra variables) | ✅ **REQUIRED** | ✅ **REQUIRED** |

> ⚠️ **This is the single most important checkbox in the whole build, and it fails silently.**
> Without **Prompt on launch**, the controller discards `job_args.extra_vars` sent by
> `run_job_template` before the job ever starts. The job launches, runs, and finishes — no
> error anywhere — with every variable undefined. You confirmed this is real by checking
> Job Template 8 (`ServiceNow Incident Handler`, the existing single-org template) via the API:
> `ask_variables_on_launch: true` is what makes its `extra_vars` survive. Set it the same way
> here, for both new templates.

**Verification:** launch each template manually once with a hand-typed extra var (e.g.
`incident_number: TEST-0001`) before wiring the rulebook to it. The **Details** tab of the
resulting job should echo `TEST-0001` back in the "Display incident information" task output.
If it shows `incident_number: ` (empty), Prompt on launch isn't actually ticked — go back and
check it, then re-launch.

---

## Step 8 — Rulebook activation per org

### 8a. Create the activation

**Nav:** Automation Decisions → Rulebook Activations → Create rulebook activation

**Page 1 — details:**

| Field | Team A | Team B |
|---|---|---|
| Name | `ServiceNow Incidents - Team A` | `ServiceNow Incidents - Team B` |
| Organization | `Team A` | `Team B` |
| Project | `Ansible EDA Test - Team A` | `Ansible EDA Test - Team B` |
| Rulebook | `team_a_rulebook.yml` | `team_b_rulebook.yml` |
| Credential | `AAP Controller - Team A` | `AAP Controller - Team B` |
| Decision environment | `DE Supported RHEL9 - Team A` | `DE Supported RHEL9 - Team B` |
| Restart policy | On failure | On failure |
| Log level | Debug (drop to Info once confirmed) | Debug |
| Skip audit events | leave unchecked | leave unchecked |

> ⚠️ Pick the file that actually says "Team A" in its own header comment
> (`team_a_rulebook.yml`), not `my_eda_rulebook.yml` (the original single-org file) and not
> `catchall_debug_rulebook.yml`. All four are legitimately selectable here — the project sync
> doesn't know which one belongs to which team, only the filename tells you.

### 8b. Map the event stream — Page 2

Click the gear icon next to Event streams, then map:

| | Team A | Team B |
|---|---|---|
| Left (rulebook source) | `ansible.eda.webhook` | `ansible.eda.webhook` |
| Right (event stream) | `sn-team-a` | `sn-team-b` |

Save the mapping. This replaces the placeholder webhook source with the server-side stream —
the rule condition text is unchanged.

> ⚠️ **Source mappings are pinned to a SHA256 of the rulebook file at mapping time.** If you
> edit `team_a_rulebook.yml` after this point and restart the activation without re-syncing the
> EDA project *and* re-attaching this mapping first, the activation fails outright with
> `Rulebook has changed since the sources were mapped. Please reattach event streams.` — at
> least that one is a loud error, not silence. The cycle for every future edit to either team's
> rulebook is: edit → commit → push (James does this) → sync `Ansible EDA Test - Team A` (or
> `- Team B`) → re-attach that team's mapping → restart that team's activation. Editing Team A's
> file does not require touching Team B's mapping, and vice versa — they are independent
> per-activation pins, not a project-wide lock.

**Page 3 — review.** Confirm *Enable rulebook activation* is ticked, then Create.

### 8c. Verify

Open the activation's log for each team and confirm both lines appear, in order:

```
ansible_rulebook.engine - INFO - load source eda.builtin.pg_listener
```

```
ansible_rulebook.rule_set_runner - INFO - Waiting for events, ruleset: Team A - ServiceNow incident automation
```

(Team B's ruleset name is `Team B - ServiceNow incident automation`, from that rulebook's own
`name:` field.)

The first line is the proof the event stream replaced the placeholder `ansible.eda.webhook`
source — if it still says `load source ansible.eda.webhook`, the Page 2 mapping either wasn't
saved or wasn't attached to this activation.

> ⚠️ **Restarts caused by the Controller cold-starting look identical to a real problem but
> aren't one.** Confirmed root cause in this sandbox: on activation start, `ansible-rulebook`'s
> `job_template_runner` validates the Controller connection *before* it will serve events. If
> the Controller pod is cold, that validation gets five `HTTP 503` responses (`aiohttp_retry`,
> 5 attempts), the readiness check times out around 65s, and the activation restarts — up to 10
> times observed. If you also see restarts ending in *"Missing container for running activation.
> Pod id: ..."*, that's the Red Hat Developer Sandbox's idler deleting the pod for being idle,
> a second, unrelated cause. Neither is memory or CPU pressure. If a fresh activation is
> restart-looping, check the Controller's own pod status before touching anything in this
> runbook.

---

## Pre-flight checklist before Experiment 1

Run through all of these before sending a single test event. Every item is something this
runbook built — if any box is unchecked, stop and fix it here rather than debugging from the
ServiceNow side.

- [ ] `Team A` and `Team B` organizations exist and are visible in both Automation Execution
      and Automation Decisions org pickers.
- [ ] The `ServiceNow` credential type (Step 0) shows `username`, `password`, **and `host`**
      inputs, with an `SN_HOST` injector.
- [ ] `TEAM_A_TOKEN` and `TEAM_B_TOKEN` are two different 64-character hex strings, neither
      equal to the token behind the existing `ServiceNow Event Stream` (UUID
      `25c68345-7022-48ce-976e-56bd1b4e5fb1`).
- [ ] Both Event Stream Token credentials store the value as `Bearer <token>` — capital `B`,
      one space — not the raw hex string alone.
- [ ] Both Event Stream Token credentials use the `ServiceNow Event Stream` type, **not**
      `OAuth2 Event Stream`.
- [ ] `sn-team-a` and `sn-team-b` both show `Forwarding: On` and distinct UUIDs.
- [ ] Both decision environments show the `de-supported-rhel9:latest` image and, on first
      activation start, actually pulled it (check the pod events, not just the object's saved
      config).
- [ ] Both EDA projects (`Ansible EDA Test - Team A` / `- Team B`) show **Completed** with a
      non-empty `git_hash`, and each one's Rulebooks list includes its team's rulebook file.
- [ ] Both controller projects (`EDA ServiceNow - Team A` / `- Team B`) show **Completed**.
- [ ] Both job templates have **Prompt on launch** ticked — verified by a manual launch with a
      hand-typed extra var that echoed back correctly, not just by looking at the checkbox.
- [ ] Both ServiceNow credentials (`ServiceNow PDI - Team A` / `- Team B`) have a non-empty
      `host` field including the `https://` scheme.
- [ ] Both activations are **Running**, each selecting its own team's rulebook file (not
      `my_eda_rulebook.yml`, not `catchall_debug_rulebook.yml`).
- [ ] Both activation logs show `load source eda.builtin.pg_listener` and end with
      `Waiting for events, ruleset: Team <X> - ServiceNow incident automation`.
- [ ] `catchall_debug_rulebook.yml` is attached to **neither** activation — it stays unattached
      until Experiment 4 specifically calls for it, and gets deleted from the repo afterward.
- [ ] You have both stream POST URLs and UUIDs recorded somewhere outside this runbook, ready
      for whichever manual test tool (`curl`, Postman) you use to fire the first test event
      without involving ServiceNow yet — mirroring how the existing single-org build was first
      tested (README §5.1) before any Flow Designer wiring existed.
