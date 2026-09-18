# Screenshots

These are the screenshots referenced by the main [README](../../README.md), in the order they
appear. All of them are present.

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
| `42-sn-api-key-credential.png` | API Key credential — header Authorization, value 'Bearer <token>' |
| `50-sn-action-inputs.png` | Action inputs — Incident Record |
| `51-sn-script-step-outputs.png` | Script step output variables (must be declared) |
| `52-sn-rest-step.png` | REST step using the connection alias |
| `53-sn-result-script-outputs.png` | Result script step output variables |
| `54-sn-action-outputs.png` | Action outputs mapped from step pills |
| `50.1-sn-script-step-inputs.png` | Script step input variables and script body |
| `60-sn-flow-trigger.png` | Flow trigger — Created on Incident with a condition |
| `61-sn-flow-action-input.png` | Action step with the Incident Record dragged in |
| `62-sn-flow-if-success.png` | If condition on the action's Success output |
| `63-sn-flow-update-record.png` | Then → Update Record with work notes |
| `64-sn-flow-log-info.png` | Log step, Info level |
| `65-sn-flow-else.png` | Else branch — update record and log the error |
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
