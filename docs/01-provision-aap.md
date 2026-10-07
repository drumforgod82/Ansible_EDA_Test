# 01 — Provision AAP (new build or rebuild)

> **What this stage gives you.** A running AAP 2.6/2.7 with both **Automation Execution** and
> **Automation Decisions** enabled, sized so that EDA actually works — and nothing created inside it
> yet.
>
> **Next stage:** [02 — Provision the ServiceNow PDI](02-provision-pdi.md). You need **both**
> platforms; this document covers only the Ansible half. If your ServiceNow instance already exists,
> `02` tells you so in its first lines and sends you straight on to
> [03 — AAP / EDA setup](03-aap-eda-setup.md).
> If your ServiceNow side already exists and only AAP died, finish both and then go straight to
> [09 — Reconnecting ServiceNow after an AAP rebuild](09-reconnect-after-aap-rebuild.md).
>
> **Time:** 30–60 minutes, most of it waiting for the operator to reconcile.

> **Any unfamiliar word?** Every term and acronym used in these guides is defined in the
> [Glossary](glossary.md) — including AAP, EDA, PDI, SCTASK, data pill, dot-walk, work note
> and `extra_vars`.

---

## 1. Getting the platform

Both platforms this project needs are available at no cost. Vendor deep links move, so these are
entry points plus what to look for — if a path has changed, search the developer portal for the
product name rather than trusting a URL here.

| You need | Where to start | Notes |
|---|---|---|
| Red Hat account | <https://developers.redhat.com> → *Register* | Free. Required before anything else Red Hat |
| An OpenShift cluster to run AAP on | <https://developers.redhat.com> → *Developer Sandbox* | Free, time-limited, renewable, no card. **This lab runs AAP 2.7 inside a Developer Sandbox namespace** |
| Or AAP hosted by Red Hat | [AAP trial](https://www.redhat.com/en/technologies/management/ansible/trial) · [console.redhat.com/ansible](https://console.redhat.com/ansible/ansible-dashboard) | Simpler if you would rather not run OpenShift yourself |

**You need admin on AAP.** Not a nicety — [03](03-aap-eda-setup.md) edits a credential *type*, which
a restricted account cannot do.

What the rest of this project assumes:

- AAP **2.6 or 2.7**, with **Automation Execution** and **Automation Decisions** both enabled
- Admin access to the AAP UI
- At least one organization — **and you will create one per team** in
  [03 §2.1](03-aap-eda-setup.md)

> ⚠️ **Do not build this project's objects in the stock `Default` organization.** AAP cannot move
> objects between organizations afterwards without recreating them
> ([03 §2.1](03-aap-eda-setup.md)), so anything you put in `Default` has to be rebuilt once you
> start separating teams.

### 1.1 Installing AAP itself — what this document does and does not do

**This document does not install AAP.** It covers getting an environment, reaching it, and sizing it
correctly. Which of those you need depends on how you got AAP:

| How you got AAP | Is it installed? | What you do here |
|---|---|---|
| **AAP hosted by Red Hat** (trial, or `console.redhat.com/ansible`) | Yes, Red Hat runs it | Skip §3 and §4 entirely — you have no cluster to patch. Go to [03](03-aap-eda-setup.md) |
| **Developer Sandbox / your own OpenShift** | **No — you install it** | Install it first (below), then do §3 and §4 |

If you are self-hosting, AAP is installed by the **AAP Operator** from OperatorHub, which then
creates an `AnsibleAutomationPlatform` **Custom Resource** that defines your instance. That is a
Red Hat-documented procedure that changes between releases, so rather than reproduce it here and go
stale, follow Red Hat's current *Installing on OpenShift Container Platform* guide for your version.

**Come back here when all three of these are true:**

1. The AAP web interface loads and you can log in as an administrator.
2. Both **Automation Execution** and **Automation Decisions** appear in the left-hand menu. If
   Automation Decisions is missing, EDA is not enabled and nothing in this project will work.
3. `K get ansibleautomationplatform` returns a row (see §3 for the `K` shortcut).

That third command is also how you discover your **`<cr-name>`**, which §4 needs:

```bash
K get ansibleautomationplatform
```

Expected output — one row, whose `NAME` is your `<cr-name>`. This is the real output, 2026-10-07:

```
NAME          AGE
sandbox-aap   19d
```

> ℹ️ **There is no `STATUS` column, and its absence is not a problem.** `kubectl` prints only `NAME`
> and `AGE` for this resource. To see whether the operator is happy, read the Custom Resource's
> conditions instead:
>
> ```bash
> K get ansibleautomationplatform <cr-name> \
>   -o jsonpath='{range .status.conditions[*]}{.type}{"="}{.status}{" "}{end}{"\n"}'
> ```
>
> Expected output on a healthy instance, 2026-10-07:
>
> ```
> Running=True Successful=True Failure=False
> ```
>
> **Read the `=True`/`=False`, not the names.** All three conditions are always listed, so seeing the
> word `Failure` means nothing on its own — `Failure=False` is what you want.

> ℹ️ **Why the Developer Sandbox case is worth a warning.** The Sandbox grants limited rights in a
> single namespace, and installing an operator may not be permitted on every Sandbox tier. If
> OperatorHub will not let you install into your namespace, the hosted trial is the faster route and
> loses you nothing in this project — only §3 and §4 become unnecessary.

### Placeholders used throughout the docs

| Placeholder | Meaning | Example |
|---|---|---|
| `<your-aap-host>` | AAP gateway hostname | `aap.example.com` |
| `<your-pdi>` | ServiceNow instance name, from [02](02-provision-pdi.md) | `dev123456` |
| `<your-scope>` | ServiceNow scope prefix, generated in [04 §1](04-servicenow-app.md) | `x_12345_myapp` |
| `<cr-name>` | The AAP Custom Resource name, from §1.1 above | `sandbox-aap` |
| `<your-cluster-domain>` | Your OpenShift cluster's domain, from your AAP URL — see §3 | `apps.rm1.0a51.p1.openshiftapps.com` |
| `<your-namespace>` | The OpenShift namespace AAP runs in, derived from your AAP URL — see §3 step 3 | `jdrebel2-dev` |
| `<Team>` | A team's name, e.g. `Team A` — used throughout [03](03-aap-eda-setup.md) | `Team A` |
| `<you>` | Your GitHub username, for the fork of this repo | `octocat` |

---

## 2. Two Developer Sandbox behaviours that are not your fault

Read these now so you don't debug them later.

> ⚠️ **The Developer Sandbox idles workloads it thinks are unused.** Two symptoms follow directly
> from that and are *not* faults in your build:
> - the first request after an idle period returns **503**, and the AAP UI shows a "provisioning"
>   screen;
> - activations die with `Missing container for running activation`.
>
> **Retry before you debug.** If it comes back on the second attempt, nothing was wrong.

> 🔴 **Nothing in AAP survives a rebuild.** Not the organization, inventory, credentials, projects,
> job templates, decision environments, event streams, tokens or activations. Plan on rebuilding all
> of it from [03](03-aap-eda-setup.md), and on re-pointing ServiceNow afterwards via
> [09](09-reconnect-after-aap-rebuild.md).

---

## 3. Get cluster access — you will need it before EDA works

The sizing fix in §4 cannot be done from the AAP web UI. There is no button for it. You need to
reach the **OpenShift API**.

### Words you'll need for this section

If you have never used Kubernetes or OpenShift, these five terms are all you need:

| Term | What it means here |
|---|---|
| **OpenShift** | Red Hat's Kubernetes platform. AAP runs *on top of* it as a set of containers |
| **Namespace** | A named folder inside the cluster that holds your things. Yours is the `jdrebel2-dev` part of your AAP URL |
| **`kubectl`** | The command-line tool for talking to the cluster. Everything in §3–§5 uses it |
| **Custom Resource (CR)** | A single configuration record that describes your whole AAP install. **This is what you edit in §4** |
| **Operator** | A background process that reads the Custom Resource and makes the cluster match it. **Reconcile** means the operator noticing your change and applying it, which takes a few minutes |

The last two matter together: you edit the **Custom Resource**, and the **operator** reconciles it.
That is why editing the running containers directly does not stick — see the warning in §4.

1. **`kubectl`.** (`oc` also works in principle — see the warning below.)

   > ⚠️ **If `oc` exits immediately with status 137 and no output, don't fight it.** Use `kubectl`
   > with an explicit `--token` and `--server` on every command, as the shortcut below does.

2. **A login token.** On Developer Sandbox the only identity provider is browser-based, so your AAP
   admin password will **not** log you in to OpenShift. Request a token at:

   ```
   https://oauth-openshift.apps.<your-cluster-domain>/oauth/token/request
   ```

   Click **Display Token** and copy the `--token=sha256~...` value.

3. **Your namespace.** OpenShift route names are `<route>-<namespace>`. So if your AAP URL is
   `https://sandbox-aap-jdrebel2-dev.apps.rm1.0a51.p1.openshiftapps.com/`, the route is
   `sandbox-aap` and the namespace is **`jdrebel2-dev`**.

### A shortcut, once per terminal session

This avoids `oc login`, so your existing kubectl context is left alone.

> 🔴 **All three values below are yours, not the examples.** Replace every one before running this.
> Pasting it unchanged points `kubectl` at a cluster you do not own and fails with
> `Unable to connect to the server`.

```bash
export T="sha256~PASTE_YOUR_TOKEN_HERE"              # from step 2 above
export API="https://api.<your-cluster-domain>:6443"  # swap apps. for api. and add :6443
export NS="<your-namespace>"                         # from step 3 above

K() { kubectl --token="$T" --server="$API" --insecure-skip-tls-verify=true -n "$NS" "$@"; }
```

Worked example, using the AAP URL from step 3
(`https://sandbox-aap-jdrebel2-dev.apps.rm1.0a51.p1.openshiftapps.com/`):

```bash
export API="https://api.rm1.0a51.p1.openshiftapps.com:6443"
export NS="jdrebel2-dev"
```

Note the API server host is **not** the `apps.` hostname — drop the `apps.` prefix and add port
`6443`.

> ⚠️ **`--insecure-skip-tls-verify=true` turns off certificate checking.** That is acceptable for a
> sandbox with self-signed certificates and should not be carried into anything real.

> ℹ️ **This lasts only for the current terminal window.** `export` and shell functions vanish when
> you close it, so re-run the whole block in each new terminal. That is what "once per terminal
> session" means above.

Check it:

```bash
K get pods
```

Expected output — a list of running AAP pods, names varying with your install:

```
NAME                                          READY   STATUS    RESTARTS   AGE
sandbox-aap-eda-default-worker-7c9f8b6d54-x2kqp   1/1   Running   0          4d
sandbox-aap-gateway-6b4d8f9c7d-mn4pq              1/1   Running   0          4d
...
```

`No resources found` means `NS` is wrong. An error mentioning `Unauthorized` means the token has
expired — request a fresh one.

---

## 4. Resize three components — do this BEFORE you create anything in EDA

This is the single most important step in this stage, and the easiest to skip because nothing has
gone wrong yet.

**Why.** The default memory limits are too small for EDA on a sandbox. Left alone, they produce three
failures that look unrelated and none of which names memory as the cause.

> ℹ️ **OOMKilled** means "Out Of Memory, Killed". The cluster gives each container a memory ceiling,
> and a container that tries to exceed it is terminated immediately — no error message, no log entry
> from the program itself, it just stops. That is why these failures never mention memory: from the
> application's point of view, nothing went wrong, it simply ceased to exist mid-task.

| Component | Default | Set to | What breaks at the default |
|---|---|---|---|
| `spec.eda.default_worker` | 400Mi | **1Gi** | Runs the git clone. Gets OOMKilled mid-clone, which surfaces as an **EDA project sync stuck on "Pending"** |
| `spec.eda.activation_worker` | 400Mi | **1Gi** | Supervises rulebook activations. OOMs once events actually start flowing |
| `spec.api` | 1000Mi | **2Gi** | The web UI and API. When it OOMs, the UI shows a **"provisioning" screen and the API returns 503** |

> 🔴 **Patch the Custom Resource, not the Deployment.** The operator reconciles Deployments back to
> whatever the CR says, so a Deployment edit is silently reverted a few minutes later — which looks
> like the fix "not working".
>
> **One documented exception exists** — `revisionHistoryLimit` has no CR equivalent, so it has to be
> patched on the Deployments. That is the only one, and it is covered in
> [AAP platform troubleshooting §4.4](aap-platform-troubleshooting.md#44-the-fix--delete-the-dead-replicasets-then-cap-the-history).

> ⚠️ **This patch consumes ReplicaSet slots, and a sandbox has few.** Changing memory limits makes the
> cluster create a new **ReplicaSet** for each component patched, keeping the old ones for rollback. A
> Developer Sandbox caps the namespace at 30, and once that cap is full **every** AAP Deployment loses
> its pods and AAP goes down completely.
>
> **Recommended on a fresh instance:** apply the patch below, wait for the reconcile, then cap the
> history with one loop —
> [AAP platform troubleshooting §5](aap-platform-troubleshooting.md#5-on-a-brand-new-sandbox-apply-both-fixes-first).
> If AAP is already down with no pods, start at
> [§4 there](aap-platform-troubleshooting.md#4-every-aap-pod-is-gone-and-rollouts-fail-on-quota)
> instead; this patch cannot apply until slots are free.

> ✅ **SETTLED 2026-10-07 on AAP 2.7 — `spec.api` is correct.** This was an open question. Verified
> three ways on the live instance: `K explain ansibleautomationplatform.spec.api` describes it as
> *"The gateway api deployment"*, the patched Custom Resource reports
> `spec.api.resource_requirements.limits.memory: 2Gi`, and that lands on the **`api` container of the
> `sandbox-aap-gateway` Deployment** — see §5.2.
>
> **Still worth one check on a different AAP version**, because `--type=merge` against a Custom
> Resource with a structural schema **silently discards** unknown fields: the patch reports success,
> nothing changes, and a half-applied patch can pass a careless verification.
>
> ```bash
> K explain ansibleautomationplatform.spec.api
> ```
>
> Expected output begins:
>
> ```
> FIELD: api <Object>
>
> DESCRIPTION:
>     The gateway api deployment.
> ```
>
> `No such field` means your version nests it elsewhere — most likely `spec.eda.api` or
> `spec.gateway`. Move that block and verify all three components in §5.2 rather than one.

Do all three in **one** patch so the operator reconciles once rather than three times:

```bash
K patch ansibleautomationplatform.aap.ansible.com <cr-name> --type=merge -p '{
 "spec": {
  "api": {
   "resource_requirements": {
    "limits":   {"cpu": "500m", "memory": "2Gi"},
    "requests": {"cpu": "100m", "memory": "512Mi"}
   }
  },
  "eda": {
   "default_worker": {
    "resource_requirements": {
     "limits":   {"cpu": "500m", "memory": "1Gi"},
     "requests": {"cpu": "25m",  "memory": "300Mi"}
    }
   },
   "activation_worker": {
    "resource_requirements": {
     "limits":   {"cpu": "500m", "memory": "1Gi"},
     "requests": {"cpu": "25m",  "memory": "300Mi"}
    }
   }
  }
 }
}'
```

That is **+2.2Gi** of `limits.memory` in total — 624Mi for each EDA worker plus 1048Mi for the API
component.

> ℹ️ **The sandbox quotas several dimensions separately, and they are not equally tight.**
> `limits.memory` is typically capped around **30Gi** with plenty unused, which is why this patch can
> raise memory freely. **`requests.cpu` is usually the constrained one** — so the patch keeps CPU
> *requests* small and does not raise CPU limits. Check your own headroom before patching:
>
> ```bash
> K get resourcequota
> ```
>
> Expected output includes a `compute-deploy` row listing `limits.memory` and `requests.cpu` as
> `used/hard` pairs. Compare the memory row against the +2.2Gi above.

CPU limits are deliberately modest and CPU *requests* are kept low, because requests are
what consume quota.

> ⚠️ **If the patch is rejected on quota**, you have genuinely run out of room. Free some by
> disabling a component you are not using, in the same patch:
>
> ```json
> "hub": {"disabled": true}
> ```
>
> Read the rejection message rather than assuming which limit was hit — the component and the
> resource named in the error are what to act on.

---

## 5. Verify before moving on

**5.1 — Wait for the operator.** Reconciliation takes a few minutes. Watch for the worker pods to be
replaced:

```bash
K get pods -w
```

**5.2 — Confirm the new limits actually landed — all three, not one.** This loops over every
deployment and prints each container with its memory limit, so you are not guessing at either
deployment names or container ordering:

```bash
for d in $(K get deploy -o name); do
  K get "$d" -o jsonpath='{.metadata.name}{"\t"}{range .spec.template.spec.containers[*]}{.name}{"="}{.resources.limits.memory}{" "}{end}{"\n"}'
done
```

Expected output — the two EDA workers at `1Gi`, and on the gateway row the container named **`api`**
at `2Gi`. This is the real output from a patched instance, 2026-10-07:

```
sandbox-aap-eda-default-worker      eda-default-worker=1Gi
sandbox-aap-eda-activation-worker   eda-activation-worker=1Gi
sandbox-aap-gateway                 proxy=1000Mi api=2Gi
...
```

> 🔴 **Read the gateway row carefully — `spec.api` does not produce a container called `gateway`.**
> The gateway Deployment runs **two** containers, and the patch changes only `api`. The `proxy=1000Mi`
> beside it is a different container and is **supposed** to stay at `1000Mi`.
>
> This matters because the obvious check is wrong: searching the output for `gateway=2Gi` finds
> nothing on a correctly patched instance, which reads as a failed patch. Look for **`api=2Gi`** on
> the `sandbox-aap-gateway` row.

**Check all three.** If `eda-default-worker` or `eda-activation-worker` still reads `400Mi`, or the
gateway's `api` container still reads `1000Mi`, either the operator has not finished — wait two
minutes and re-run — or that component's field path in the patch was wrong and was silently
discarded.

> ⚠️ **If a component is still at its default after five minutes, stop re-running and investigate the
> field path.** A merge patch that was accepted but discarded looks exactly like one that is still
> reconciling.

**5.3 — Confirm the worker is listening.** The worker has to be up and subscribed before a project
sync can succeed.

First find the worker pod's name. The name ends in a random suffix, so you cannot type it from
memory:

```bash
K get pods | grep eda-default-worker
```

Expected output — one `Running` pod, with your own random suffix:

```
sandbox-aap-eda-default-worker-7c9f8b6d54-x2kqp   1/1   Running   0   3m
```

Now check its log, pasting that pod name in place of the one below:

```bash
K logs sandbox-aap-eda-default-worker-7c9f8b6d54-x2kqp | grep pg_notify
```

Expected output — at least one line mentioning `pg_notify`. **Any match means the worker is
listening.** No output at all means it is not ready yet: wait a minute and re-run.

> ⚠️ **Order matters and is unforgiving.** Create an EDA project *before* the patch has reconciled
> and the worker is listening, and the sync fails — then sits in a state that looks like a
> repository or credential problem. If you have already hit that, the diagnostic path is in
> [10 — Troubleshooting](10-troubleshooting.md).

---

## 6. Other things a fresh instance invalidates

- **Any Personal Access Token you saved is dead** and must be re-minted. Anything scripted against
  AAP — including `scripts/verify_team.py` — needs the new value.
- **Any event stream UUID and token recorded in ServiceNow is stale.** That is the whole subject of
  [09](09-reconnect-after-aap-rebuild.md); don't try to fix it from here.

---

## Checkpoint

Before you go on, all of these should be true:

- [ ] AAP UI loads, with **Automation Execution** and **Automation Decisions** both visible
- [ ] You can run `K get pods` against the cluster
- [ ] `spec.eda.default_worker` reports a `1Gi` memory limit
- [ ] The default worker's log shows the `pg_notify` line
- [ ] You have **not** created any EDA project, decision environment or event stream yet

**Next:** [02 — Provision the ServiceNow PDI](02-provision-pdi.md) — or, if you already have a
ServiceNow instance, skip ahead to [03 — AAP / EDA setup](03-aap-eda-setup.md).

---

## Self-check

**Did I skip any prerequisite steps?** One is deliberately out of scope rather than skipped: §1.1
states plainly that this document does **not** install AAP, splits hosted from self-hosted, and gives
three verifiable conditions for when to come back. The `<cr-name>` discovery command is there too,
because §4 cannot be done without it.

**Is every command copy-paste ready with context?** Yes, after a correction — the `K` shortcut
originally shipped with the author's own cluster and namespace pre-filled in a block the reader is
told to run. Both are now placeholders, with the real values shown separately as a labelled worked
example. Every command states its expected output, including what `No resources found` and an
`Unauthorized` error each mean.

**Would a complete novice understand every single sentence?** §3 front-loads the five Kubernetes
terms the rest depends on, and pairs Custom Resource with operator and reconcile because the §4
warning turns on that relationship. OOMKilled is defined where the failures it causes are listed,
since nothing in those symptoms mentions memory.
