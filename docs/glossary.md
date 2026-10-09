# Glossary

**This document defines every term and acronym used across the build guides, in one place.**

> **This is a reference, not a stage.** Every numbered document links here. If a word in any guide is
> unfamiliar, it is defined below.

---

## The two platforms

| Term | Definition |
|---|---|
| **AAP** | **Ansible Automation Platform.** Red Hat's product for running Ansible at scale. It has two halves, below |
| **Automation Execution** | The half of AAP that *runs* playbooks. Formerly called "Controller" or "Tower" |
| **Automation Decisions** | The half of AAP that runs **EDA** — rulebooks, event streams, activations |
| **EDA** | **Event-Driven Ansible.** Automation that reacts to events as they arrive, instead of running on a schedule or being launched by a person |
| **ServiceNow** | The IT service-management platform that holds the incidents, tasks and problems this project reacts to |
| **PDI** | **Personal Developer Instance.** A free, full ServiceNow instance for one developer, with complete administrator rights. **Reclaimed after about ten days of inactivity** |

> ℹ️ **"Flow Designer" and "Workflow Studio" are the same thing.** ServiceNow renamed it; both names
> appear in the interface and in these guides depending on the release. Either navigation path gets
> you to the same place.

---

## Ansible side

| Term | Definition |
|---|---|
| **Playbook** | An Ansible file that *does* work — restarts a service, writes back to ServiceNow. **One shared playbook serves every team** |
| **Rulebook** | An Ansible file that *decides whether* work should happen. **Not a playbook** — different keywords, different purpose. One per team. See [Rulebook anatomy](rulebook-anatomy.md) |
| **Ruleset** | One top-level block in a rulebook, named by its outermost `name:` |
| **Rule** | One condition-plus-action pair inside a ruleset |
| **Condition** | A boolean expression over an incoming event. True means the action runs |
| **Job template** | A saved, runnable configuration of a playbook in AAP. **Matched by exact name** from a rulebook |
| **Activation** | A long-running container holding one rulebook, waiting for events. One per team |
| **Event stream** | A URL plus a token that ServiceNow posts events to. One per team |
| **Source mapping** | The record on an activation that says which **event stream** feeds which `sources:` entry in its rulebook. Pins a `rulebook_hash`, so it is tied to one exact revision of the rulebook file |
| **`rulebook_hash`** | The plain SHA-256 of a rulebook file's bytes, stored inside a source mapping. Any byte change, including a trailing newline, produces a different one |
| **Rule engine** | The component inside an activation that evaluates a rulebook's conditions against arriving events. Implemented with Drools, and the thing `enable_persistence` would give a database to |
| **`LISTEN`/`NOTIFY`** | A PostgreSQL messaging feature where a sender announces a message and only processes *currently listening* receive it. There is no queue, so a message announced while nothing listens is discarded. This is how an event stream reaches an activation, and why a stopped activation loses events |
| **Decision environment** | The container image an activation runs inside |
| **Inventory** | The list of machines a playbook targets. Here it is just `localhost` |
| **Collection** | A packaged bundle of Ansible content. `servicenow.itsm` is the one this project needs |
| **`extra_vars`** | Variables passed *into* a job at launch time. The rulebook builds them from the event; the playbook reads them |
| **Jinja** | The `{{ ... }}` templating syntax Ansible uses to read values out of data |
| **`event.payload`** | The JSON body ServiceNow sent, verbatim |
| **`event.meta`** | Metadata **AAP itself adds**. The sender cannot set or forge it |
| **PAT** | **Personal Access Token.** A long-lived credential used instead of a password by scripts and API clients |
| **OOMKilled** | "Out Of Memory, Killed". A container exceeding its memory ceiling is terminated instantly, with no error from the program itself |

---

## ServiceNow side

| Term | Definition |
|---|---|
| **Scope / scoped application** | A namespace owning a set of ServiceNow records, so they can be moved as one unit. **Records created in the wrong scope cannot be moved** |
| **Global** | The default, un-namespaced scope. Most of the platform's own tables live here |
| **`sys_id`** | A 32-character identifier ServiceNow gives every record. **Stable** — it does not change when you rename the record |
| **Reference field** | A column pointing at a row in another table. It stores that row's `sys_id`, **not its name** |
| **Display column** | The one column ServiceNow shows when something points at this table. Without one, you see raw `sys_id`s |
| **Flow** | An automation that starts by itself when a record changes |
| **Trigger** | The condition that starts a flow |
| **Action** | A reusable sequence of steps a flow calls, like a function |
| **Step** | One unit inside an action — a script, an HTTP call |
| **Action input** | A value the *flow* passes **into** an action |
| **Step variable** | A value one *step* inside an action can read. **Separate from an action input** — both must be wired |
| **Data pill** | A small rounded token representing a value from an earlier step, which you drag into a later field |
| **Dot-walk** | Following a reference from one record into a field on the record it points at — shown in the interface as `➛`. Dragging `Record ➛ Number` instead of `Record` is **dot-walking**, and in this project it is almost always wrong |
| **Work note** | A comment written onto a ServiceNow record. The automation's visible output: it is how you see what happened |
| **SCTASK** | A **Catalog Task** — the work item created when someone orders something from the service catalog |
| **RITM** | A **Requested Item** — the catalog request an SCTASK belongs to. Holds the catalog variables |
| **Catalog item** | One orderable thing in the service catalog |
| **Order guide** | A catalog entry that bundles several items. Enrolling a guide enrols everything ordered through it |
| **ACL** | **Access Control List.** A ServiceNow rule deciding who can read or write a record |
| **Connection & Credential Alias** | A ServiceNow object bundling "where to send a request" with "what credential to send it with" |
| **Update Set** | A ServiceNow export file holding configuration changes. How you back up or move work between instances |
| **`password2`** | ServiceNow's encrypted-property field type. **Deprecated** — `GlideEncrypter` now returns null, so values cannot be read back |
| **ES5 / ES12** | Two versions of JavaScript. ServiceNow runs scripts in one mode or the other; newer instances default to ES12 |

---

## Infrastructure terms

Needed only if you self-host AAP on OpenShift. See [01 §3](01-provision-aap.md), and
[AAP platform troubleshooting](aap-platform-troubleshooting.md) when the cluster itself is the
problem.

| Term | Definition |
|---|---|
| **OpenShift** | Red Hat's Kubernetes platform. AAP runs on top of it as a set of containers |
| **Namespace** | A named folder inside the cluster holding your things |
| **`kubectl`** | The command-line tool for talking to the cluster |
| **Custom Resource (CR)** | A single configuration record describing your whole AAP install. **This is what you patch**, never the running containers |
| **Operator** | A background process that reads the Custom Resource and makes the cluster match it |
| **Reconcile** | The operator noticing your change and applying it. Takes a few minutes |
| **Pod** | One running container, or a small group of containers that run together. The unit the cluster starts and stops |
| **Deployment** | The record saying "keep this many copies of this container running". AAP is made of about twelve of them |
| **ReplicaSet** | What a Deployment creates to run its pods. A change to the container's settings makes a **new** ReplicaSet and scales the old one to zero pods, keeping it as a rollback point |
| **`revisionHistoryLimit`** | How many of those old, empty ReplicaSets a Deployment keeps. **Default 10** — on a quota-limited cluster that is enough to fill the cap. See [AAP platform troubleshooting §4](aap-platform-troubleshooting.md) |
| **StatefulSet** | Like a Deployment, but for things holding data — the AAP database and cache. It manages its pods directly and creates **no** ReplicaSets |
| **Quota** | A cap the cluster puts on how much of something your namespace may use. Memory, CPU and the **number of ReplicaSets** are each capped separately |
| **OOMKilled** | "Out Of Memory, Killed". A container exceeding its memory ceiling is terminated instantly, with no error from the program itself. Also listed under *Ansible side*, where its failures appear |

---

## Concepts

| Term | Definition |
|---|---|
| **JSON** | A text format for structured data — the format of every message between ServiceNow and AAP |
| **Fail-closed** | If something unexpected happens, **nothing is sent.** The safe default, and what this project aims for |
| **Fail-open** | If something unexpected happens, **everything is sent.** What you are avoiding |
| **Fan-out** | One event delivered to *every* listener, rather than to one. Event streams are fan-out, **not a queue** |
| **Non-durable** | No stored backlog. An event posted while nothing is listening is **dropped silently** |
| **Enrollment** | Whether a record is in scope for automation at all. **Only Catalog Tasks have this** — incidents and problems have no catalog item |
| **Routing** | Which team's event stream a record goes to. Keyed on **assignment group** |

---

## Self-check

**Did I skip any prerequisite steps?** No steps are performed here.

**Is every command copy-paste ready with context?** There are no commands in this document.

**Would a complete novice understand every single sentence?** Each definition avoids using another
undefined term, and where one definition depends on another the dependency is defined in the same
table or above it. The two most consequential entries — **dot-walk** and **work note** — are written
so they can be understood without having opened ServiceNow, because both appear in warnings a reader
may hit before they have built anything.
