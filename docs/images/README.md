# Screenshots

Drop your screenshots here using these exact filenames and they will render in the main
[README](../../README.md) automatically. PNG is preferred.

Tick them off as you capture them:

- [ ] `10-controller-credential-type.png` — Custom ServiceNow credential type — input and injector configuration
- [ ] `11-controller-credentials.png` — Automation Execution credential list
- [ ] `12-controller-project.png` — Automation Execution project pointing at this repo
- [ ] `13-controller-job-template.png` — Job template settings
- [ ] `14-controller-prompt-on-launch.png` — Variables → Prompt on launch enabled (required)
- [ ] `20-eda-credentials.png` — Automation Decisions credential list
- [ ] `21-eda-aap-controller-credential.png` — Red Hat Ansible Automation Platform credential — host ends at /api/controller/
- [ ] `22-eda-registry-credential.png` — Container Registry credential for registry.redhat.io
- [ ] `23-eda-decision-environment.png` — Decision Environment using the de-supported-rhel9 image
- [ ] `24-eda-project.png` — EDA project synced, state Completed
- [ ] `25-eda-rulebooks.png` — Rulebooks discovered after a successful sync
- [ ] `26-eda-event-stream-credential.png` — ServiceNow Event Stream credential — auth type token, header key Authorization
- [ ] `27-eda-event-stream.png` — Event stream definition
- [ ] `28-eda-event-stream-url.png` — The generated event stream URL — copy this into ServiceNow
- [ ] `29-activation-details.png` — Activation page 1 — details
- [ ] `30-activation-event-stream-mapping.png` — Activation page 2 — mapping ansible.eda.webhook onto the event stream
- [ ] `31-activation-running.png` — Activation in Running state
- [ ] `40-sn-credential-alias.png` — Connection & Credential Alias
- [ ] `41-sn-http-connection.png` — HTTP(s) Connection pointing at the AAP host
- [ ] `42-sn-api-key-credential.png` — API Key credential — header Authorization, value 'Bearer <token>'
- [ ] `50-sn-action-inputs.png` — Action inputs — Incident Record
- [ ] `51-sn-script-step-outputs.png` — Script step output variables (must be declared)
- [ ] `52-sn-rest-step.png` — REST step using the connection alias
- [ ] `53-sn-result-script-outputs.png` — Result script step output variables
- [ ] `54-sn-action-outputs.png` — Action outputs mapped from step pills
- [ ] `60-sn-flow-trigger.png` — Flow trigger — Created on Incident with a condition
- [ ] `61-sn-flow-action-input.png` — Action step with the Incident Record dragged in
- [ ] `62-sn-flow-if-success.png` — If condition on the action's Success output
- [ ] `63-sn-flow-update-record.png` — Then → Update Record with work notes
- [ ] `64-sn-flow-log-info.png` — Log step, Info level
- [ ] `65-sn-flow-else.png` — Else branch — update record and log the error
- [ ] `66-sn-flow-error-handler.png` — Flow error handler
- [ ] `67-sn-flow-overview.png` — Full flow overview
- [ ] `70-eda-event-stream-events.png` — Event stream Events tab showing the received JSON
- [ ] `71-controller-job-from-eda.png` — Controller job launched by the rulebook, with extra vars
- [x] `80-aap-oauth-application.png` — OAuth application — authorization code, confidential
- [ ] `81-aap-allow-external-oauth.png` — Settings → Platform Gateway → Allow External Users to Create OAuth2 Tokens
- [ ] `82-sn-configuration-template.png` — Integration Hub configuration template
- [ ] `83-sn-ansible-alias.png` — Connection & Credential Alias for Ansible
- [ ] `84-sn-create-get-oauth-token.png` — Create New Connection & Credential → Create and Get OAuth Token
- [ ] `85-sn-rest-message.png` — REST Message with OAuth 2.0 authentication

## Tips

- Crop to the panel that matters. A full-screen browser shot is hard to read in a README.
- **Redact before saving:** client secrets, bearer tokens, API keys, PAT values, and any
  internal hostnames. Once pushed to a public repo, a screenshot is public permanently.
- Keep files under roughly 500 KB so the repo stays quick to clone.
