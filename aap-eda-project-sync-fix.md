# Fixing "EDA Project won't sync" on AAP 2.7 (Red Hat Developer Sandbox)

**Written:** 2026-09-18
**Applies to:** Ansible Automation Platform 2.7 on OpenShift, installed via the AAP Operator.
Specifically a Red Hat **Developer Sandbox** deployment, but the same fix applies to any AAP
install whose template sets small memory limits.

---

## 1. The symptom

You add a Project under **Automation Decisions** (Event-Driven Ansible) pointing at a public
GitHub repo. It sits at **Pending**, and after about 10 minutes flips to **Failed** with:

```
Task was stuck in pending state. Marked as failed by monitoring system.
```

The confusing part: the **same repo** added as a Project under **Automation Execution**
(automation controller) syncs successfully in a couple of seconds.

Everything in the AAP UI looks healthy. The EDA service reports "good".

---

## 2. What is actually wrong (in plain English)

**Your project configuration is fine.** The repo URL, the branch, the credential (none
needed for a public repo), and the repo layout are all irrelevant to this failure.

The problem is that the pod that does the git clone **runs out of memory and is killed
mid-clone**.

Here is the chain:

1. You click Sync. The EDA API writes a database row with `import_state = pending` and puts
   a task on a queue named `default`.
2. A pod called `<name>-eda-default-worker` picks that task up and starts cloning.
3. That clone is **not** a plain `git clone`. EDA runs `ansible-runner`, which runs a small
   Ansible playbook, which then runs `git`. That is a lot of processes in one container.
4. The container has a **400Mi memory limit**. The Django worker process already occupies
   most of it. Adding ansible-runner + git blows past the limit in about **1.3 seconds**.
5. Linux kills the container (`OOMKilled`, exit code 137). The task dies with it.
6. Task delivery uses PostgreSQL `pg_notify`, which has **no backing table**. It is
   fire-and-forget. A task whose worker died is simply gone — it is never retried.
7. The row stays at `pending` forever. A separate monitor job notices it 10 minutes later
   and rewrites it as `failed` with that misleading message.

### Why the Automation Execution project works but Automation Decisions does not

They are completely different code paths:

| | Where the git clone runs | Memory available |
|---|---|---|
| **Automation Execution** (controller) | its own execution-environment pod | its own budget |
| **Automation Decisions** (EDA) | inside the eda-default-worker pod | 400Mi, shared with Django |

A controller project syncing successfully tells you **nothing** about the EDA side. Do not
treat it as evidence that networking, DNS, or credentials are fine for EDA (although in this
case they were).

### Why the UI says everything is healthy

The health checks only probe the EDA **API** and **event-stream** pods. They never check the
worker. So `/api/eda/v1/status/` returns `good` and the gateway shows the `eda` service as
`good` while the worker is dying repeatedly.

---

## 3. What you need before you start

1. **Cluster access.** You must be able to reach the OpenShift API, not just the AAP web UI.
   This cannot be fixed from the AAP UI — there is no button for it.
2. **`kubectl`** (or `oc`). See the note in section 8 if `oc` misbehaves.
3. **A login token.** On Developer Sandbox the only identity provider is browser-based, so
   the AAP admin password will *not* log you in to OpenShift. Get a token here:

   ```
   https://oauth-openshift.apps.<your-cluster-domain>/oauth/token/request
   ```

   Click **Display Token** and copy the `--token=sha256~...` value.

4. **Your namespace name.** If your AAP URL is
   `https://sandbox-aap-jdrebel2-dev.apps.rm1.0a51.p1.openshiftapps.com/`, then OpenShift
   route names are `<route>-<namespace>`, so the route is `sandbox-aap` and the namespace is
   **`jdrebel2-dev`**.

### Set up a shortcut

Run this once per terminal session. It avoids `oc login`, so your existing kubectl context
is left alone:

```bash
export T="sha256~PASTE_YOUR_TOKEN_HERE"
export API="https://api.rm1.0a51.p1.openshiftapps.com:6443"
export NS="jdrebel2-dev"

K() { kubectl --token="$T" --server="$API" --insecure-skip-tls-verify=true -n "$NS" "$@"; }
```

Test it:

```bash
K get pods
```

---

## 4. Confirm the diagnosis before changing anything

Do these in order. Each one is read-only.

### Step 4a — Read the project's real error from the API

```bash
curl -sk -u admin:'YOUR_AAP_ADMIN_PASSWORD' \
  "https://YOUR-AAP-HOST/api/eda/v1/projects/" | python3 -m json.tool
```

Look at `import_state` and `import_error`. `git_hash` being empty confirms no clone ever
completed.

### Step 4b — Find the worker pod

```bash
K get pods | grep eda
```

You want the one named `...-eda-default-worker-...`. Note its **RESTARTS** column.

### Step 4c — Prove it was OOMKilled

Replace the pod name with yours:

```bash
K get pod sandbox-aap-eda-default-worker-XXXXX -o json | python3 -c "
import sys, json
p = json.load(sys.stdin)
for c in p['spec']['containers']:
    print('limits:', c.get('resources', {}).get('limits'))
for cs in p['status']['containerStatuses']:
    print('restarts:', cs['restartCount'])
    print('lastState:', json.dumps(cs.get('lastState'), indent=2))
"
```

You are looking for:

```
limits: {'cpu': '500m', 'memory': '400Mi'}
lastState: { "terminated": { "reason": "OOMKilled", "exitCode": 137, ... } }
```

`reason: OOMKilled` is the smoking gun.

### Step 4d — See the clone die in the log

```bash
K logs sandbox-aap-eda-default-worker-XXXXX --previous | tail -20
```

The log **ends mid-clone**, with no error after it:

```
13:00:16,993 INFO aap_eda.tasks.project Task started: Sync project (project_id=1)
13:00:16,999 INFO aap_eda.services.project.scm Cloning repository: https://github.com/...
   <nothing after this — the container was killed>
```

### Step 4e — Check you have quota room for the fix

```bash
K get resourcequota
```

Look at the `compute-deploy` row. On Developer Sandbox you typically have **30Gi** for
`limits.memory` and only around 15Gi in use, so there is plenty of headroom.

**The tight one is `requests.cpu`** (e.g. `1950m / 3`). So when you raise memory, **do not
raise CPU requests** — you may not have room.

---

## 5. The fix

### Why you must edit the Custom Resource, not the Deployment

The AAP Operator owns these Deployments. If you edit the Deployment directly, the operator
reverts your change within a minute or two. You must edit the
**AnsibleAutomationPlatform** custom resource, and let the operator apply it.

### The command

This raises all three components that run out of memory on a sandbox-sized install. Doing
them in **one** patch means the operator reconciles once instead of three times.

```bash
K patch ansibleautomationplatform.aap.ansible.com sandbox-aap --type=merge -p '{
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

Replace `sandbox-aap` with your CR name if different — find it with
`K get ansibleautomationplatform`.

### What each piece does

| CR path | Pod affected | Default | New | Why |
|---|---|---|---|---|
| `spec.eda.default_worker` | `eda-default-worker` | 400Mi | **1Gi** | Runs the git clone. **This is the project-sync fix.** |
| `spec.eda.activation_worker` | `eda-activation-worker` | 400Mi | **1Gi** | Supervises rulebook activations; OOMs once events start flowing. |
| `spec.api` | `gateway` (api container) | 1000Mi | **2Gi** | The web UI/API. When it OOMs, the UI shows a "provisioning" screen and the API returns 503. |

Total cost: roughly **+2.3Gi** of `limits.memory`, against a 30Gi ceiling.

CPU limits and CPU requests are deliberately left alone, because `requests.cpu` is the quota
that is actually near its ceiling.

### If your edit is rejected

If the patch fails complaining about quota, you have genuinely run out of room. Free some by
disabling a component you are not using, in the same patch:

```json
"hub": {"disabled": true}
```

On the sandbox measured here this was **not necessary** — there was ~15Gi of memory
headroom. Do not disable hub reflexively.

---

## 6. Verify the fix

### Step 6a — Wait for the operator (about 3 minutes)

The CR changes instantly but the Deployment does not. Watch for it:

```bash
K get deploy sandbox-aap-eda-default-worker \
  -o jsonpath='{.spec.template.spec.containers[0].resources.limits.memory}{"\n"}'
```

Keep running it until it prints `1Gi`. Then:

```bash
K get pods | grep eda-default-worker
```

You want a **new** pod (low AGE) that is `1/1 Running` with **0 restarts**.

### Step 6b — Wait for the worker to actually start listening

This matters. The pod can be `Running` for ~11 seconds before it is ready to accept work:

```bash
K logs sandbox-aap-eda-default-worker-XXXXX | grep pg_notify
```

Wait for:

```
dispatcherd.brokers.pg_notify Set up pg_notify listening on channel 'default'
```

### Step 6c — Re-sync the project

In the UI: **Automation Decisions → Projects → your project → ⋮ → Sync**.

Or by API:

```bash
curl -sk -u admin:'YOUR_AAP_ADMIN_PASSWORD' -X POST \
  -w '\nHTTP:%{http_code}\n' \
  "https://YOUR-AAP-HOST/api/eda/v1/projects/1/sync/"
```

**If you get HTTP 503 "Project workers unavailable", that is not a failure.** AAP 2.7 checks
worker health before queuing, and you simply asked too early. Wait for the `pg_notify` line
from Step 6b and try again.

### Step 6d — Confirm success

```bash
curl -sk -u admin:'YOUR_AAP_ADMIN_PASSWORD' \
  "https://YOUR-AAP-HOST/api/eda/v1/projects/1/" | python3 -m json.tool | grep -E 'import_state|git_hash'
```

Success looks like:

```
"import_state": "completed",
"git_hash": "81a1695a47bdc3f6f97af87cbcf8ec6f6adeeba2"
```

A healthy sync takes about **3 seconds**:

```
Task started: Sync project (project_id=1)
Cloning repository: https://github.com/you/your-repo.git
Task complete: Sync project (project_id=1)
```

### Step 6e — Confirm your rulebooks were found

```bash
curl -sk -u admin:'YOUR_AAP_ADMIN_PASSWORD' \
  "https://YOUR-AAP-HOST/api/eda/v1/rulebooks/" | python3 -m json.tool | grep '"name"'
```

---

## 7. Doing this on a brand-new sandbox (the important part)

**These patches do not survive re-provisioning.** A fresh AAP instance comes back with the
400Mi limits, and the project sync will fail again exactly the same way.

Recommended order on a new instance:

1. Get a fresh OpenShift token (section 3).
2. **Apply the patch from section 5 immediately**, before creating anything in EDA.
3. Wait for reconcile and for the `pg_notify` log line (section 6a/6b).
4. *Then* create your EDA Project. It will sync the first time.

Also remember, on a new instance:

- Any **Personal Access Token** you saved is invalid and must be re-minted. On AAP 2.7 the
  endpoint is `/api/gateway/v1/tokens/` — `/api/controller/v2/tokens/` returns 404.
- If you use an **Event Stream**, its URL contains a new random UUID, so anything posting to
  it (e.g. a ServiceNow Connection record) must be updated, and the token re-created on both
  sides.

---

## 8. Gotchas worth knowing

**`oc` may silently fail.** On one Mac, `/usr/local/bin/oc` was killed on every invocation
(exit 137, no output), which made `oc login` appear to succeed while writing no config. If
`oc version --client` prints nothing, use `kubectl` with the `K()` function from section 3.
To repair `oc`: `xattr -d com.apple.quarantine /usr/local/bin/oc`.

**A restart count of 0 does not rule out OOM.** The worker forks child processes. The kernel
can kill a child without restarting the pod. If the count is 0 but a task never finished,
read the log for a task that starts and never completes.

**The reaper runs inside the worker it is reporting on.** `monitor_project_tasks` runs every
30 seconds in the default worker and fails anything pending longer than 600 seconds. If the
worker is completely dead, even that message never appears, and the project sits at Pending
indefinitely with no error at all.

**Upstream does not impose these limits.** The `eda-server-operator` default is
`requests: {cpu 25m, memory 130Mi}` with **no memory limit** and `replicas: 2`. Every limit
you are fighting was added by the sandbox's own template. This is not an AAP bug.

---

## 9. Quick reference

```bash
# setup
export T="sha256~..."; export API="https://api.<cluster>:6443"; export NS="<namespace>"
K() { kubectl --token="$T" --server="$API" --insecure-skip-tls-verify=true -n "$NS" "$@"; }

# diagnose
K get pods | grep eda
K get pod <default-worker-pod> -o jsonpath='{.status.containerStatuses[0].lastState}'
K logs <default-worker-pod> --previous | tail -20
K get resourcequota

# fix  (see section 5 for the full patch)
K patch ansibleautomationplatform.aap.ansible.com <cr-name> --type=merge -p '{...}'

# verify
K get deploy sandbox-aap-eda-default-worker -o jsonpath='{.spec.template.spec.containers[0].resources.limits.memory}'
K logs <new-worker-pod> | grep pg_notify
```

| Value | Meaning |
|---|---|
| `import_state: pending` forever | worker not consuming — check the pod |
| `import_state: completed`, `import_error: "This project contains no rulebooks."` | sync worked; wrong repo layout. Rulebooks must be in `extensions/eda/rulebooks/` or `rulebooks/` at repo root. Not a recursive search. |
| `HTTP 503` on sync | worker not listening yet — wait and retry |
| `OOMKilled` / exit `137` | memory limit too low |
