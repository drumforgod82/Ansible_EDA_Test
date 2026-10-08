# 00 — Set up your own computer

This page gets your own computer ready to run the two Python tools in this repository, starting from
nothing installed and assuming no prior experience.

**Next stage:** [01 — Provision AAP](01-provision-aap.md). You do not need this page to follow the
numbered build guides by hand; you need it only to run the tools in
[`scripts/`](../scripts/README.md).

> ℹ️ **How far each set of instructions has been checked.** Honesty matters more here than
> tidiness, because an instruction that does not work is worse than no instruction at all.
>
> | Platform | Status |
> |---|---|
> | **macOS** | **Verified.** Every command on this page was run on macOS 26.7.1 with zsh, and the output shown is the output observed |
> | **Windows 11** | **Not yet run end to end.** Written from standard practice. Treat §7 as a checklist to confirm the first time someone uses it, and correct this page if anything differs |
> | **Linux** | **Not yet run end to end.** Same caveat. The commands follow each distribution's normal package manager |
>
> If you are the first person to use the Windows or Linux path, please fix anything that is wrong
> here as you go. That is more useful than working around it silently.

---

## 0. Words you'll need

Nothing here assumes you have met these before.

| Term | What it means |
|---|---|
| **Terminal** | A window where you type commands instead of clicking. On macOS it is an app called **Terminal**; on Windows 11 it is **Windows Terminal** or **PowerShell**; on Linux it is usually **Terminal** or **Console** |
| **Shell** | The program inside the terminal that reads what you type and runs it. macOS uses **zsh**, Windows uses **PowerShell**, Linux usually uses **bash** |
| **Prompt** | The text the shell prints while waiting for you, often ending in `$`, `%` or `>`. When this page shows a command, do **not** type the prompt character |
| **Package manager** | A tool that installs software for you and keeps track of it, so you do not download installers by hand. macOS has **Homebrew**, Windows 11 has **winget**, Linux distributions have their own |
| **Environment variable** | A named value the shell hands to any program it starts. The tools here read their passwords and addresses from these, so nothing secret has to be typed on a command line |
| **Repository**, or **repo** | A folder of files tracked by Git, including its full history. This project is one |
| **Clone** | To make your own local copy of a repository |
| **Git** | The program that does the cloning, and that records changes |

Everything else is defined in [the glossary](glossary.md).

---

## 1. What you need, and why

Four things. Each one earns its place:

| What | Why you need it |
|---|---|
| **Python 3.9 or newer** | Both tools are written in Python. 3.9 is the oldest version they are written for |
| **PyYAML** | A Python add-on. The tools use it to confirm a rulebook file really is valid YAML before anything is built from it. It is the **only** add-on needed |
| **Git** | To get your own copy of this repository, and to push a new team's rulebook so AAP can see it |
| **A plain-text editor** | To read and edit YAML files. Anything that saves plain text will do. A word processor will **not** — it adds invisible formatting that breaks YAML |

You do **not** need Ansible, OpenShift tooling, or anything from Red Hat installed locally. The tools
talk to AAP and ServiceNow over the network.

---

## 2. Install the tools

**Open the section for your operating system and ignore the other two.** They are collapsed so you
do not read instructions meant for a different computer.

<details>
<summary><strong>macOS</strong> — verified on macOS 26.7.1</summary>

### 2.1 Open a terminal

Press **Command + Space**, type `Terminal`, press **Return**. A window opens with a prompt ending
in `%`.

### 2.2 Install Git

On macOS, Git arrives with Apple's developer command-line tools. Run:

```bash
xcode-select --install
```

A dialog box appears; choose **Install** and wait. If Git is already present you will instead see a
note beginning `xcode-select: note: Command line tools are already installed`, which means you are
done with this step — it is information, not an error.

Check it:

```bash
git --version
```

Expected output: a line beginning `git version`, for example `git version 2.23.0`. Any version from
2.x onward is fine.

### 2.3 Install Homebrew

Homebrew is the package manager this page uses for everything else. Check whether you already have
it:

```bash
brew --version
```

If that prints a version such as `Homebrew 7.0.4`, skip ahead to §2.4. If it instead prints
`command not found`, install Homebrew by following the one command on the front page of
<https://brew.sh> — it is a single line that you paste into the terminal. It will ask for your
password and explain what it is about to do.

> ⚠️ **Homebrew may tell you to run two extra commands afterwards**, to add itself to your `PATH` —
> the list of places your shell looks for programs. Do run them; without that step, `brew` works in
> the window where you installed it and nowhere else.

### 2.4 Install Python and PyYAML

```bash
brew install python pyyaml
```

This takes a few minutes and prints a lot of progress output. Then check both:

```bash
python3 --version
python3 -c "import yaml; print(yaml.__version__)"
```

Expected output: `Python 3.13.3` or any version 3.9 or newer, then a version number such as `6.0.3`.

> ℹ️ **Why `brew install pyyaml` rather than `pip install pyyaml`.** Recent Python builds, Homebrew's
> included, deliberately refuse to let you install packages into the system Python and print a
> message about an *externally managed environment*. That is working as intended, not a fault. Using
> Homebrew avoids the problem entirely. If you would rather keep Python packages separate from the
> system, §2.4a shows how.

<details>
<summary><strong>Optional:</strong> §2.4a — using a virtual environment instead</summary>

A **virtual environment** is a folder containing its own private copy of Python and its packages, so
nothing is installed system-wide. You do not need this, but it is good practice if you work on
several Python projects.

```bash
cd ~/Ansible_EDA_Test
python3 -m venv .venv
./.venv/bin/python -m pip install pyyaml
./.venv/bin/python -c "import yaml; print(yaml.__version__)"
```

Expected output: `pip` may print an unrelated notice about upgrading itself, which is harmless, then
a version number such as `6.0.3`.

> 🔴 **If you take this route, run every later command with `./.venv/bin/python` in place of
> `python3`.** Using `python3` will use the system Python, which does not have PyYAML, and the error
> will look like a missing file rather than the wrong interpreter.

</details>

</details>

<details>
<summary><strong>Windows 11</strong> — not yet run end to end; please correct anything wrong</summary>

### 2.1 Open a terminal

Press the **Windows** key, type `Windows Terminal`, press **Enter**. A window opens with a prompt
ending in `>`. The shell inside is **PowerShell**.

> ℹ️ **If Windows Terminal is not installed**, search for `PowerShell` instead and use that. Both
> work for everything on this page.

### 2.2 Install Git, Python and PyYAML

Windows 11 includes a package manager called **winget**. Check it first:

```powershell
winget --version
```

Expected output: a version string such as `v1.8.1911`. If the command is not found, install **App
Installer** from the Microsoft Store, which provides winget, then reopen the terminal.

Install Git and Python:

```powershell
winget install --id Git.Git -e
winget install --id Python.Python.3.12 -e
```

Each prints progress and finishes with a success message.

> 🔴 **Close the terminal and open a new one after installing.** New programs are not visible to a
> terminal window that was already open, and the resulting `command not found` looks like a failed
> installation when it is not.

Check Git and Python:

```powershell
git --version
python --version
```

Expected output: a line beginning `git version`, then `Python 3.12.x` or newer.

> ⚠️ **On Windows the command is `python`, not `python3`.** Everywhere later on this page and in the
> other guides that shows `python3`, type `python` instead. If you type `python3` you may get a
> Microsoft Store page instead of an error, which is confusing.

Install PyYAML:

```powershell
python -m pip install pyyaml
python -c "import yaml; print(yaml.__version__)"
```

Expected output: pip prints its progress, then a version number such as `6.0.3`.

> ℹ️ **The externally-managed-environment refusal described in the macOS section does not normally
> happen on Windows**, because the Python you installed is yours rather than part of the operating
> system. If it does happen, use a virtual environment:
>
> ```powershell
> cd $HOME\Ansible_EDA_Test
> python -m venv .venv
> .\.venv\Scripts\python -m pip install pyyaml
> ```
>
> and then run later commands with `.\.venv\Scripts\python` in place of `python`.

</details>

<details>
<summary><strong>Linux</strong> — not yet run end to end; please correct anything wrong</summary>

### 2.1 Open a terminal

How you open one depends on your desktop. Look for an application called **Terminal**, **Console**
or **Konsole**. On many systems **Ctrl + Alt + T** opens one.

### 2.2 Install Git, Python and PyYAML

Use the package manager for your distribution. Run the block that matches it.

**Debian, Ubuntu, Linux Mint and similar:**

```bash
sudo apt update
sudo apt install -y git python3 python3-yaml
```

**Fedora, RHEL, Rocky, AlmaLinux and similar:**

```bash
sudo dnf install -y git python3 python3-pyyaml
```

**openSUSE:**

```bash
sudo zypper install -y git python3 python3-PyYAML
```

**Arch and similar:**

```bash
sudo pacman -S --needed git python python-yaml
```

`sudo` runs a command as the administrator and will ask for your password. You will see nothing as
you type it; that is deliberate.

Check all three:

```bash
git --version
python3 --version
python3 -c "import yaml; print(yaml.__version__)"
```

Expected output: a line beginning `git version`, then `Python 3.9` or newer, then a version number
such as `6.0.3`.

> ℹ️ **Install PyYAML from your package manager, not with `pip`, where you have the choice.** Most
> current distributions refuse `pip install` into the system Python and print a message about an
> *externally managed environment*. The package names above avoid that. If your distribution does not
> package PyYAML, use a virtual environment:
>
> ```bash
> cd ~/Ansible_EDA_Test
> python3 -m venv .venv
> ./.venv/bin/python -m pip install pyyaml
> ```
>
> and run later commands with `./.venv/bin/python` in place of `python3`.

> ⚠️ **If `python3 --version` reports older than 3.9**, your distribution is older than these tools
> support. Install a newer Python alongside the system one — how to do that varies enough by
> distribution that it is out of scope here — or run the tools from a machine with a newer Python.

</details>

---

## 3. Get your own copy of the repository

The same on all three platforms, except that Windows users should type `python` wherever `python3`
appears later.

1. Choose where it should live and go there. Your home folder is fine:

   ```bash
   cd ~
   ```

   On Windows, use `cd $HOME` instead.

2. Clone the repository:

   ```bash
   git clone https://github.com/drumforgod82/Ansible_EDA_Test.git
   ```

   Expected output: several lines beginning `Cloning into 'Ansible_EDA_Test'...` and ending with a
   count of objects received.

3. Go into it:

   ```bash
   cd Ansible_EDA_Test
   ```

4. Confirm you are in the right place:

   ```bash
   ls
   ```

   Expected output: among other entries, you should see `docs`, `rulebooks`, `scripts` and
   `local-test`.

> ℹ️ **Every command in the rest of this page assumes you are inside that folder.** If a command
> fails saying it cannot find a file, check with `pwd`, which prints where you are.

---

## 4. Tell the tools how to reach AAP and ServiceNow

The tools read seven values from **environment variables** rather than taking them as arguments, so
no password is ever typed on a command line where it would be saved in your shell's history.

### 4.1 The values, and where each comes from

| Variable | What it is | Where to get it |
|---|---|---|
| `AAP_GATEWAY` | The web address of your AAP, with no path on the end | The URL you log in to AAP with. See [01 §3](01-provision-aap.md) |
| `SANDBOX_AAP_PAT_TOKEN` | An AAP **personal access token** — a long random string that acts in place of your password for scripts | Created in the AAP web interface, under your own user's **Tokens**. The exact menu wording varies by AAP version; look for Tokens on your user record. Note it is **destroyed by an AAP rebuild** and must be re-made ([09](09-reconnect-after-aap-rebuild.md)) |
| `SN_PDI_HOST` | The web address of your ServiceNow developer instance | The instance URL from [02 §1](02-provision-pdi.md), of the form `https://devNNNNNN.service-now.com` |
| `SN_PDI_USERNAME` | A ServiceNow account that can **read** the route table | You create it; see [04](04-servicenow-app.md) |
| `SN_PDI_PASSWORD` | That account's password | |
| `SN_PDI_PROVISION_USERNAME` | A ServiceNow account that can **write** to the route table and credential tables | You create it; see [04](04-servicenow-app.md) |
| `SN_PDI_PROVISION_PASSWORD` | That account's password | |

> ℹ️ **Why two ServiceNow accounts.** `verify_team.py` only reads, so it is given an account that can
> only read. `provision_team.py` has to create records, so it needs one that can write. Keeping them
> apart means a mistake while verifying cannot change anything.

> 🔴 **Never put these values in a file inside the repository.** `.gitignore` blocks the obvious
> filenames as a backstop, but the only reliable approach is to keep them out of the folder
> entirely.

### 4.2 Setting them

<details>
<summary><strong>macOS and Linux</strong></summary>

For a single terminal session, set them by typing:

```bash
export AAP_GATEWAY="https://<your-aap-host>"
export SN_PDI_HOST="https://devNNNNNN.service-now.com"
export SN_PDI_USERNAME="<your-read-account>"
```

Replace each `<...>` with your own value, keeping the quotes. These last only until you close the
window.

> 🔑 **Do not type passwords or tokens this way.** Anything typed on a command line is written to
> your shell history file. Read secrets from your system's password store instead. On macOS the
> Keychain can do this:
>
> ```bash
> security add-generic-password -a "$USER" -s my-aap-token -w -U
> ```
>
> Leave `-w` with no value after it: the command then prompts you twice and the secret never appears
> as an argument. Read it back into a variable with:
>
> ```bash
> export SANDBOX_AAP_PAT_TOKEN="$(security find-generic-password -a "$USER" -s my-aap-token -w)"
> ```
>
> On Linux, `secret-tool` from the `libsecret` package does the same job.

To set the non-secret values every time you open a terminal, add the `export` lines to the file your
shell reads at startup — `~/.zshrc` on macOS, `~/.bashrc` on most Linux systems. Then open a **new**
terminal.

> ⚠️ **That startup file is only read by interactive terminals.** A program launched from the Dock,
> a desktop shortcut, or a scheduled job gets none of it — and the resulting failure looks like a
> wrong password rather than a missing variable.

</details>

<details>
<summary><strong>Windows 11</strong></summary>

For a single terminal session:

```powershell
$env:AAP_GATEWAY = "https://<your-aap-host>"
$env:SN_PDI_HOST = "https://devNNNNNN.service-now.com"
$env:SN_PDI_USERNAME = "<your-read-account>"
```

Replace each `<...>` with your own value. These last only until you close the window.

To be prompted for a secret without it appearing in your history, use `Read-Host`:

```powershell
$env:SANDBOX_AAP_PAT_TOKEN = Read-Host -AsSecureString |
    ForEach-Object { [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($_)) }
```

The cursor waits with no prompt text; type or paste the token and press **Enter**. Nothing is
echoed.

To make the non-secret values permanent, use the Settings app: press the **Windows** key, search for
`environment variables`, and choose **Edit environment variables for your account**. Add each one
there, then **open a new terminal** so it is picked up.

> ⚠️ **Variables set in Settings are not visible to terminals that were already open.** Close and
> reopen, or the value will appear to be missing.

</details>

### 4.3 Check they are set

```bash
python3 -c "
import os
need = ['AAP_GATEWAY','SANDBOX_AAP_PAT_TOKEN','SN_PDI_HOST','SN_PDI_USERNAME','SN_PDI_PASSWORD']
for v in need:
    print(f'{v}: ' + ('set' if os.environ.get(v) else 'NOT SET'))
"
```

Expected output: one line per variable, each saying `set`. That list is what `verify_team.py` needs;
`provision_team.py` needs the two `PROVISION` variables as well.

> ℹ️ **This prints only whether each is set, never its value**, so it is safe to run with someone
> watching.

---

## 5. Check the whole setup at once

The best test is to run the read-only tool against a team that already exists. It proves your
Python, your PyYAML, your network access, your AAP token and your ServiceNow account all work —
before anything is asked to write.

```bash
cd ~/Ansible_EDA_Test
python3 scripts/verify_team.py --team team-a
```

Expected output: a long list of lines beginning `PASS`, then a summary of the form

```
Team A: incident + sctask + problem
46/46 checks passed.
```

The count differs per team, because it depends on how many record types that team handles. A record
type the team's rulebook does not mention reports `SKIP`, which is not a failure.

> ✅ **Verify:** every line says `PASS`, and the command's exit status is `0`. Check the status with
> `echo $?` immediately afterwards, or `echo $LASTEXITCODE` in PowerShell.

If you do not have a team called `team-a`, substitute any team that exists on your instance.

---

## 6. Running the two tools

The procedures themselves live elsewhere, so there is only one copy to keep correct:

| What you want to do | Where it is written |
|---|---|
| Understand what each tool is for and when to run it | [`scripts/README.md`](../scripts/README.md) |
| Add a team — by hand, or with the script | [08 §2](08-routine-ops.md) |
| Check a team's wiring | [08 §5](08-routine-ops.md) |

> 🔴 **Read the token-scheme warning at the top of [08 §2](08-routine-ops.md) before provisioning
> anything.** It explains a choice this instance has already made that the scripts do not know
> about.

> ℹ️ **`provision_team.py` writes nothing unless you pass `--apply`.** Run it without that flag
> first and read what it says it will do. `verify_team.py` never writes at all.

---

## 7. When something is wrong

| What you see | What it usually means |
|---|---|
| `command not found: python3` | Python is not installed, or you installed it in a terminal window that was already open. Close the window, open a new one, try again. On Windows the command is `python` |
| `ModuleNotFoundError: No module named 'yaml'` | PyYAML is missing — §2 for your platform. If you used a virtual environment, you are running the wrong Python: use `./.venv/bin/python` |
| A message about an *externally managed environment* | Expected, not a fault. Install PyYAML with your package manager, or use a virtual environment. See the note in your platform's §2 |
| The tool stops saying a variable is missing | That variable is not set **in this terminal**. Re-run the check in §4.3. If you set it in a startup file or in Settings, open a new terminal |
| A ServiceNow error that reads like a permissions problem | Check the variable first with §4.3. A missing password and a refused password look very similar from the outside |
| `401` or `403` from AAP | The token is wrong, expired, or was destroyed by an AAP rebuild. Make a new one and set it again ([09](09-reconnect-after-aap-rebuild.md)) |
| Everything worked yesterday and nothing works today | Both platforms idle or sleep when unused. Confirm AAP and your ServiceNow instance are awake before anything else ([09](09-reconnect-after-aap-rebuild.md)) |
| `could not resolve host` | A networking or VPN problem, not a problem with these tools. Try opening the same address in a browser |

Deeper problems, once the setup itself is sound, are in [10 — Troubleshooting](10-troubleshooting.md).

---

## Checkpoint — before you move on

- [ ] `git --version` prints a version.
- [ ] `python3 --version` prints 3.9 or newer (`python` on Windows).
- [ ] `python3 -c "import yaml; print(yaml.__version__)"` prints a version.
- [ ] You have your own clone, and `ls` inside it shows `docs`, `rulebooks` and `scripts`.
- [ ] §4.3 reports every variable as `set`.
- [ ] §5 ran against an existing team and every line said `PASS`.

With all six true, go to [01 — Provision AAP](01-provision-aap.md) if you are building from nothing,
or straight to [08 §2](08-routine-ops.md) if AAP and ServiceNow already exist and you are adding a
team.

---

## Self-check

**Did I skip any prerequisite steps?** No, with one deliberate exclusion stated where it arises:
installing a newer Python on an old Linux distribution is out of scope, and §2 says so rather than
leaving the reader stuck. Opening a terminal, installing a package manager, and the need to reopen
the terminal afterwards are all covered rather than assumed.

**Is every command copy-paste ready with context?** Yes. Each shows the directory it is run from
where that matters, and the expected output so success is distinguishable from failure. The macOS
commands were all executed; the Windows and Linux commands were not, which the status table at the
top states plainly.

**Would a complete novice understand every sentence?** The terminal, the shell, the prompt, a
package manager, an environment variable, a repository and cloning are all defined in §0 before
being used. `sudo`, `PATH` and virtual environments are explained where they first appear.
