# Screenshots

Screenshots referenced by the main [README](../../README.md) and by
[Dynamic team routing](../servicenow-dynamic-team-routing.md).

## Files kept on disk but not displayed

Four images are intentionally not shown by any page. They are listed in the table below so the
inventory stays complete — **not** because a page is missing an image.

| File | Why it is not displayed |
|---|---|
| `50-sn-action-inputs.png` | Superseded by `72-sn-action-inputs-four.png` — shows only the Incident Record input, from before the action took four. Part 3 still names it in prose as "the older version" |
| `54-sn-action-outputs.png` | Superseded — shows the older output wiring |
| `61-sn-flow-action-input.png` | Superseded — pre-dates the four-input action step |
| `28-eda-event-stream-url.png` | **Obsolete, not merely superseded.** Shows the retired *single shared* stream (`ServiceNow Event Stream`, organization `Default`), which no longer exists, and its callout reads "Copy this URL for ServiceNow REST Message" — that is the Appendix A OAuth pattern, not the event-stream design this guide uses. Safe to delete; kept only so the count reconciles |

If you recapture any of the first three, display the new one and delete the old rather than growing
this list.

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
| `28-eda-event-stream-url.png` | The generated event stream URL — copy this into ServiceNow |
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
| `62-sn-flow-if-success.png` | If condition on the action's Success output |
| `63-sn-flow-update-record.png` | Then → Update Record with work notes |
| `64-sn-flow-log-info.png` | Log step, Info level |
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

**These nine are placeholders — the markdown references them but the files are not on disk yet.**
Capture each one, save it under exactly the filename below, and it will resolve with no doc edit.

| File | Shows | Where to capture it |
|---|---|---|
| `100-sn-problem-state-readonly.png` | `problem.state` with **Read only = true** | **Use the LIST view, not the form.** `sys_dictionary_override_list.do?sysparm_query=name=problem`, then add the **Read only** and **Override read only** columns via the column personalizer. The *form* has a checkbox labelled "Override read only option" which is a different field from `read_only_override` and is **unticked on this record** — a form capture shows the opposite of the truth and was rejected once for exactly that reason |
| `101-aap-problem-job-templates.png` | The three Problem job templates | AAP → Automation Execution → Templates, filtered on `Problem`. Show name, type and organization for all three |
| `102-sn-problem-action-inputs.png` | The four action inputs | Workflow Studio → `Send Problem to Ansible EDA` → Action inputs. Must show `Problem Record` typed **Reference → Problem** |
| `103-sn-problem-step1-vars.png` | Step 1's input and output variables | Step 1 **Build EDA Payload**. The point of the shot is output 4 reading **`problem_number`**, not `incident_number` |
| `104-sn-problem-flow-overview.png` | The whole flow, four steps collapsed | `Trigger EDA remediation on Problem`. Show step 2 is the If containing End Flow, and that steps 3–4 sit at the outer level |
| `105-sn-problem-flow-gate.png` | The route gate expanded | The If condition reading `EDA Team Route Record ➛ Sys ID` **is empty**, with `End Flow` inside it. The pill must visibly end at **Sys ID** |
| `106-sn-problem-flow-action-pills.png` | The four pills on the action step | Show `Connection alias` as a **bare** reference pill — no `➛ Sys ID` dot-walk — and `Problem Record` bare, not `➛ Number` |
| `107-aap-problem-job-output.png` | A successful job's report tasks | AAP job output, the `Report what was written…` and `Print problem summary` tasks. Should read `State left at New BY DESIGN` |
| `108-sn-problem-record-notes.png` | The record after automation | A problem showing `cause_notes`, `fix_notes` and `close_notes` populated while **State is still New** |

**Redact before saving:** `101` and `107` may show the AAP hostname — that is already public in this
repo, so it is fine. `106` must **not** reveal the Event stream UUID if the pill preview expands it;
mask it as `71-sn-route-table-rows.png` does. `107` and `108` contain record numbers and a sys_id —
mask the sys_id, as `95-aap-job-extra-vars.png` does.
