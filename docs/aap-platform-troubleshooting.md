# AAP platform troubleshooting — OpenShift and the Red Hat Developer Sandbox

**This document covers the cluster-level failures that stop a self-hosted AAP install from working —
an EDA project that never finishes syncing, and every AAP pod disappearing at once — and gives the
read-only diagnosis and the fix for each.**

> **How to use this.** Don't read it top to bottom. Find your symptom in
> [§1](#1-symptom-index), and it tells you which section to open.
>
> **Related:** [10 — Troubleshooting](10-troubleshooting.md) ·
> [01 — Provision AAP](01-provision-aap.md) · [Glossary](glossary.md)

> **Applies to** Ansible Automation Platform (AAP) 2.7 on OpenShift, installed with the AAP
> Operator. Measured on a Red Hat **Developer Sandbox**, which is a free, quota-limited OpenShift
> account. Both failures here are caused by the sandbox's small default limits, so a larger cluster
> may never show them.

> **Any unfamiliar word?** Every term and acronym used in these guides is defined in the
> [Glossary](glossary.md) — including AAP, EDA, operator, Custom Resource, reconcile, Deployment,
> ReplicaSet and `revisionHistoryLimit`.

---

## Contents

- [0. Which document do you need](#0-which-document-do-you-need)
- [1. Symptom index](#1-symptom-index)
- [2. Before you start — cluster access](#2-before-you-start--cluster-access)
- [3. An EDA project never finishes syncing](#3-an-eda-project-never-finishes-syncing)
  - [3.1 The symptom](#31-the-symptom)
  - [3.2 What is actually wrong](#32-what-is-actually-wrong)
  - [3.3 Confirm the diagnosis before changing anything](#33-confirm-the-diagnosis-before-changing-anything)
  - [3.4 The fix — raise three memory limits](#34-the-fix--raise-three-memory-limits)
  - [3.5 Verify the fix](#35-verify-the-fix)
- [4. Every AAP pod is gone and rollouts fail on quota](#4-every-aap-pod-is-gone-and-rollouts-fail-on-quota)
  - [4.1 The symptom](#41-the-symptom)
  - [4.2 What is actually wrong](#42-what-is-actually-wrong)
  - [4.3 Confirm the diagnosis before changing anything](#43-confirm-the-diagnosis-before-changing-anything)
  - [4.4 The fix — delete the dead ReplicaSets, then cap the history](#44-the-fix--delete-the-dead-replicasets-then-cap-the-history)
  - [4.5 Verify the fix](#45-verify-the-fix)
  - [4.6 Why this one can come back](#46-why-this-one-can-come-back)
- [5. On a brand-new sandbox, apply both fixes first](#5-on-a-brand-new-sandbox-apply-both-fixes-first)
- [6. Gotchas worth knowing](#6-gotchas-worth-knowing)
- [7. Quick reference](#7-quick-reference)

---

## 0. Which document do you need

There are two troubleshooting documents and they do not overlap. Pick by **what is still working**:

| If… | Go to |
|---|---|
| AAP itself is up, but ServiceNow events do not arrive or no job runs | [10 — Troubleshooting](10-troubleshooting.md) |
| AAP itself is broken — pods missing, UI down, a sync that never completes | **This document** |

> ℹ️ **Everything here needs cluster access**, not just the AAP web interface. None of it can be done
> from the AAP user interface, because the problems are one layer below it. If Red Hat hosts your AAP,
> you cannot apply these fixes and you should not need to — the limits that cause them are the
> sandbox's.

---

## 1. Symptom index

Find your symptom, go to that section.

| Symptom | Section |
|---|---|
| EDA project sits at **Pending**, then fails with *"Task was stuck in pending state"* | [§3](#3-an-eda-project-never-finishes-syncing) |
| Same repository syncs fine under Automation Execution but not Automation Decisions | [§3.2](#32-what-is-actually-wrong) |
| AAP interface shows a "provisioning" screen and the API returns `503` | [§3.4](#34-the-fix--raise-three-memory-limits) |
| A container shows `OOMKilled` or exit code `137` | [§3](#3-an-eda-project-never-finishes-syncing) |
| `HTTP 503 "Project workers unavailable"` when you trigger a sync | [§3.5](#35-verify-the-fix) |
| The AAP interface does not load at all, and every Deployment shows `0/1` ready | [§4](#4-every-aap-pod-is-gone-and-rollouts-fail-on-quota) |
| Events show `ReplicaSetCreateError` | [§4](#4-every-aap-pod-is-gone-and-rollouts-fail-on-quota) |
| Events show `exceeded quota` naming `count/replicasets.apps` | [§4](#4-every-aap-pod-is-gone-and-rollouts-fail-on-quota) |
| A Custom Resource patch is rejected on quota | [§3.4](#34-the-fix--raise-three-memory-limits) |
| `K get resourcequota` reports `NotFound` for a quota an error just named | [§4.3](#43-confirm-the-diagnosis-before-changing-anything) |
| `oc` prints nothing at all and exits | [§6](#6-gotchas-worth-knowing) |

---

## 2. Before you start — cluster access

Both fixes need you to run `kubectl` against the cluster. This section sets that up and is a
prerequisite for §3 and §4.

> ℹ️ **`kubectl` is the command-line tool for talking to a Kubernetes or OpenShift cluster.** It is a
> separate program from the AAP interface and uses a separate login.

**1. Install `kubectl`** if you do not have it. Check with:

```bash
kubectl version --client
```

Expected output — a version line, the number will differ:

```
Client Version: v1.31.1
```

**2. Get an OpenShift login token.** On the Developer Sandbox the only identity provider is
browser-based, so your **AAP admin password will not log you in to OpenShift**. Open this in a
browser, replacing the placeholder:

```
https://oauth-openshift.apps.<your-cluster-domain>/oauth/token/request
```

Click **Display Token** and copy the value shown after `--token=`. It begins `sha256~`.

**3. Work out your namespace.** OpenShift route names are `<route>-<namespace>`. So if your AAP
address is `https://sandbox-aap-jdrebel2-dev.apps.rm1.0a51.p1.openshiftapps.com/`, the route is
`sandbox-aap` and the namespace is **`jdrebel2-dev`**.

### The placeholders used in this document

| Placeholder | Meaning | How to get it |
|---|---|---|
| `<your-cluster-domain>` | Your OpenShift cluster's domain, e.g. `rm1.0a51.p1.openshiftapps.com` | The part of your AAP address after `.apps.` |
| `<your-namespace>` | The OpenShift namespace AAP runs in, e.g. `jdrebel2-dev` | Step 3 above |
| `<your-aap-host>` | Your AAP hostname, e.g. `sandbox-aap-jdrebel2-dev.apps.rm1.0a51.p1.openshiftapps.com` | The address you open AAP at, without `https://` |
| `<cr-name>` | The name of the AAP Custom Resource, e.g. `sandbox-aap` | `K get ansibleautomationplatform` |
| `<project-id>` | The numeric id of an EDA project, e.g. `1` | [§3.3](#33-confirm-the-diagnosis-before-changing-anything) step 1 |
| `<pod-name>` | A full pod name, including its random suffix | `K get pods` |
| `<deployment-name>` | A full Deployment name, e.g. `sandbox-aap-gateway`. Deployment names have **no** random suffix | `K get deploy` |
| `<your-sandbox-user>` | Your Red Hat Developer Sandbox username, e.g. `jdrebel2` | The part of `<your-namespace>` before `-dev` |

### A shortcut, once per terminal session

This avoids `oc login`, so your existing `kubectl` configuration is left alone.

> 🔴 **All three values below are yours, not the examples.** Replace every one before running this.
> Pasting it unchanged points `kubectl` at a cluster you do not own and fails with
> `Unable to connect to the server`.

```bash
export T="sha256~PASTE_YOUR_TOKEN_HERE"              # from step 2 above
export API="https://api.<your-cluster-domain>:6443"  # swap apps. for api. and add :6443
export NS="<your-namespace>"                         # from step 3 above

K() { kubectl --token="$T" --server="$API" --insecure-skip-tls-verify=true -n "$NS" "$@"; }
```

Worked example, for the AAP address used in step 3:

```bash
export API="https://api.rm1.0a51.p1.openshiftapps.com:6443"
export NS="jdrebel2-dev"
```

Note the API server host is **not** the `apps.` hostname — drop the `apps.` prefix and add port
`6443`.

> ⚠️ **`--insecure-skip-tls-verify=true` turns off certificate checking.** That is acceptable for a
> sandbox using self-signed certificates and should not be carried into anything real.

> ℹ️ **This lasts only for the current terminal window.** `export` and shell functions vanish when you
> close it, so re-run the whole block in each new terminal. That is what "once per terminal session"
> means above.

> ⚠️ **`K` is a shell function, not a program.** That means it cannot be used with `xargs` or `sudo`,
> which can only run real programs. Every loop in this document calls `K` from inside a `for` loop for
> that reason.

Check it works:

```bash
K get pods
```

Expected output — a list of AAP pods, names varying with your install:

```
NAME                                              READY   STATUS    RESTARTS   AGE
sandbox-aap-eda-default-worker-7c9f8b6d54-x2kqp   1/1     Running   0          4d
sandbox-aap-gateway-6b4d8f9c7d-mn4pq              1/1     Running   0          4d
...
```

`No resources found` means `NS` is wrong. An error mentioning `Unauthorized` means the token has
expired — request a fresh one from step 2.

---

## 3. An EDA project never finishes syncing

### 3.1 The symptom

You add a Project under **Automation Decisions** (Event-Driven Ansible) pointing at a public GitHub
repository. It sits at **Pending**, and after about ten minutes flips to **Failed** with:

```
Task was stuck in pending state. Marked as failed by monitoring system.
```

Two things make this confusing:

- The **same repository** added as a Project under **Automation Execution** syncs in a couple of
  seconds.
- Everything in the AAP interface looks healthy. The EDA service reports `good`.

### 3.2 What is actually wrong

**Your project configuration is fine.** The repository address, the branch, the credential (a public
repository needs none) and the repository layout are all irrelevant to this failure.

The pod that performs the git clone **runs out of memory and is killed mid-clone**.

> ℹ️ **OOMKilled** means "Out Of Memory, Killed". The cluster gives each container a memory ceiling,
> and a container that tries to exceed it is terminated immediately — no error message and no log
> entry from the program itself. That is why nothing in AAP mentions memory.

Here is the chain:

1. You click Sync. The EDA API writes a database row with `import_state = pending` and puts a task on
   a queue named `default`.
2. A pod called `<cr-name>-eda-default-worker` picks that task up and starts cloning.
3. That clone is **not** a plain `git clone`. EDA runs `ansible-runner`, which runs a small Ansible
   playbook, which then runs `git`. That is a lot of processes in one container.
4. The container has a **400Mi memory limit**. The worker's own Python process already occupies most
   of it, so adding `ansible-runner` and `git` passes the limit in about **1.3 seconds**.
5. Linux kills the container (`OOMKilled`, exit code `137`). The task dies with it.
6. Task delivery uses PostgreSQL `pg_notify`, which has **no backing table** — it is fire-and-forget.
   A task whose worker died is simply gone, and is never retried.
7. The database row stays at `pending` forever. A separate monitor notices it ten minutes later and
   rewrites it as `failed` with that misleading message.

**Why the Automation Execution project works and the Automation Decisions one does not.** They are
completely different code paths:

| | Where the git clone runs | Memory available |
|---|---|---|
| **Automation Execution** (controller) | Its own execution-environment pod | Its own budget |
| **Automation Decisions** (EDA) | Inside the `eda-default-worker` pod | 400Mi, shared with the worker |

A controller project syncing successfully tells you **nothing** about the EDA side. Do not treat it as
evidence that networking, DNS or credentials are fine for EDA.

**Why the interface says everything is healthy.** The health checks probe the EDA **API** and
**event-stream** pods only. They never check the worker. So `/api/eda/v1/status/` returns `good` while
the worker is dying repeatedly.

### 3.3 Confirm the diagnosis before changing anything

Every step here is read-only. Do them in order.

**1. Read the project's real error.** This prompts for the password rather than taking it on the
command line, so it does not land in your shell history:

```bash
read -rsp "AAP admin password: " AAPPW; echo
curl -sk -u "admin:$AAPPW" "https://<your-aap-host>/api/eda/v1/projects/" | python3 -m json.tool
```

Look at `import_state` and `import_error`. An **empty `git_hash`** confirms no clone ever completed.
Note the project's `id` — that is `<project-id>` in the commands below.

**2. Find the worker pod** and note its `RESTARTS` count:

```bash
K get pods | grep eda-default-worker
```

Expected output — one pod, with your own random suffix:

```
sandbox-aap-eda-default-worker-7c9f8b6d54-x2kqp   1/1   Running   0   3m
```

**3. Prove it was OOMKilled.** Paste your own pod name in place of the example:

```bash
K get pod <pod-name> -o json | python3 -c "
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

**4. Watch the clone die.** `--previous` reads the log of the *killed* container rather than the
running one:

```bash
K logs <pod-name> --previous | tail -20
```

The log **ends mid-clone**, with nothing after it — no error and no stack trace:

```
INFO aap_eda.tasks.project Task started: Sync project (project_id=1)
INFO aap_eda.services.project.scm Cloning repository: https://github.com/...
   <nothing after this -- the container was killed>
```

**5. Check you have quota room for the fix.**

> ℹ️ **A quota is a cap the cluster puts on how much of something your namespace may use.** The
> sandbox caps several things separately, and they are not equally tight.

```bash
K get resourcequota
```

Look at the `compute-deploy` row. On the Developer Sandbox `limits.memory` is typically **30Gi** with
plenty unused. The constrained one is usually **`requests.cpu`** — which is why the patch below raises
memory and leaves CPU requests alone.

### 3.4 The fix — raise three memory limits

> 🔴 **Patch the Custom Resource, not the Deployment.** The operator reconciles Deployments back to
> whatever the Custom Resource says, so a Deployment edit is silently reverted a minute or two later —
> which looks exactly like the fix "not working". (§4 is the one deliberate exception, and it says so.)

This raises all three components that run out of memory on a sandbox-sized install. Do them in **one**
patch so the operator reconciles once rather than three times:

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

Expected output:

```
ansibleautomationplatform.aap.ansible.com/sandbox-aap patched
```

Find `<cr-name>` with `K get ansibleautomationplatform` if you do not know it.

| Custom Resource path | Pod affected | Default | New | Why |
|---|---|---|---|---|
| `spec.eda.default_worker` | `eda-default-worker` | 400Mi | **1Gi** | Runs the git clone. **This is the project-sync fix** |
| `spec.eda.activation_worker` | `eda-activation-worker` | 400Mi | **1Gi** | Supervises rulebook activations. Runs out of memory once events start flowing |
| `spec.api` | `gateway` (api container) | 1000Mi | **2Gi** | The web interface and API. When it runs out, the interface shows a "provisioning" screen and the API returns `503` |

That is roughly **+2.2Gi** of `limits.memory` against a 30Gi ceiling. CPU limits and CPU requests are
deliberately left alone, because `requests.cpu` is the quota actually near its ceiling.

> ✅ **SETTLED 2026-10-07 on AAP 2.7 — `spec.api` is correct**, and it patches the `api` container of
> the gateway Deployment. Verified against the live Custom Resource; details in
> [01 §4](01-provision-aap.md).
>
> **Still worth one check on a different AAP version**, because `--type=merge` against a Custom
> Resource with a structural schema **silently discards** unknown fields — the patch reports success
> and nothing changes:
>
> ```bash
> K explain ansibleautomationplatform.spec.api
> ```
>
> Expected output begins `FIELD: api <Object>` followed by *"The gateway api deployment."* A
> `No such field` error means your version nests it elsewhere — most likely `spec.eda.api` or
> `spec.gateway`.

> ⚠️ **If the patch is rejected on quota**, you have genuinely run out of room. Free some by disabling
> a component you are not using, in the same patch:
>
> ```json
> "hub": {"disabled": true}
> ```
>
> Read the rejection message rather than assuming which limit was hit. On the sandbox measured here
> this was **not** necessary — there was around 15Gi of memory unused. Do not disable hub reflexively.

### 3.5 Verify the fix

**1. Wait for the operator**, which takes about three minutes. The Custom Resource changes instantly;
the Deployment does not. This prints every Deployment with each container's memory limit, so you are
not guessing at deployment names or container ordering:

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
```

> 🔴 **`spec.api` does not produce a container called `gateway`.** The gateway Deployment runs **two**
> containers and the patch changes only `api`; the `proxy=1000Mi` beside it is a different container
> and is **supposed** to stay at `1000Mi`. Searching the output for `gateway=2Gi` finds nothing on a
> correctly patched instance, which reads as a failed patch. Look for **`api=2Gi`**.

**Check all three.** If a worker still reads `400Mi`, or the gateway's `api` container still reads
`1000Mi` after five minutes, stop re-running: that component's field path was wrong and was silently
discarded.

**2. Wait for the worker to start listening.** This matters — the pod can be `Running` for about ten
seconds before it will accept work:

```bash
K logs <pod-name> | grep pg_notify
```

Wait for a line like:

```
dispatcherd.brokers.pg_notify  Set up pg_notify listening on channel 'default'
```

No output at all means it is not ready yet. Wait a minute and re-run.

**3. Re-sync the project.** In the interface: **Automation Decisions → Projects → your project → ⋮ →
Sync**. Or by API, using the `<project-id>` you noted in §3.3:

```bash
read -rsp "AAP admin password: " AAPPW; echo
curl -sk -u "admin:$AAPPW" -X POST -w '\nHTTP:%{http_code}\n' \
  "https://<your-aap-host>/api/eda/v1/projects/<project-id>/sync/"
```

> ℹ️ **`HTTP 503 "Project workers unavailable"` is not a failure.** AAP checks worker health before
> queuing work, and you asked before the worker finished starting. Wait for the `pg_notify` line from
> step 2 and retry.

**4. Confirm it synced:**

```bash
curl -sk -u "admin:$AAPPW" \
  "https://<your-aap-host>/api/eda/v1/projects/<project-id>/" \
  | python3 -m json.tool | grep -E 'import_state|git_hash'
```

Expected output — a completed state and a non-empty hash, which will be your own commit:

```
"import_state": "completed",
"git_hash": "81a1695a47bdc3f6f97af87cbcf8ec6f6adeeba2"
```

A healthy sync takes about **three seconds**.

**5. Confirm your rulebooks were found:**

```bash
curl -sk -u "admin:$AAPPW" "https://<your-aap-host>/api/eda/v1/rulebooks/" \
  | python3 -m json.tool | grep '"name"'
```

Expected output — one line per rulebook file in the repository.

> ⚠️ **If `import_state` is `completed` but `import_error` says "This project contains no rulebooks",
> the sync worked and the repository layout is wrong.** Rulebooks must be in `rulebooks/` or
> `extensions/eda/rulebooks/` **at the repository root**. The search is **not** recursive.

---

## 4. Every AAP pod is gone and rollouts fail on quota

### 4.1 The symptom

AAP is simply not there. The web address does not load. Checking the cluster, every AAP Deployment
wants one pod and has none:

```bash
K get deploy
```

Observed output when this is the problem — all of them `0/1`:

```
NAME                                READY   UP-TO-DATE   AVAILABLE   AGE
sandbox-aap-gateway                 0/1     0            0           19d
sandbox-aap-eda-api                 0/1     0            0           19d
sandbox-aap-eda-default-worker      0/1     0            0           19d
...
```

```bash
K get pods
```

Only the database and cache survive, and they look perfectly healthy:

```
NAME                        READY   STATUS    RESTARTS   AGE
sandbox-aap-postgres-15-0   1/1     Running   0          6h22m
sandbox-aap-redis-0         1/1     Running   0          6h22m
```

> ℹ️ **Those two survive because they are StatefulSets, not Deployments.** A StatefulSet manages its
> pods directly and does not create ReplicaSets, so the cap described below never touches it. Seeing
> them healthy is not evidence that the cluster is healthy.

This is **not** the §3 failure. Nothing is `OOMKilled` here, because nothing ever started.

### 4.2 What is actually wrong

Your namespace has hit a cap on **how many ReplicaSets may exist at once**, so no Deployment can
start a new pod.

Three terms, in the order they matter:

- A **Deployment** is the record that says "keep one copy of this container running".
- A **ReplicaSet** is what a Deployment creates to do that. Every time a Deployment's container
  settings change — a new image, a new memory limit — Kubernetes creates a **new** ReplicaSet and
  scales the old one down to zero pods. The old, empty one is kept on purpose, as a rollback point.
- **`revisionHistoryLimit`** is the setting controlling how many of those old empty ReplicaSets a
  Deployment keeps. **The default is 10.**

A sandbox AAP install has around **12 Deployments**. At the default, those 12 can retain up to 132
ReplicaSets between them — 12 live ones plus 120 kept for rollback. The Developer Sandbox caps the
namespace at **30**. So after a handful of configuration changes the cap is reached, and the next
rollout has nowhere to put its new ReplicaSet:

```
Failed to create new replica set: replicasets.apps "sandbox-aap-gateway-6b4d8f9c7d" is forbidden:
exceeded quota: for-jdrebel2-replicas, requested: count/replicasets.apps=1,
used: count/replicasets.apps=30, limited: count/replicasets.apps=30
```

The Deployment's own status reports this as **`ReplicaSetCreateError`**. Your quota name will be
different — on the sandbox it is `for-<your-sandbox-user>-replicas`.

The result is worse than a failed update: the Deployment has already given up its old pods and cannot
create new ones, so you are left with zero running pods and an AAP that is completely down.

> 🔴 **Applying the §3 memory patch is a common trigger.** Changing memory limits changes every
> patched Deployment's container settings, which creates a new ReplicaSet for each one. If you are
> already near the cap, the fix in §3 is what tips you over it — so the two sections are related
> even though the failures look nothing alike.

> ℹ️ **Why the pods vanish hours after the last change you made.** The Developer Sandbox scales idle
> workloads down and back up on its own. That restart is what attempts the rollout and discovers the
> cap, long after anyone touched the configuration.

### 4.3 Confirm the diagnosis before changing anything

Every step here is read-only.

**1. Read the actual error.** This is the one that names the quota:

```bash
K get events --sort-by=.lastTimestamp | grep -i quota
```

Expected output — one or more lines containing `exceeded quota` and `count/replicasets.apps`. If you
get no output, this is not your problem; go back to [§1](#1-symptom-index).

You can also read it off one Deployment:

```bash
K describe deploy <deployment-name> | grep -A6 Conditions
```

Look for `ReplicaSetCreateError` in the `Progressing` condition.

**2. Count your ReplicaSets.** The number should sit exactly at the cap named in the error:

```bash
K get rs --no-headers | wc -l
```

Observed output on the broken sandbox:

```
30
```

**3. Count how many of them are dead.** `K get rs` prints the columns `NAME DESIRED CURRENT READY`,
so a ReplicaSet with `0` desired is holding a slot and running nothing:

```bash
K get rs --no-headers | awk '$2=="0" && $3=="0" && $4=="0"' | wc -l
```

Observed output — all 30 were empty, because none of the Deployments had any pods at all:

```
30
```

> ⚠️ **`K get resourcequota` will probably not list this quota.** On the sandbox it reports `NotFound`
> for the name the error just gave you, because the cap is applied from outside your namespace rather
> than by a quota object inside it. **This is not evidence that the quota is gone** — it is still
> enforced, and chasing it here wasted real time on the day this was diagnosed. Take the numbers from
> the event message in step 1, which always states `used` and `limited`.

### 4.4 The fix — delete the dead ReplicaSets, then cap the history

Two commands. The first frees the slots; the second stops them filling up again.

> 🔴 **This is the one place in these guides where you patch Deployments directly**, which §3.4 tells
> you never to do. The reason is that `revisionHistoryLimit` is a Deployment setting with no equivalent
> field in the AAP Custom Resource, so there is nothing to patch at the Custom Resource level. See
> [§4.6](#46-why-this-one-can-come-back) for what that costs you.

**1. List the dead ReplicaSets first.** Look at the list before deleting anything:

```bash
K get rs --no-headers | awk '$2=="0" && $3=="0" && $4=="0" {print $1}'
```

Expected output — one name per line:

```
sandbox-aap-gateway-6b4d8f9c7d
sandbox-aap-eda-api-5f7c4b8d96
...
```

> ⚠️ **Only ever delete a ReplicaSet whose DESIRED, CURRENT and READY columns are all `0`.** That is
> what the `awk` filter above enforces. An empty ReplicaSet owns no pods, so deleting it stops nothing
> and only costs you the ability to roll back to that revision. Deleting one with `1` desired **kills
> a running pod**.

**2. Delete them.** `K` is a shell function, so this loops rather than using `xargs`:

```bash
for rs in $(K get rs --no-headers | awk '$2=="0" && $3=="0" && $4=="0" {print $1}'); do
  K delete rs "$rs"
done
```

Expected output — one line per deletion:

```
replicaset.apps "sandbox-aap-gateway-6b4d8f9c7d" deleted
replicaset.apps "sandbox-aap-eda-api-5f7c4b8d96" deleted
...
```

On the day this was diagnosed, 30 were deleted and the count dropped to 12 — one live ReplicaSet per
Deployment — once the operator had recreated what it needed.

**3. Cap the history on every Deployment**, so the slots cannot silently refill:

```bash
for d in $(K get deploy -o name); do
  K patch "$d" --type=merge -p '{"spec":{"revisionHistoryLimit":1}}'
done
```

Expected output — one line per Deployment:

```
deployment.apps/sandbox-aap-gateway patched
deployment.apps/sandbox-aap-eda-api patched
...
```

Each Deployment now keeps **one** old ReplicaSet instead of ten. With 12 Deployments that is a
worst case of 24 slots out of 30, instead of 132.

> ℹ️ **What you give up.** One rollback point per Deployment rather than ten. On a sandbox that is a
> fair trade: the Custom Resource is the real source of truth, so a bad change is re-patched rather
> than rolled back.

### 4.5 Verify the fix

**1. The pods come back on their own.** You do not need to restart anything — the Deployments retry
as soon as there are free slots. On the day this was diagnosed every pod was running about **two and
a half minutes** after the deletions.

```bash
K get pods -w
```

Press `Ctrl-C` to stop watching. Readiness and startup probe warnings during the first minute are
expected and clear by themselves.

**2. Confirm every Deployment is ready and the cap is set**, in one command:

```bash
K get deploy -o custom-columns='NAME:.metadata.name,REVHIST:.spec.revisionHistoryLimit,READY:.status.readyReplicas'
```

Expected output — `REVHIST` of `1` and `READY` of `1` on every row:

```
NAME                               REVHIST   READY
sandbox-aap-gateway                1         1
sandbox-aap-eda-api                1         1
sandbox-aap-eda-default-worker     1         1
...
```

A `READY` of `<none>` on any row means that Deployment still has no pod. Re-run step 3 of §4.3 — if
the count is back at the cap, something else is consuming slots.

**3. Confirm you have headroom.** Compare this against the `limited` number from the event in §4.3:

```bash
K get rs --no-headers | wc -l
```

Observed output after the fix — 12 of the 30 slots in use, leaving 18 free for future rollouts:

```
12
```

**4. Confirm AAP itself answers.** The web interface is the real test:

```bash
curl -sk -o /dev/null -w '%{http_code}\n' "https://<your-aap-host>/"
```

Expected output:

```
200
```

For a fuller check, the gateway reports the platform's own health:

```bash
curl -sk "https://<your-aap-host>/api/gateway/v1/ping/" | python3 -m json.tool
```

Expected output includes `"status": "good"` along with the platform version and
`"db_connected": true`.

### 4.6 Why this one can come back

Unlike the §3 patch, this one is **not** recorded in the AAP Custom Resource, so two things can undo
it:

- **An operator reconcile may reset `revisionHistoryLimit`.** The operator owns these Deployments and
  rewrites fields it manages. Evidence so far is encouraging but incomplete: the setting survived
  every reconcile on the day it was applied, and **re-checked 2026-10-07 after the sandbox idled the
  whole install to zero and brought it back, all 12 Deployments still read `1`.** That covers a
  restart cycle. It does **not** cover an AAP version upgrade, which rewrites far more.
- **Re-provisioning AAP wipes it entirely.** A fresh install comes back with the default of 10 and a
  clean 30-slot budget that will fill the same way.

**So re-check it after any Custom Resource edit, any AAP upgrade and any rebuild**, with step 2 of
§4.5. If `REVHIST` has gone back to `10` or `<none>`, re-run step 3 of §4.4 — it is idempotent, so
running it when nothing has changed is harmless.

> ✅ **Cheapest early warning.** Run step 3 of §4.5 occasionally. Once the ReplicaSet count climbs
> back towards the cap you have a few rollouts of warning, instead of finding out when AAP is already
> down.

---

## 5. On a brand-new sandbox, apply both fixes first

**Neither fix survives re-provisioning.** A fresh AAP instance comes back with 400Mi limits and a
`revisionHistoryLimit` of 10, and both failures will happen again in the same order.

Do this on a new instance, in order:

1. Get a fresh OpenShift token and set up the `K` shortcut — [§2](#2-before-you-start--cluster-access).
2. **Apply the memory patch** — [§3.4](#34-the-fix--raise-three-memory-limits) — before creating
   anything in EDA.
3. **Apply the `revisionHistoryLimit` patch** — step 3 of
   [§4.4](#44-the-fix--delete-the-dead-replicasets-then-cap-the-history). Do it *after* step 2, so the
   new ReplicaSets the memory patch creates are the ones kept.
4. Wait for the reconcile and the `pg_notify` log line — steps 1 and 2 of [§3.5](#35-verify-the-fix).
5. *Then* create your EDA project. It will sync the first time.

Two other things a fresh instance invalidates:

- **Any Personal Access Token you saved is dead** and must be re-minted. On AAP 2.7 the endpoint is
  `/api/gateway/v1/tokens/`; `/api/controller/v2/tokens/` returns `404`. Anything scripted against AAP,
  including `scripts/verify_team.py`, needs the new value.
- **Any event stream UUID and token recorded in ServiceNow is stale.** A rebuilt stream gets a new
  address. That is the subject of [09 — Reconnect after an AAP rebuild](09-reconnect-after-aap-rebuild.md).

---

## 6. Gotchas worth knowing

- **`oc` may fail silently.** On one Mac, `/usr/local/bin/oc` was killed on every invocation (exit
  `137`, no output), which made `oc login` appear to succeed while writing no configuration. If
  `oc version --client` prints nothing, use `kubectl` with the `K` function from
  [§2](#2-before-you-start--cluster-access). To repair `oc`:
  `xattr -d com.apple.quarantine /usr/local/bin/oc`.
- **A restart count of `0` does not rule out an out-of-memory kill.** The worker forks child
  processes, and the kernel can kill a child without restarting the pod. If the count is `0` but a
  task never finished, read the log for a task that starts and never completes.
- **The reaper runs inside the worker it reports on.** `monitor_project_tasks` runs every 30 seconds
  in the default worker and fails anything pending for more than 600 seconds. If the worker is
  completely dead, even that message never appears and the project sits at Pending with no error at
  all.
- **Upstream does not impose the memory limits in §3.** The `eda-server-operator` default is
  `requests: {cpu 25m, memory 130Mi}` with **no** memory limit. Every limit you are fighting was added
  by the sandbox's own template. This is not an AAP defect.
- **A `NotFound` from `K get resourcequota` does not mean there is no quota.** See the warning in
  [§4.3](#43-confirm-the-diagnosis-before-changing-anything).
- **An idled sandbox looks like a broken one.** The Developer Sandbox scales workloads to zero after
  a period of inactivity. If AAP is unreachable, retry once or twice before diagnosing anything — and
  see [10 §6.4](10-troubleshooting.md#64-aap-ui-shows-a-provisioning-screen-and-the-api-returns-503).

---

## 7. Quick reference

Set up, once per terminal session — see [§2](#2-before-you-start--cluster-access) for where each value
comes from:

```bash
export T="sha256~..."; export API="https://api.<your-cluster-domain>:6443"; export NS="<your-namespace>"
K() { kubectl --token="$T" --server="$API" --insecure-skip-tls-verify=true -n "$NS" "$@"; }
```

Diagnose a project that will not sync — [§3.3](#33-confirm-the-diagnosis-before-changing-anything):

```bash
K get pods | grep eda-default-worker
K get pod <pod-name> -o jsonpath='{.status.containerStatuses[0].lastState}'
K logs <pod-name> --previous | tail -20
K get resourcequota
```

Diagnose missing pods — [§4.3](#43-confirm-the-diagnosis-before-changing-anything):

```bash
K get deploy
K get events --sort-by=.lastTimestamp | grep -i quota
K get rs --no-headers | wc -l
K get rs --no-headers | awk '$2=="0" && $3=="0" && $4=="0"' | wc -l
```

Fix, and verify:

```bash
# memory  (full patch in 3.4)
K patch ansibleautomationplatform.aap.ansible.com <cr-name> --type=merge -p '{...}'

# replicaset slots  (4.4)
for rs in $(K get rs --no-headers | awk '$2=="0" && $3=="0" && $4=="0" {print $1}'); do K delete rs "$rs"; done
for d in $(K get deploy -o name); do K patch "$d" --type=merge -p '{"spec":{"revisionHistoryLimit":1}}'; done

# verify both
K get deploy -o custom-columns='NAME:.metadata.name,REVHIST:.spec.revisionHistoryLimit,READY:.status.readyReplicas'
K logs <pod-name> | grep pg_notify
```

What the signals mean:

| Signal | Meaning |
|---|---|
| `import_state: pending` forever | The worker is not consuming tasks — check the pod, [§3](#3-an-eda-project-never-finishes-syncing) |
| `OOMKilled` / exit `137` | A memory limit is too low — [§3.4](#34-the-fix--raise-three-memory-limits) |
| `HTTP 503` on sync | The worker is not listening yet. Wait and retry — [§3.5](#35-verify-the-fix) |
| `import_state: completed` plus *"This project contains no rulebooks"* | The sync worked; the repository layout is wrong — [§3.5](#35-verify-the-fix) |
| `ReplicaSetCreateError` / `exceeded quota` | The ReplicaSet cap is full — [§4](#4-every-aap-pod-is-gone-and-rollouts-fail-on-quota) |
| Every Deployment `0/1`, postgres and redis healthy | The ReplicaSet cap is full — [§4](#4-every-aap-pod-is-gone-and-rollouts-fail-on-quota) |
| `K get resourcequota` says `NotFound` | Expected on the sandbox. Read the numbers from the event instead — [§4.3](#43-confirm-the-diagnosis-before-changing-anything) |

---

## Self-check

**On length.** This file is about 900 lines, well past the point where a *build guide* should be
split into stages. It is deliberately not split: it is entered at one symptom and read one section
deep, never top to bottom, so the thing a split would provide — a thin entry point that hands off —
is provided instead by [§0](#0-which-document-do-you-need), the [Contents](#contents) list and the
[§1 symptom index](#1-symptom-index). If a third failure is added here, split it.

**Did I skip any prerequisite steps?** Cluster access is the prerequisite for everything here, so it
is §2 rather than a note, and includes how to install `kubectl`, how to get a token that is *not* the
AAP password, and how to derive the namespace from the AAP address. `<project-id>` and `<cr-name>` are
in the placeholder table with the command that discovers each, so no command depends on a value the
reader has not been told how to find. There is no checkpoint, because this is a reference entered at
whichever symptom matches rather than a build stage.

**Is every command copy-paste ready with context?** Yes. Both `curl` commands that need the AAP
password prompt for it with `read -rsp` rather than taking it inline, so it does not land in shell
history, and the project id is a placeholder rather than the author's `1`. Every command states its
expected output, and the §4 outputs are labelled "observed" where they are the real numbers recorded
on 2026-10-06 rather than a generic example. The destructive step in §4.4 lists what it will delete
before it deletes it, and §2 warns that `K` is a shell function so no reader rewrites those loops
with `xargs`.

**Would a complete novice understand every single sentence?** §4.2 defines Deployment, ReplicaSet and
`revisionHistoryLimit` before using them, in that order, because the arithmetic in the next paragraph
needs all three. OOMKilled is defined in §3.2 where its failure is described. Two things a beginner
would otherwise read as contradictions are called out rather than left implicit: that §4.4 patches
Deployments when §3.4 forbids it, and that healthy postgres and redis pods are not evidence of a
healthy cluster.
