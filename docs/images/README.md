# Screenshots

Screenshots displayed by the numbered build guides — [03](../03-aap-eda-setup.md),
[04](../04-servicenow-app.md), [05](../05-servicenow-action.md), [06](../06-servicenow-flow.md) and
[09](../09-reconnect-after-aap-rebuild.md) — plus
[Adding a record type](../adding-record-types.md), the
[OAuth appendix](../appendix-oauth-direct-launch.md) and the root [README](../../README.md).

## Files kept on disk but not displayed

**Verified 2026-10-07: 52 PNGs on disk, 48 displayed, 4 not displayed.** All four are listed below so
the inventory reconciles — **not** because a page is missing an image. Re-check with:

```bash
cd /path/to/Ansible_EDA_Test
comm -13 <(grep -ohrE '\]\([^)]*images/[^)]+\.png\)' --include="*.md" . | sed 's/.*images\///;s/)$//' | sort -u) \
         <(ls docs/images/*.png | xargs -n1 basename | sort)
```

### Superseded by a newer capture

| File | Why it is not displayed |
|---|---|
| `50-sn-action-inputs.png` | Superseded by `72-sn-action-inputs-four.png` — shows only the Incident Record input, from before the action took four |
| `50.1-sn-script-step-inputs.png` | Superseded by `73-sn-step1-input-vars.png`, which covers step 1's input variables including `team_code`. This one pre-dates that input |
| `54-sn-action-outputs.png` | Superseded by `77-sn-action-outputs.png` — shows the older output wiring |
| `61-sn-flow-action-input.png` | Superseded by `76-sn-flow-action-pills.png` — pre-dates the four-input action step |

### Resolved 2026-10-07 — four of the five README-split orphans are now displayed

Five flow screenshots were orphaned when the old single-file `README.md` became
[01](../01-provision-aap.md)–[10](../10-troubleshooting.md), because the rewritten
[06 — The Flow](../06-servicenow-flow.md) builds the flow from text. **Four were reviewed image by
image and placed in `06`; one was rejected.**

| File | Where it is now displayed | What it is actually good for |
|---|---|---|
| `60-sn-flow-trigger.png` | [06 §1.2](../06-servicenow-flow.md) | The **current** flow (`Incident-EDA`), showing both halves of the trigger condition and *Run flow in background* under expanded Advanced Options |
| `63-sn-flow-update-record.png` | [06 §5](../06-servicenow-flow.md) | The one image of a **work-note field mixing typed text with a dragged pill** — the thing `06`'s own self-check says cannot be pasted |
| `64-sn-flow-end-flow.png` | [06 §5](../06-servicenow-flow.md) | **Renamed** from `64-sn-flow-log-info.png`. The old name and description were wrong: there is **no Log step in it**. It is an arrow pointing at `End Flow` inside the `then` branch, which is exactly the point `06 §5` makes |
| `66-sn-flow-error-handler.png` | [06 §6](../06-servicenow-flow.md) | The Error Handler **toggle in its on state**, with a step nested inside it. The toggle is the part people miss |

> 🔴 **Three of those four show a flow with no route gate**, because that is how the live flow was
> built — step 1 *Look Up* goes straight to step 2 *Send*, with no `If Sys ID is not empty` and no
> Else branch. Every caption in `06` says so explicitly. **If you recapture any of them, do not
> reproduce that shape** — build the gate from
> [06 §3.2](../06-servicenow-flow.md#32-the-sys-id-gate) first, then capture.

### Deleted 2026-10-07 — reviewed, obsolete, removed

Both are in git history. Neither was displayed by any page.

| File | Why it was deleted |
|---|---|
| `62-sn-flow-if-success.png` | **Obsolete four ways at once.** The flow was named `…on Incident` not `…on Incident-EDA`; the Workflow Studio tabs read **`Flow • Global`**, contradicting the scope check `06 §1` opens with; the trigger showed only the `Caller` half of its condition; and there was no route lookup. It also carried an *Autosave error* state. Its only unique content — the `If` on the action's `Success` output — is covered by `64` |
| `28-eda-event-stream-url.png` | **Obsolete, not merely superseded.** Showed the retired *single shared* stream (`ServiceNow Event Stream`, organization `Default`), which no longer exists, and its callout read "Copy this URL for ServiceNow REST Message" — the Appendix A OAuth pattern, not the event-stream design these guides use |

### Orphaned by the routing-guide deletion (2026-10-07) — all four now placed

`docs/servicenow-dynamic-team-routing.md` was deleted, which left four images it alone displayed.
Each was opened and checked before placing — the index description alone was not trusted, because
`64`'s had been wrong:

| File | Where it is now | What it shows |
|---|---|---|
| `73-sn-step1-input-vars.png` | [05 §3.1](../05-servicenow-action.md) | Step 1's declared **input** variables (`Incident_record`, `team_code`) with pills, its four declared outputs, and the script's case-sensitivity comment. **Its `Incident_record` pill reads `action ▸ … ▸ Number`**, which `05 §3.2` warns against — flagged there as something to verify in the UI rather than asserted as a fault |
| `75-sn-lookup-record-step.png` | [06 §3.1](../06-servicenow-flow.md) | The singular **Look Up Record** step fully expanded — table, both conditions, *Return only the first record*, and **Don't fail on error** ticked. Every field in `06 §3.1`'s table, in one view |
| `95-aap-job-extra-vars.png` | [07 §4](../07-end-to-end-test.md) | A successful job's **Extra variables**, including `target_team` and `source_stream`, plus the `ansible_eda` block and `meta.source.type: eda.builtin.pg_listener`. Record `sys_id`, stream UUID and event `uuid` are masked |
| `74-sn-step3-input-vars.png` | [05 §5.1](../05-servicenow-action.md) | Step 3's three **lowercase** declared inputs, with arrows to the title-case outputs they map from on the POST step — the clearest single view of the two-layer wiring — plus the four declared outputs. Opened and confirmed 2026-10-07 |

If you recapture any of the superseded ones, display the new one and delete the old rather than
growing this list.

**Redaction:** `71-sn-route-table-rows.png` and `95-aap-job-extra-vars.png` have the Event stream
UUID and record sys_ids masked. This repo is public and the UUIDs are deliberately absent from the
text, so keep them masked in any replacement capture.

| File | Shows |
|---|---|
| `10-controller-credential-type.png` | Custom ServiceNow credential type — input and injector configuration |
| `11-controller-credentials.png` | Automation Execution credential list |
| `12-controller-project.png` | Automation Execution project pointing at this repo |
| `13-controller-job-template.png` | Job template settings, with Prompt on launch ticked next to Extra variables |
| `20-eda-credentials.png` | Automation Decisions credential list |
| `21-eda-aap-controller-credential.png` | Red Hat Ansible Automation Platform credential — host ends at /api/controller/ |
| `22-eda-registry-credential.png` | Container Registry credential for registry.redhat.io |
| `23-eda-decision-environment.png` | Decision Environment using the de-supported-rhel9 image |
| `24-eda-project.png` | EDA project settings |
| `26-eda-event-stream-credential.png` | ServiceNow Event Stream credential — auth type token, header key Authorization |
| `27-eda-event-stream.png` | Event stream definition |
| `25-eda-rulebooks.png` | Rulebook activation form, showing the Event streams field mapped to the event stream |
| `31-activation-running.png` | Activation in Running state |
| `40-sn-credential-alias.png` | Connection & Credential Alias |
| `41-sn-http-connection.png` | HTTP(s) Connection pointing at the AAP host |
| `42-sn-api-key-credential.png` | API Key credential — header `Authorization`, bare token, **API Key Prefix empty** |
| `50-sn-action-inputs.png` | Action inputs — Incident Record |
| `51-sn-script-step-outputs.png` | Script step output variables (must be declared) |
| `52-sn-rest-step.png` | REST step — Connection Alias and Event Stream UUID as **pills** |
| `53-sn-result-script-outputs.png` | Result script step output variables |
| `54-sn-action-outputs.png` | Action outputs mapped from step pills |
| `50.1-sn-script-step-inputs.png` | Script step input variables and script body |
| `60-sn-flow-trigger.png` | Flow trigger — Created on Incident with a condition |
| `61-sn-flow-action-input.png` | Action step with the Incident Record dragged in |
| `63-sn-flow-update-record.png` | Then → Update Record with work notes |
| `64-sn-flow-end-flow.png` | `End Flow` inside the If's `then` branch, with the failure-path Update Record after the branch. **Renamed 2026-10-07** from `64-sn-flow-log-info.png` — it contains no Log step |
| `66-sn-flow-error-handler.png` | Full flow with the error handler expanded |
| `80-aap-oauth-application.png` | OAuth application — authorization code, confidential |
| `81-aap-allow-external-oauth.png` | Settings → Platform Gateway → Allow External Users to Create OAuth2 Tokens |
| `83-sn-ansible-alias.png` | Connection & Credential Alias for Ansible |
| `84-sn-create-get-oauth-token.png` | Create New Connection & Credential → Create and Get OAuth Token |

## If you recapture any of these

- Keep the filename identical so the README keeps resolving.
- Crop to the panel that matters; a full-screen browser shot is hard to read inline.
- **Redact before saving:** client secrets, bearer tokens, API keys, PAT values, internal
  hostnames, and internal email addresses. A screenshot pushed to a public repo stays public
  in git history even after you delete the file.
- Keep files under roughly 500 KB.

## Multi-team routing (added 2026-09-29)

| File | Shows |
|---|---|
| `70-sn-route-table-columns.png` | `EDA Team Route` table — six columns and their types |
| `71-sn-route-table-rows.png` | The two route rows, Event stream UUID column redacted |
| `72-sn-action-inputs-four.png` | All four action inputs — supersedes `50-sn-action-inputs.png` |
| `73-sn-step1-input-vars.png` | Step 1's `Incident_record` and `team_code` input variables with pills mapped |
| `74-sn-step3-input-vars.png` | Step 3's lowercase inputs (`status_code`, `response_body`, `rest_error_message`) and outputs |
| `75-sn-lookup-record-step.png` | The singular **Look Up Record** step with its conditions |
| `76-sn-flow-action-pills.png` | The flow's four action inputs, Connection alias as a **bare** reference pill, no For Each loop |
| `77-sn-action-outputs.png` | Action outputs — `Payload` wired to step 1, not step 3 |
| `90-aap-two-organizations.png` | Both AAP organizations |
| `91-aap-two-event-streams.png` | `sn-team-a` and `sn-team-b`, each in its own org with its own credential |
| `92-aap-two-activations.png` | Both activations running, each mapped to its own stream |
| `95-aap-job-extra-vars.png` | A successful Team A job with `target_team`, `source_stream` and `sn_close_incident` populated |

## Recaptured for the two-team setup (2026-09-29)

`40`, `42`, `52`, `53`, `60`, `66` were retaken. `65-sn-flow-else.png` was **deleted** — the flow has
no Else branch; the failure path works via End Flow inside the `then` branch.

## Problem record type — Phase 8 (added 2026-10-02)

Referenced by [Adding a record type](../adding-record-types.md). The `1xx` block is new so the
Problem build's screenshots stay together and nothing above has to be renumbered.

**All nine are on disk and committed.** The "Where it was captured" column is kept because several of
these were non-obvious to get right, and a recapture that ignores the note will reintroduce the
original mistake.

| File | Shows | Where it was captured |
|---|---|---|
| `100-sn-problem-state-readonly.png` | `problem.state` with **Read only = true** | **The LIST view, not the form** — `sys_dictionary_override_list.do?sysparm_query=name=problem`, with the **Read only** and **Override read only** columns added via the column personalizer. Recaptured 2026-10-06. ⚠️ **Do not recapture this from the form.** The form has a checkbox labelled "Override read only option" which is a *different field* from `read_only_override`, and it is unticked on this record — so a form capture shows the opposite of the truth. That is exactly how the first version of this image was wrong |
| `101-aap-problem-job-templates.png` | The three Problem job templates | AAP → Automation Execution → Templates, filtered on `Problem`. Show name, type and organization for all three |
| `102-sn-problem-action-inputs.png` | The four action inputs | Workflow Studio → `Send Problem to Ansible EDA` → Action inputs. Must show `Problem Record` typed **Reference → Problem** |
| `103-sn-problem-step1-vars.png` | Step 1's input and output variables | Step 1 **Build EDA Payload**. The point of the shot is output 4 reading **`problem_number`**, not `incident_number` |
| `104-sn-problem-flow-overview.png` | The whole flow, four steps collapsed | `Trigger EDA remediation on Problem`. Show step 2 is the If containing End Flow, and that steps 3–4 sit at the outer level |
| `105-sn-problem-flow-gate.png` | The route gate expanded | The If condition reading `EDA Team Route Record ➛ Sys ID` **is empty**, with `End Flow` inside it. The pill must visibly end at **Sys ID** |
| `106-sn-problem-flow-action-pills.png` | The four pills on the action step | Show `Connection alias` as a **bare** reference pill — no `➛ Sys ID` dot-walk — and `Problem Record` bare, not `➛ Number` |
| `107-aap-problem-job-output.png` | A successful job's report tasks | AAP job output, the `Report what was written…` and `Print problem summary` tasks. Should read `State left at New BY DESIGN` |
| `108-sn-problem-record-notes.png` | The record after automation, with **State still New** — the state ladder across the top and the **Assess** button make the "state changes are UI actions, not API writes" point | The problem record form. ⚠️ **Do not try to show `cause_notes` and `fix_notes` in one shot** — they live on different tabs of the Problem form, so it would take two screenshots. That is not worth it; the point of this image is that automation wrote its findings while leaving State alone |

**Redact before saving — and be precise about what is actually a secret:**

- **Mask: event stream UUIDs, tokens, API keys, client secrets, PAT values, passwords.** A stream
  UUID is the POST path and is paired with a bearer token, so it is close to a credential. `106` must
  **not** reveal the Event stream UUID if the pill preview expands it — mask it the way
  `71-sn-route-table-rows.png` does.
- **Do not mask record sys_ids or record numbers.** A problem `sys_id` on a throwaway PDI is a record
  identifier, not a credential: the instance requires authentication regardless. `107` is committed
  with a record sys_id visible and **that is a settled decision — do not re-raise it.**
- The AAP hostname in `101` and `107` is already public throughout this repo, so it is fine.

This distinction matters beyond the lab. On the Centene port nothing is disposable, so the rule there
is the same shape but stricter: UUIDs and tokens never leave the instance.

---

## Self-check

**Did I skip any prerequisite steps?** This file performs no build steps. Its one job is to make the
inventory reconcile, so the prerequisite is the count — and the command that proves it is in the
*Files kept on disk but not displayed* section rather than being asserted as a number you have to
trust.

**Is every command copy-paste ready with context?** The single command is the `comm` pipeline that
lists on-disk PNGs not referenced by any markdown file. It states its working directory and its
expected output is the table beneath it. Run 2026-10-07: **52 on disk, 48 displayed, 4 not.**

**Would a complete novice understand every single sentence?** The distinction this file exists to
carry is **superseded** versus **obsolete** — superseded means recapture and replace, obsolete means
delete — and the tables are grouped by that difference rather than mixing them. The redaction rule is
stated as what is and is not a secret, with the reasoning, because "mask everything" and "mask
nothing" are both wrong here: a stream UUID is a POST path paired with a token, while a record
`sys_id` on a throwaway PDI is not a credential.

**What this file cannot tell you.** It records what each image *should* show. Twice now that has been
wrong — `100` showed the opposite of its caption, and `64`'s description named a Log step the image
does not contain. **Open the file before trusting a row**, especially before deleting or re-placing
one.

