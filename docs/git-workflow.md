# Git workflow for this repo

This repo has a branch setup that **generates merge conflicts on every pull request** unless one
habit is kept. It is not obvious, a tree comparison does not predict it, and the usual fix is blocked
by the repository's own rules. Read this before your second PR.

---

## The rules in force

| Rule | What it means |
|---|---|
| **`main` is protected** | No direct push. `git push origin main` is rejected with `GH006: Protected branch update failed … Changes must be made through a pull request`, **even when the local merge succeeded**. Everything goes through a PR |
| **`dev` has a ruleset forbidding force-push** | `GH013: Repository rule violations found … Cannot force-push to this branch`. So `reset --hard` + `push --force-with-lease` is **not available**. Do not reach for it |
| **PRs are squash-merged** | The tip commit on `main` reads `Dev (#18)` with a single parent. A real merge commit would read `Merge pull request #18 from …` |
| **`main` required linear history** (until 2026-10-05) | This is the rule that **forced** squash-merging, and the one that made the trap unavoidable. It forbids a merge commit from landing on `main`, so of the three merge methods only squash and rebase were ever legal — and rebase cannot work here (see below). **Turned off 2026-10-05**, which is what finally made the real fix available |
| **AAP projects track `main`** | With `scm_update_on_launch = false`. So pushing to `dev` changes nothing that runs; only a merge to `main` **plus a manual project sync** does |

> ⚠️ **The three settings interact, and GitHub reports the conflict misleadingly.** With linear
> history required and only *Allow merge commits* enabled, merging is blocked with **"Merge is not an
> allowed merge method in this repository / This branch must not contain merge commits."** With only
> *Allow rebase merging* enabled, the PR shows a red **"Merge conflicts"** badge and
> `This branch cannot be rebased due to conflicts` — even though the API reports
> `mergeable_state: clean`. In both cases **there is no merge conflict**; the selected *strategy* is
> impossible. Check `rebaseable` separately from `mergeable` before believing the badge:
>
> ```bash
> curl -s https://api.github.com/repos/<owner>/<repo>/pulls/<n> \
>   | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['mergeable'], d['mergeable_state'], d['rebaseable'])"
> ```
>
> `True clean False` means: merge or squash will work, rebase will not.

---

## The trap

Squash-merging rewrites `dev`'s commits into **one new commit** on `main`. Git can no longer tell the
two branches share that work — both branches now contain the same *content* by way of unrelated
commits.

The next PR is therefore a three-way merge from an **old** base, where both sides changed the same
regions. It conflicts on every file both branches touched, including `CONFLICT (add/add)` on files
each branch appears to have created independently.

> 🔴 **A tree comparison does not predict this.** `git diff origin/main origin/dev` came back
> **identical** and the merge still conflicted on three files. Tree equality says nothing about a
> three-way merge from the merge base. The only reliable predictor is to try it:
>
> ```bash
> git worktree add -q --detach /tmp/mergetest origin/main
> cd /tmp/mergetest && git merge --no-commit --no-ff origin/dev
> git diff --name-only --diff-filter=U        # the files that would conflict
> git merge --abort; cd -; git worktree remove --force /tmp/mergetest
> ```

### How to tell you are in it

```bash
git fetch origin
git rev-list --left-right --count origin/main...origin/dev
git merge-base --is-ancestor origin/dev origin/main && echo CLEAN || echo DIVERGED
```

`DIVERGED` means the trap is live and your next PR will conflict.

> ⚠️ **Check that `dev` is an ancestor of `main`, not the reverse.** Earlier revisions of this page
> had the arguments the other way round, which **false-alarms after every merge-commit PR**. With
> merge commits, GitHub creates the merge commit *on `main`*, and `dev` still points at its own tip —
> which is that commit's second parent. So `main ahead 1, dev ahead 0` is the **normal, healthy**
> steady state, not divergence. What matters is that every commit on `dev` has landed on `main`,
> which is `dev` being an ancestor of `main`.
>
> Confirmed 2026-10-05 after PR #19: `main ahead 1, dev ahead 0`, `dev` an ancestor of `main`, and a
> trial `dev` → `main` merge reporting **`Already up to date.`** — i.e. nothing to conflict over.
>
> The genuinely bad state is the squash one: **both** counters non-zero, or `dev` *not* an ancestor
> of `main` while `git diff origin/main origin/dev` is empty. That combination — identical content
> reached by unrelated commits — is the trap.

---

## The habit that prevents it

> ℹ️ **Only needed while PRs are squash-merged.** Since the switch to merge commits on 2026-10-05
> (Option 1 below), `main` stays an ancestor of `dev` on its own and this is no longer part of the
> routine. Keep it for two reasons: it is what clears the divergence left behind by the squash era,
> and it is the fix if anyone re-enables squash merging.

**Run this immediately after every squash-merge to `main`:**

```bash
git fetch origin
git checkout dev
git merge --no-edit origin/main
git push origin dev
```

It is a **content no-op** — clean, zero conflicts, tree unchanged — but it makes `main` an ancestor
of `dev` again, so the next PR is a clean fast-forward. It works inside both rulesets; no force
needed. `--no-edit` keeps it from opening an editor for a merge message you do not care about.

### Verify

```bash
git merge-base --is-ancestor origin/main origin/dev && echo "OK: main is an ancestor again"
git diff --quiet origin/main origin/dev && echo "OK: content identical"
git rev-list --left-right --count origin/main...origin/dev
```

You want **`main ahead by 0`**. The `dev ahead by N` figure grows by a few each cycle — that is
**healthy, not drift**. Those extra commits carry zero file changes, which is exactly what the
`git diff --quiet` line proves. Do not try to flatten them; that needs the force-push the ruleset
blocks.

---

## Getting out of the trap permanently

The cause is **not** squash-merging. It is squash-merging combined with a **long-lived `dev`**.
Squash is designed for *disposable* branches; `dev` never goes away, so it diverges every time.
Three real exits:

| Option | What to do | Trade-off |
|---|---|---|
| **1. Merge commits instead of squash** — keeps `dev` | **Two steps, and the order matters — see the warning below.** ① Settings → Rules → Rulesets (or Settings → Branches for classic protection): untick **Require linear history** on `main`. ② Settings → General → Pull Requests: tick *Allow merge commits*, untick *Allow squash merging* **and** *Allow rebase merging* | Every merge gives `main` a commit whose parent is `dev`'s tip, so `main` is permanently an ancestor. **No divergence, no habit, nothing to remember.** Cost: `main`'s history shows every `dev` commit — for a single-developer repo that is arguably better, since you keep the real history instead of flattening it |
| **2. Make `dev` disposable** — keeps squash | Branch per change off `main`, PR it, squash, delete the branch | Nothing long-lived exists to diverge. This is the pattern squash is built for. Cost: you lose the integration-branch concept — though with one developer there is nothing to integrate |
| **3. Automate the back-merge** | A GitHub Action on push to `main` that merges `main` into `dev` | Works inside both rulesets (a real merge, no force). Cost: a workflow to maintain, and it manages the symptom rather than removing it |

**Option 1 is the recommendation**, and it was taken on 2026-10-05. It removes the cause and `dev`
stays.

> 🔴 **Step ① is not optional, and skipping it wastes a PR.** Learned the hard way on PRs #16–#18.
> *Require linear history* on `main` **forbids merge commits**, so ticking *Allow merge commits*
> while that rule is live leaves you with **no legal merge method at all** — squash and rebase are
> off by your own hand, and merge is off by the rule. The PR then reports
> **"Merging is blocked / Merge is not an allowed merge method in this repository."** Untick the rule
> **first**, then change the merge methods.

**Run the habit command once after switching**, to clear the divergence you already have. Switching
the merge method does not retroactively fix it: the last squash (`Dev (#18)`) already left
`main ahead 1, dev ahead 11` with identical content. The first merge-commit PR after that back-merge
is what makes `main` an ancestor for good.

### Verifying it actually took

After the next PR merges, the tip of `main` must have **two parents**:

```bash
git fetch origin
git log -1 --format='%s%nparents: %p' origin/main
```

`parents:` listing two hashes and a subject reading `Merge pull request #NN from …` means Option 1 is
in force. A single parent and a subject like `Dev (#18)` means it squashed again — the setting did
not take, and you are back in the trap.

**Verified in force on 2026-10-05 by PR #19:**

```
subject: Merge pull request #19 from drumforgod82/dev
parents: 7d70581 6663923        <- two parents; 6663923 is dev's tip
```

Expect `main ahead 1, dev ahead 0` from here on. That single commit is the merge commit itself,
which lives only on `main`. It is the steady state, not drift — see the warning under
*How to tell you are in it*. No habit run is needed.

---

## Resolving a conflicted `dev` → `main` merge

If you are already conflicted: when `main`'s copy of every file is byte-identical to `dev`'s
*pre-change* commit, **take `dev`'s side wholesale** — `dev` is then `main`'s content plus the
intended changes, and nothing is lost.

Verify that per file rather than assuming:

```bash
git show origin/main:<file> | shasum
git show <dev's last pre-change commit>:<file> | shasum
```

Then:

```bash
git checkout --theirs -- <each conflicted file>
git add <each conflicted file>
git diff --cached --stat origin/dev     # MUST print nothing before you commit
git commit
```

Because `main` is protected, that merge commit **cannot be pushed to `main`**. Move it onto `dev` and
PR from there — `dev` can fast-forward to it, because the merge commit has `dev`'s tip as a parent:

```bash
git checkout dev && git merge --ff-only main && git push origin dev
```

---

## What to sync after a merge, and what not to

| You changed | Sync | Re-attach stream mapping | Restart activation |
|---|---|---|---|
| A **playbook** (`servicenow_*_handler.yml`) | **controller** projects only | no | no |
| A **rulebook** (`rulebooks/team_*.yml`) | **EDA** projects | **yes — gear icon** | **yes** |
| Docs or scripts only | nothing | no | no |

Rulebook changes are the expensive ones: source mappings are pinned to a **SHA256 of the rulebook
file's raw bytes**, so *any* edit — including a whitespace-only one or an editor adding a trailing
newline — invalidates the mapping and costs the full cycle. **Batch rulebook edits** so you pay it
once.

The hash is computable offline, against the **synced revision** rather than your worktree:

```bash
git show <eda_project.git_hash>:rulebooks/team_x_rulebook.yml | shasum -a 256
```

Compare that to `rulebook_hash` inside the activation's `source_mappings`. Skipping the re-attach
fails with `Rulebook has changed since the sources were mapped`.

A playbook-only change is cheap, and you can **prove** you took the cheap path: the activations'
restart counts should not change.
