# 02 — Provision the ServiceNow PDI

**This document covers getting a free ServiceNow instance and enabling the plugins this project
needs, starting from having no ServiceNow account at all.**

> **Previous stage:** [01 — Provision AAP](01-provision-aap.md) · **Next stage:**
> [03 — AAP / EDA setup](03-aap-eda-setup.md)
>
> **You can often skip this.** A ServiceNow instance survives an AAP rebuild completely. If only AAP
> died, your instance is intact — go to [09 — Reconnecting ServiceNow](09-reconnect-after-aap-rebuild.md)
> instead. This document is for starting from nothing, or for replacing a lost instance.
>
> **Time:** 20 minutes of work, plus up to an hour of waiting for the instance to be built.

> **Any unfamiliar word?** Every term and acronym used in these guides is defined in the
> [Glossary](glossary.md) — including AAP, EDA, PDI, SCTASK, data pill, dot-walk, work note
> and `extra_vars`.

---

## 0. Words you'll need

| Term | What it means here |
|---|---|
| **PDI** | **Personal Developer Instance** — a free, full ServiceNow instance for one developer, with complete administrator rights |
| **Plugin** | An optional ServiceNow feature you switch on. Some bring sample records with them |
| **Demo data** | Sample records a plugin can install alongside itself, so features have something to act on |
| **Scoped application** | A namespace that owns a set of records. You create one in [04](04-servicenow-app.md) |
| **Update Set** | A ServiceNow export file holding a set of configuration changes. How you move work between instances, or back up |
| **ES5 / ES12** | Two versions of JavaScript. ServiceNow runs scripts in one mode or the other, and newer instances default to the newer one |

---

## 1. Create the account and request the instance

1. Go to <https://developer.servicenow.com> and choose **Sign up**. The developer programme account
   is free.
2. Sign in, then choose **Request Instance**.
3. Wait. Provisioning usually takes a few minutes and can take up to an hour.
4. When it finishes, the site shows you three things. **Record all three before leaving the page:**
   - the **instance URL**, of the form `https://devNNNNNN.service-now.com`
   - the **admin username**
   - the **admin password**

Your instance name is the `devNNNNNN` part. For example, if your URL is
`https://dev211593.service-now.com`, your instance is `dev211593`. You will need that string in
[03 §1](03-aap-eda-setup.md) when you build the AAP credential that points back here.

> ℹ️ **Deep links on vendor sites move.** If a path above has changed, search the developer portal for
> the product name rather than trusting a URL here.

> ✅ **Verify:** you can log in at your instance URL with the admin account, and the ServiceNow
> interface loads.

---

## 2. Understand the reclaim rule before you build anything

> 🔴 **A PDI is reclaimed after about ten days of inactivity, and you lose everything on it.** For
> this project that means the scoped application, the action, the flow, all three tables, and every
> route row. There is no recovery and no warning email you can rely on.

Two habits make that survivable. Adopt both:

1. **Log in periodically.** The inactivity clock resets on use.
2. **Keep the source of truth somewhere else.** Export the scoped application to an **Update Set**,
   or publish it to source control. Rebuilding by hand from [04](04-servicenow-app.md) through
   [06](06-servicenow-flow.md) takes hours. Re-importing an Update Set takes minutes.

> ℹ️ The same reasoning applies to the AAP side, which is why
> [09](09-reconnect-after-aap-rebuild.md) exists as its own document.

---

## 3. Confirm you have full administrator rights

**You need admin on this instance.** That is a requirement, not a convenience:

- [04](04-servicenow-app.md) creates a **scoped application** and three tables.
- [04 §2](04-servicenow-app.md) grants two roles to the account AAP authenticates as.
- [06](06-servicenow-flow.md) sets a flow to run as **System user**.

A restricted account cannot do any of those. A PDI gives you admin by default, so this is only worth
checking if someone else provisioned the instance for you.

> ✅ **Verify:** type `sys_user_role_list.do` into the navigation filter and confirm the page loads.
> If you are not an admin, it will not.

---

## 4. Enable the four plugins

Go to **All → System Applications → All Available Applications → All**, then search for and install
each of these:

| Plugin | Install demo data? |
|---|---|
| Event Management | **Yes, with demo data** |
| Flow Designer support for the Service Catalog | No |
| ServiceNow IntegrationHub Installer | No |
| ServiceNow IntegrationHub Professional Pack Installer | No |

Install them one at a time and let each finish before starting the next.

> ℹ️ **Why Event Management needs demo data and the others do not.** The incident payload script reads
> alert context from the `em_alert` table when an incident originated from an alert. The demo data
> gives you alerts to test that path against. The other three plugins only supply capability, not
> records.

> ✅ **Verify:** each of the four shows as **Installed** in that list.

<details>
<summary><strong>Optional:</strong> Service Operations Workspace / Site Reliability, if your region's portal does not offer them</summary>

Some PDIs do not expose these on the public developer portal. Install them from inside the instance
instead:

1. Log in as admin.
2. Go to **All → System Applications → All Available Applications → All**.
3. Search for `sn_sow_itsm_cont` — *Service Operations Workspace ITSM Applications*. Install or
   update it.
4. Then look in the same menu for *Service Reliability Management* (`sn_srm`), also listed as Site
   Reliability Metrics.

Neither is required for the pipeline in these documents. Install them only if you want the workspace
experience.

</details>

---

## 5. One thing that will differ on a new instance

> ⚠️ **A newly requested PDI may be on a newer ServiceNow release than these documents were written
> against, and platform defaults do change between releases.**

The one that matters here: since the **Xanadu** release, newly created scripts default to **ES12**
(ES2021) JavaScript mode rather than **ES5**, regardless of the application's own setting.

The canonical scripts in [`docs/scripts/`](scripts/) are ES5 — they use `var`, with no arrow
functions and no template literals. **ES5 runs correctly in either mode**, so this does not block
you. See [05 §9](05-servicenow-action.md) for the one consequence worth knowing.

> ℹ️ **Where this document disagrees with your instance, your instance is right.** Verify against it
> rather than against this page.

---

## 6. Placeholders used from here on

| Placeholder | Meaning | Example |
|---|---|---|
| `<your-pdi>` | Your instance name | `dev211593` |
| `<your-scope>` | The scope prefix ServiceNow generates for your app in [04](04-servicenow-app.md) | `x_12345_myapp` |
| `<your-aap-host>` | Your AAP gateway hostname from [01](01-provision-aap.md) | `aap.example.com` |

---

## Checkpoint

- [ ] You can log in to `https://<your-pdi>.service-now.com` as admin
- [ ] You have recorded the instance URL, username and password somewhere safe
- [ ] `sys_user_role_list.do` loads, confirming admin rights
- [ ] All four plugins show as **Installed**
- [ ] Event Management was installed **with** demo data
- [ ] You know the reclaim rule in §2 and have picked a backup habit

**Next:** [03 — AAP / EDA setup](03-aap-eda-setup.md). If AAP is already built and running, skip
ahead to [04 — The ServiceNow app](04-servicenow-app.md).

---

## Self-check

**Did I skip any prerequisite steps?** No. The account comes before the instance request, the
instance name is captured at the point it is shown rather than assumed later, and the admin check is
its own step because three later documents depend on it.

**Is every command copy-paste ready with context?** The only things to type are two navigation
paths — `sys_user_role_list.do` and `sn_sow_itsm_cont` — and both state where to type them and what
a successful result looks like.

**Would a complete novice understand every single sentence?** PDI, plugin, demo data, Update Set and
ES5/ES12 are all defined in §0 before use. The reclaim rule is stated as a consequence in terms of
what is lost rather than as a policy, because the cost is the part that makes someone act on it.
