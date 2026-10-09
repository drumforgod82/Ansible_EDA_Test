# The three Python tools

This page explains what `verify_team.py`, `provision_team.py` and `eda_apply_rulebook_change.py`
are for, what must be true before you run them, and where the step-by-step procedures live — it is a
signpost, not a manual.

**Nothing installed yet?** Start at
[00 — Set up your own computer](../docs/00-workstation-setup.md), which covers macOS, Windows 11 and
Linux from nothing, then come back here.

**New to the project?** Read [§1 of the main README](../README.md) first, for what Event-Driven
Ansible is and what this pipeline does. Every term used below is defined in
[the glossary](../docs/glossary.md).

> 🔴 **Do not start here if you have never built a team.** Build your first one **by hand**, following
> [08 §2](../docs/08-routine-ops.md). The provisioning script removes four silent failure modes *by
> construction*, which is exactly why a successful run teaches you nothing about them — and those
> four are what you will be debugging when something breaks later. Script every team after the first.

---

## 1. What each one is

| Script | Writes anything? | What it is for |
|---|---|---|
| `verify_team.py` | **No — read-only.** GETs only; never writes to AAP, ServiceNow or Git | Checks one team's wiring across the repository, AAP and ServiceNow, and asserts the things a human eyeball misses. Run it before testing with a real record |
| `provision_team.py` | **Only with `--apply`.** Dry run by default | Builds a new team's AAP objects and renders its rulebook from an existing team's. Records a manifest, so `--destroy` removes exactly what it made and nothing else |
| `eda_apply_rulebook_change.py` | **Only with `--apply`.** Dry run by default | Makes a rulebook edit take effect: syncs the project, rewrites the activation's stream mapping and restarts it. Replaces a six-step sequence of clicks with one command. `--list` is read-only |

**Where the procedures are.** This page deliberately does not repeat the commands, so there is only
one copy to keep correct:

- Provisioning a team — [08 §2](../docs/08-routine-ops.md), including the by-hand path and the
  scripted one side by side.
- Verifying a team — [08 §5](../docs/08-routine-ops.md).
- Applying a rulebook change — [08 §6](../docs/08-routine-ops.md#6-apply-a-rulebook-change),
  written step by step for someone who has never done it. **Start there** if you have just edited a
  rulebook and nothing has happened.

> 🔴 **Read the token-scheme warning at the top of [08 §2](../docs/08-routine-ops.md) before
> provisioning anything on this instance.** Both scripts build the scheme the guides teach — one
> token per team — and this lab deliberately runs the other one. Provisioning without reading it
> leaves you with two schemes in play and no sign that anything is wrong until a rotation silently
> half-completes.

---

## 2. What must be true before you run either

### 2.1 Software

You need Python 3.9 or newer, and **one package that is not part of Python itself**: PyYAML. Both
scripts use it to confirm a rendered rulebook really parses as YAML before anything is built from it.

**Check what you already have before installing anything** — on many machines PyYAML is already
present and there is nothing to do:

```bash
python3 --version
python3 -c "import yaml; print(yaml.__version__)"
```

Expected output: `Python 3.9` or newer, then a version number such as `6.0.3`. If you get both, skip
the rest of this section.

If the second command prints `ModuleNotFoundError: No module named 'yaml'`, install it one of these
two ways.

**On macOS with Homebrew** — this is how it is installed on the machine these guides were written on:

```bash
brew install pyyaml
python3 -c "import yaml; print(yaml.__version__)"
```

Expected output: a version number on the second command.

**Anywhere, using a virtual environment** — a self-contained folder holding its own copy of Python
and its packages, so nothing is installed system-wide:

```bash
cd /path/to/Ansible_EDA_Test
python3 -m venv .venv
./.venv/bin/python -m pip install pyyaml
./.venv/bin/python -c "import yaml; print(yaml.__version__)"
```

Expected output: `pip` may print an unrelated notice about its own version, which is harmless, then
the last command prints a version number. **If you take this route, run the scripts with
`./.venv/bin/python` in place of `python3`**, or they will use your system Python and still not find
PyYAML.

> ⚠️ **`python3 -m pip install pyyaml` on its own may refuse to run**, with a message about an
> externally managed environment. That is not a broken installation — recent Python builds,
> including Homebrew's, deliberately stop you installing into the system Python. Use one of the two
> methods above instead of overriding it.

> ℹ️ **PyYAML is the only external dependency.** Everything else both scripts use is part of Python,
> which is why it is named here rather than left in a requirements file for you to find.

### 2.2 Environment variables

Both scripts read their credentials from the environment and will stop with a clear message if one
is missing. Note that the two scripts use **different ServiceNow accounts on purpose** — verifying
only needs to read, provisioning needs to write.

| Variable | `verify_team.py` | `provision_team.py` | `eda_apply_rulebook_change.py` | What it is |
|---|---|---|---|---|
| `AAP_TOKEN` | — | — | required | An AAP personal access token. `SANDBOX_AAP_PAT_TOKEN` is accepted too, so an existing setup keeps working |
| `SANDBOX_AAP_PAT_TOKEN` | required | required | accepted | An AAP personal access token. Provisioning also uses it as the EDA controller credential |
| `AAP_GATEWAY` | required | required | required | Your AAP gateway base URL, e.g. `https://<your-aap-host>` — or pass `--gateway` |
| `SN_PDI_HOST` | required | required | — | Your ServiceNow developer instance, e.g. `https://dev123456.service-now.com` |
| `SN_PDI_USERNAME` | required | — | — | An account that can **read** the route table |
| `SN_PDI_PASSWORD` | required | — | — | That account's password |
| `SN_PDI_PROVISION_USERNAME` | — | required | — | An account that can **write** to the route table and the credential tables |
| `SN_PDI_PROVISION_PASSWORD` | — | required | — | That account's password |
| `EDA_STREAM_TOKEN` | — | — | only for `--probe` | An event stream token, used to post one non-matching test event after a change |

> ⚠️ **A missing variable looks like a permissions problem.** If `provision_team.py` reaches the
> ServiceNow section and fails in a way that reads like an access error, check the variable is
> exported in *this* shell before you go auditing ServiceNow roles.

> 🔑 **Keep the secrets out of your shell history.** Store them in a password manager or the macOS
> Keychain and export them from your shell profile, rather than typing them on a command line —
> see the Keychain note in [03 §2.9](../docs/03-aap-eda-setup.md).

> ⚠️ **A shell profile is only read by interactive shells.** A tool launched from the Dock, or a
> cron job, inherits none of it, and that failure also looks like a bad credential rather than a
> missing one. Start a fresh login shell and check before blaming the token:
>
> ```bash
> echo "${#SANDBOX_AAP_PAT_TOKEN}"
> ```
>
> Expected output: a number greater than zero. `0` means it is not set in this shell.

### 2.3 Both platforms reachable

The AAP sandbox idles its workloads and a developer instance can be put to sleep, so confirm both
are awake before blaming a script. [09](../docs/09-reconnect-after-aap-rebuild.md) covers waking AAP
back up.

---

## 3. Which one to run, and when

1. **Before you test a team with a real record** — run `verify_team.py`. It is read-only, so there is
   no reason not to.
2. **After any change to a rulebook, stream, route row or activation** — run `verify_team.py` again.
   It compares the two things that only disagree when compared: the route row's stream identifier
   against the real stream, and the activation's pinned rulebook against the rulebook at the
   project's synced revision.
3. **When adding a team** — follow [08 §2](../docs/08-routine-ops.md). Preview first; the script
   writes nothing until you pass `--apply`.
4. **When removing a team you provisioned** — `--destroy`, which uses the manifest from the original
   run, so it removes what that run created rather than guessing from names.
5. **After you edit a rulebook and push it** — run `eda_apply_rulebook_change.py`. Nothing you
   pushed is live until an activation is restarted, and this is what restarts it correctly. Start
   with `--list`, which only reads:

   ```bash
   cd ~/Ansible_EDA_Test
   python3 scripts/eda_apply_rulebook_change.py --list
   ```

   Expected output: one row per activation, with an `ID`, its organization, and a `FLAGGED` column.
   Then follow [08 §6](../docs/08-routine-ops.md#6-apply-a-rulebook-change).

   > 🔴 **Events that arrive while it runs are lost, and the sender is told they succeeded.** This
   > is the one thing to understand before using it — [08 §6.6](../docs/08-routine-ops.md#66-the-window-is-silent-data-loss)
   > explains why and what to do about it.

---

## 4. Checkpoint

You are ready to use these tools when all of the following are true:

- [ ] `python3 --version` reports 3.9 or newer.
- [ ] Every variable your chosen script needs is set in the shell you will run it from.
- [ ] Both the AAP sandbox and the ServiceNow instance respond.
- [ ] You have read the token-scheme warning in [08 §2](../docs/08-routine-ops.md).
- [ ] `verify_team.py` runs against an existing, known-good team and passes.

That last one is the useful smoke test, because it proves your credentials and both endpoints at
once before you ask anything to write. Substitute a team that already exists:

```bash
cd /path/to/Ansible_EDA_Test
python3 scripts/verify_team.py --team team-a
```

Expected output: a list of `PASS` lines, then a summary of the form

```
Team A: incident + sctask + problem
46/46 checks passed.
```

The number differs per team, because it depends on how many record types that team's rulebook
handles — a type the rulebook does not mention reports `SKIP`, not `FAIL`. Any `FAIL`, or a non-zero
exit status, means stop and fix that before going further. Add `--json` if you want the result
machine-readable for CI.
