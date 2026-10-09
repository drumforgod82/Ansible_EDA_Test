#!/usr/bin/env python3
"""Apply a rulebook change to a running activation over the API, instead of by hand in the UI.

Why this exists
---------------
After a rulebook is edited and pushed, AAP does **not** pick it up. A running activation keeps
using the rulebook revision it started with, and the activation's ``source_mappings`` pins a
``rulebook_hash`` that no longer matches the synced file. The documented fix is a six-step
sequence of clicks -- sync the project, deactivate, remove the event stream, re-add the event
stream, save, reactivate -- which 08-routine-ops.md describes and which has two problems:

1. It is manual, so it needs a person with platform admin rights for every rulebook change of
   every team, and it cannot be put in a pipeline or a catalog item's fulfilment script.
2. **Events that arrive while the activation is down are lost silently.** The event stream
   accepts them with ``HTTP 200`` and the sender is told it succeeded, because an event stream
   reaches an activation over a Postgres ``LISTEN``/``NOTIFY`` channel and a ``NOTIFY`` with no
   listener is discarded rather than queued. So the length of the window is the size of the
   data-loss hole, and clicking through six screens is a far bigger hole than one API call.

This script does the same six steps over the REST API. Measured on this lab: 38 seconds end to
end including a project sync (5s to reach ``stopped``, 25s to reach ``running``), against minutes
of clicking. It prints the window it actually took, so the number is never a guess.

What a real rulebook edit does -- measured 2026-10-09
-----------------------------------------------------
A comment-only change was pushed, synced and restarted end to end to establish this. The sources
block was untouched; see "What is not covered" below.

* **The sync rewrites the pinned hash itself.** The rulebook moved from one SHA to another and the
  activation's ``source_mappings`` showed the new one with no manual re-attach. An ordinary edit
  does not leave the mapping stale.
* **The sync updates the rulebook row in place** -- same ``rulebook_id``, one row per filename per
  project. The repointing logic below has therefore never been needed in practice; it is kept
  because a version that behaves differently would otherwise fail silently. ``modified_at`` on the
  rulebook does *not* change on an edit, so it cannot be used to detect one.
* **A plain stop/start is what makes the edit live.** The restarted instance reported the new Git
  revision. Re-attaching the event stream is *not* required for the rulebook to take effect.
* **The flag survives a plain restart.** Rewriting ``source_mappings`` is what clears it, which is
  the only thing the PATCH below actually achieves.
* **Events route correctly throughout** -- with the flag set, and before the restart on the old
  rulebook. So "Rulebook content has changed since event stream sources were mapped" is a sticky
  flag, not a live comparison, and not proof that anything is broken. It asks you to update a
  mapping AAP has already updated.
* **A genuinely wrong hash fails closed.** Writing a bogus hash is accepted with ``HTTP 200``, and
  the activation then refuses to start: ``enable`` returns ``HTTP 400`` and it goes to ``error``.
  Loud, not silent -- and this script rolls the mapping back if it happens.

What is not covered
-------------------
A rulebook edit that **adds, removes or renames a source** was not measured. There the
source-to-stream binding itself, not just the hash, may need rebuilding, and the manual re-attach
may be genuinely required. Treat a change to a ``sources:`` block as needing the UI until somebody
measures it.

What it does NOT fix
--------------------
It shrinks the window; it does not remove it. The activation still stops and starts, and events
arriving in between are still lost. Pause the sender, or accept the loss, or reconcile
afterwards -- that decision is yours and this script cannot make it for you. ``enable_persistence``
on the activation does **not** help: it backs the *rule engine's* state with Postgres (see the
``Event-Driven Ansible Rule Engine`` credential type) and the loss happens upstream of the rule
engine, where nothing is listening at all.

Choosing an activation
----------------------
Three ways in, in the order you will want them:

1. ``--list`` prints every activation with its id, organization, status and whether it carries
   the stale-mapping flag. Read-only. This is how you find an id without guessing.
2. ``--activation NAME`` (optionally with ``--organization NAME``), or ``--activation-id N``.
   This is the form to use from a pipeline or a catalog item's fulfilment script.
3. Run it with no target **at a terminal** and it prints the table and asks which id to use.

That third path is deliberately gated on stdin being a terminal. Run it with no target from a
pipeline and it prints the table to stderr and exits non-zero instead of prompting, because a
fulfilment script blocking on ``input()`` is an invisible hang rather than a failure anyone sees.

Usage
-----
    # what is out there, and what is flagged (read-only)
    python3 scripts/eda_apply_rulebook_change.py --list

    # show what would change, touch nothing (default)
    python3 scripts/eda_apply_rulebook_change.py --activation team-c-incidents

    # sync the project first, then apply
    python3 scripts/eda_apply_rulebook_change.py --activation team-c-incidents --sync --apply

    # apply, then prove an event still routes afterwards
    EDA_STREAM_TOKEN="$(security find-generic-password -a "$USER" -s sandbox-eda-team-a -w)" \
      python3 scripts/eda_apply_rulebook_change.py --activation team-c-incidents --apply --probe

    # self-signed lab certificate, and a name used in more than one organization
    python3 scripts/eda_apply_rulebook_change.py --activation-id 5 --insecure --apply

Environment
-----------
    AAP_TOKEN               AAP personal access token            (required)
    AAP_GATEWAY             AAP gateway base URL                 (required, or pass --gateway)
    EDA_STREAM_TOKEN        event-stream token, only for --probe (optional)

``SANDBOX_AAP_PAT_TOKEN`` is also accepted, for this lab's existing setup.

Exit status is 0 only when the activation ends up running with no warnings.

Portability
-----------
Nothing here is specific to one company or one instance: the API paths, the ``rulebook_hash``
rule and the mapping format are product behaviour, and the script takes every identifier as an
argument. Four things are still worth knowing before running it somewhere that matters.

* **TLS verification is on by default.** ``--insecure`` exists for self-signed lab certificates
  and should never be used against a real deployment.
* **Version scope.** Developed and measured against AAP with controller 4.8.9. The EDA paths
  under ``/api/eda/v1/`` and the gateway-mounted event-stream POST path are version-dependent;
  on another release, confirm them before trusting a run. Everything else is plain REST.
* **Two API filter traps, both measured.** ``name=`` on the activations endpoint is a *substring*
  match, so ``--activation team-a`` could match ``team-a-incidents`` and ``team-a-problems``;
  this script matches names exactly and refuses when more than one activation matches, rather
  than acting on an arbitrary one. And ``organization_id`` is **silently ignored** on that
  endpoint -- asking for one organization's activations returns another organization's rows --
  so organization is filtered on the response, never in the query. Any other tool written
  against this API should assume unsupported filters are dropped rather than rejected.
* **It is not transactional.** Two people running it against one activation at the same time
  will interleave a stop and a start. Serialise it -- a pipeline or a fulfilment script, not a
  shared console.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

import yaml

HTTP_TIMEOUT_SECONDS = 30
STOP_TIMEOUT_SECONDS = 120
START_TIMEOUT_SECONDS = 300
POLL_SECONDS = 5


class ApiError(RuntimeError):
    """An AAP API call returned a status this script cannot continue from."""


def ssl_context(verify: bool) -> ssl.SSLContext:
    """Build the TLS context. Verification is ON unless explicitly disabled.

    A lab with a self-signed certificate needs ``--insecure``; anything else must not use it.
    This defaults to verifying precisely because the opposite default is the kind of thing that
    gets copied out of a sandbox script and into a real one without anyone noticing.
    """
    ctx = ssl.create_default_context()
    if not verify:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


class Aap:
    """Minimal AAP client over the EDA and gateway REST APIs."""

    def __init__(self, gateway: str, token: str, verify: bool = True) -> None:
        self.gateway = gateway.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        self.ctx = ssl_context(verify)

    def call(self, path: str, method: str = "GET", body: dict | None = None) -> tuple[int, Any]:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            self.gateway + path, data=data, headers=self.headers, method=method
        )
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS, context=self.ctx) as r:
                raw = r.read()
                status = r.status
        except urllib.error.HTTPError as exc:
            raw, status = exc.read(), exc.code
        try:
            return status, json.loads(raw) if raw else None
        except json.JSONDecodeError:
            return status, raw.decode(errors="replace")

    def get(self, path: str) -> Any:
        status, payload = self.call(path)
        if status != 200:
            raise ApiError(f"GET {path} -> HTTP {status}: {str(payload)[:300]}")
        return payload

    def first(self, path: str) -> dict[str, Any] | None:
        results = self.get(path).get("results") or []
        return results[0] if results else None

    def paged(self, path: str) -> list[dict[str, Any]]:
        """Collect every page, so a site with more activations than one page still works."""
        joiner = "&" if "?" in path else "?"
        payload = self.get(f"{path}{joiner}page_size=200")
        rows = list(payload.get("results") or [])
        while payload.get("next"):
            nxt = str(payload["next"])
            # ``next`` may be absolute; keep only the part after the host.
            if nxt.startswith("http"):
                nxt = urllib.parse.urlsplit(nxt)._replace(scheme="", netloc="").geturl()
            payload = self.get(nxt)
            rows.extend(payload.get("results") or [])
        return rows


def rulebook_hash(aap: Aap, rulebook_id: int) -> str:
    """SHA-256 of the rulebook's content, which is exactly what ``source_mappings`` pins.

    Taken from the API's ``rulesets`` field rather than from ``git show``, so it reflects what
    AAP actually holds. A local clone can be on a different branch, or missing the synced
    revision entirely, and would then produce a hash that looks like drift but is not.
    """
    rulesets = aap.get(f"/api/eda/v1/rulebooks/{rulebook_id}/")["rulesets"]
    return hashlib.sha256(rulesets.encode()).hexdigest()


def resolve_rulebook(aap: Aap, project_id: int, name: str) -> int:
    """Find the rulebook row for ``name`` in ``project_id``, preferring the newest.

    A project sync can add rulebook rows. If a sync ever replaces a changed file with a new row
    rather than updating the existing one, the activation's ``rulebook_id`` has to move too --
    so this resolves by name and reports when the id differs from the one the activation holds.

    Filtered server-side by ``project_id``, which was verified to be honoured (a nonexistent
    project returns zero rows rather than everything). ``name`` is matched exactly here rather
    than trusted to the query, because the API's ``name`` filter is a *substring* match.
    """
    query = urllib.parse.urlencode({"name": name, "project_id": project_id})
    page = aap.get(f"/api/eda/v1/rulebooks/?{query}&page_size=200")
    matches = [
        rb for rb in page.get("results", [])
        if rb.get("project_id") == project_id and rb.get("name") == name
    ]
    if not matches:
        raise ApiError(f"no rulebook named {name!r} in project {project_id}")
    return max(rb["id"] for rb in matches)


def resolve_activation(aap: Aap, name: str, organization: str | None) -> dict[str, Any]:
    """Resolve an activation by exact name, refusing to guess when the name is ambiguous.

    The API's ``name`` filter is a substring match -- ``name=team`` returns every activation with
    "team" anywhere in its name -- so taking the first result would quietly act on the wrong
    activation. At thirty teams that is a real possibility, and the failure would be invisible.

    ``organization_id`` cannot be used to disambiguate: it is **silently ignored** on this
    endpoint (asking for one organization's activations returns another organization's rows), so
    an unsupported filter looks like a successful narrow. Organization is therefore matched here,
    on the returned rows, never pushed into the query -- and matched on ``organization_id``,
    because activation rows carry no ``organization_name`` and comparing to one would match
    nothing while looking like a clean "not found".
    """
    query = urllib.parse.urlencode({"name": name})
    rows = aap.get(f"/api/eda/v1/activations/?{query}&page_size=200").get("results", [])
    exact = [r for r in rows if r.get("name") == name]
    if organization:
        org_rows = aap.get(
            "/api/eda/v1/organizations/?" + urllib.parse.urlencode({"name": organization})
        ).get("results", [])
        org_ids = {o["id"] for o in org_rows if o.get("name") == organization}
        if not org_ids:
            raise ApiError(f"no organization named exactly {organization!r}")
        exact = [r for r in exact if r.get("organization_id") in org_ids]
    if not exact:
        raise ApiError(
            f"no activation named exactly {name!r}"
            + (f" in organization {organization!r}" if organization else "")
        )
    if len(exact) > 1:
        detail = ", ".join(f"id={r['id']} org_id={r.get('organization_id')}" for r in exact)
        raise ApiError(
            f"{len(exact)} activations are named {name!r} ({detail}). "
            "Pass --activation-id to say which one."
        )
    return exact[0]


def inventory(aap: Aap) -> list[dict[str, Any]]:
    """List every activation with the facts needed to choose one.

    ``warnings`` is read from each activation's **detail** endpoint, not the list: the list
    endpoint returns ``warnings: null`` for every row and does not compute them, so a bulk check
    built on the list would report a clean estate however stale it actually was.
    """
    orgs = {o["id"]: o["name"] for o in aap.paged("/api/eda/v1/organizations/")}
    rows = []
    for row in aap.paged("/api/eda/v1/activations/"):
        detail = aap.get(f"/api/eda/v1/activations/{row['id']}/")
        rows.append(
            {
                "id": row["id"],
                "name": row["name"],
                "organization": orgs.get(row.get("organization_id"), "?"),
                "organization_id": row.get("organization_id"),
                "status": detail.get("status"),
                "enabled": detail.get("is_enabled"),
                "rulebook": detail.get("rulebook_name"),
                "flagged": bool(detail.get("warnings")),
                "streams": [s.get("name") for s in (detail.get("event_streams") or [])],
            }
        )
    return sorted(rows, key=lambda r: (str(r["organization"]), r["name"]))


def print_inventory(rows: list[dict[str, Any]], stream: Any = sys.stdout) -> None:
    """Print the activation inventory as a table, widest-field aware."""
    if not rows:
        print("no activations found", file=stream)
        return
    width_name = max(len("ACTIVATION"), *(len(r["name"]) for r in rows))
    width_org = max(len("ORGANIZATION"), *(len(str(r["organization"])) for r in rows))
    header = (
        f"{'ID':>4}  {'ACTIVATION':<{width_name}}  {'ORGANIZATION':<{width_org}}  "
        f"{'STATUS':<9}  {'FLAGGED':<7}  STREAMS"
    )
    print(header, file=stream)
    print("-" * len(header), file=stream)
    for r in rows:
        print(
            f"{r['id']:>4}  {r['name']:<{width_name}}  {str(r['organization']):<{width_org}}  "
            f"{str(r['status']):<9}  {'yes' if r['flagged'] else 'no':<7}  "
            f"{','.join(r['streams']) or '-'}",
            file=stream,
        )
    flagged = [r for r in rows if r["flagged"]]
    print(
        f"\n{len(rows)} activation(s), {len(flagged)} flagged "
        '("rulebook content has changed since event stream sources were mapped").',
        file=stream,
    )
    print(
        "A flag is not proof of breakage -- measured: events still route while it is set.",
        file=stream,
    )


def choose_interactively(rows: list[dict[str, Any]]) -> int:
    """Let a human at a terminal pick an activation by id.

    Only ever called when stdin is a TTY. A pipeline that reaches this point gets the table and
    a non-zero exit instead, because blocking on input in a fulfilment script is an invisible
    hang rather than an error anyone sees.
    """
    print_inventory(rows)
    valid = {r["id"] for r in rows}
    while True:
        try:
            raw = input("\nActivation ID to apply to (or Enter to cancel): ").strip()
        except EOFError:
            raise ApiError("no selection made") from None
        if not raw:
            raise ApiError("cancelled")
        if raw.isdigit() and int(raw) in valid:
            return int(raw)
        print(f"  not one of the listed ids: {sorted(valid)}")


def build_mappings(existing: str, streams: list[dict], target_hash: str) -> str:
    """Rewrite the mapping with a fresh ``rulebook_hash``, preserving every other field.

    The source-to-stream binding is the part a human would recreate by removing and re-adding the
    event stream, and it is the part that must survive untouched -- only the hash is stale.
    """
    parsed = yaml.safe_load(existing) if (existing or "").strip() else None
    if parsed:
        rows = [
            {
                "event_stream_id": row["event_stream_id"],
                "event_stream_name": row["event_stream_name"],
                "rulebook_hash": target_hash,
                "source_name": row["source_name"],
            }
            for row in parsed
        ]
    elif len(streams) == 1:
        # No mapping yet: a single stream binds unambiguously to a single unnamed source.
        rows = [
            {
                "event_stream_id": streams[0]["id"],
                "event_stream_name": streams[0]["name"],
                "rulebook_hash": target_hash,
                "source_name": "__SOURCE_1",
            }
        ]
    else:
        raise ApiError(
            f"no existing source_mappings and {len(streams)} event streams attached -- "
            "cannot infer which source each stream belongs to; map it once in the UI first"
        )
    # AAP's own field order and block style, and -- measured -- with no trailing newline, so
    # re-applying an unchanged mapping writes a byte-identical value rather than a pointless diff.
    return "\n".join(
        f"- event_stream_id: {r['event_stream_id']}\n"
        f"  event_stream_name: {r['event_stream_name']}\n"
        f"  rulebook_hash: {r['rulebook_hash']}\n"
        f"  source_name: {r['source_name']}"
        for r in rows
    )


def same_mapping(left: str, right: str) -> bool:
    """Compare mappings by meaning, not by text.

    AAP stores the mapping with no trailing newline and may reformat it. Comparing the raw
    strings reports drift that is only whitespace, which would make every run look like it has
    work to do and defeat the point of the idempotency check.
    """
    try:
        return yaml.safe_load(left or "") == yaml.safe_load(right or "")
    except yaml.YAMLError:
        return False


def wait_for_status(aap: Aap, act_id: int, target: str, timeout: int) -> tuple[bool, str, int]:
    """Poll until the activation reaches ``target``. Returns (reached, last_status, seconds)."""
    waited = 0
    status = "unknown"
    while waited < timeout:
        status = aap.get(f"/api/eda/v1/activations/{act_id}/")["status"]
        if status == target:
            return True, status, waited
        if status == "error":
            return False, status, waited
        time.sleep(POLL_SECONDS)
        waited += POLL_SECONDS
    return False, status, waited


def sync_project(aap: Aap, project_id: int) -> None:
    """Sync the EDA project and wait for the import to finish."""
    status, payload = aap.call(f"/api/eda/v1/projects/{project_id}/sync/", method="POST")
    if status not in (200, 202, 204):
        raise ApiError(f"project sync -> HTTP {status}: {str(payload)[:300]}")
    print(f"  project {project_id} sync requested (HTTP {status})")
    waited = 0
    while waited < START_TIMEOUT_SECONDS:
        project = aap.get(f"/api/eda/v1/projects/{project_id}/")
        state = project.get("import_state")
        if state == "completed":
            print(f"  sync completed after {waited}s at {str(project.get('git_hash'))[:12]}")
            return
        if state == "failed":
            raise ApiError(f"project sync failed: {project.get('import_error')}")
        time.sleep(POLL_SECONDS)
        waited += POLL_SECONDS
    raise ApiError(
        f"project sync still {state!r} after {waited}s. A sync stuck in pending is usually the "
        "default worker being OOM-killed mid-clone -- raise its memory limit and retry"
    )


def probe(gateway: str, uuid: str, token: str, label: str, verify: bool = True) -> int:
    """POST a deliberately non-matching event, so it proves routing without launching a job.

    The event-stream POST path is gateway-mounted and was measured on this platform version; if
    a different version mounts it elsewhere this is the one call that needs adjusting.
    """
    ctx = ssl_context(verify)
    url = f"{gateway}/eda-event-streams/api/eda/v1/external_event_stream/{uuid}/post/"
    body = json.dumps({"event_type": "apply_probe_nonmatching", "probe": label}).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "Authorization": token},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS, context=ctx) as r:
            return r.status
    except urllib.error.HTTPError as exc:
        return exc.code


def probe_arrived(aap: Aap, act_id: int, label: str) -> bool:
    """True if ``label`` appears in any recent instance log for this activation.

    An ``HTTP 200`` from the event stream is not evidence of delivery -- the stream's counter
    rises even for a rejected token, and even when no activation is listening at all. The
    activation's own log is the only place delivery can be confirmed.
    """
    instances = aap.get(f"/api/eda/v1/activations/{act_id}/instances/").get("results", [])
    for inst in instances[:3]:
        logs = aap.get(f"/api/eda/v1/activation-instances/{inst['id']}/logs/?page_size=500")
        if any(label in str(row.get("log")) for row in logs.get("results", [])):
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Apply a rulebook change to an activation over the API."
    )
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--activation", help="exact activation name, e.g. team-c-incidents")
    target.add_argument("--activation-id", type=int, help="activation id, for an ambiguous name")
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_only",
        help="list activations with their ids, organizations and flag state, then exit",
    )
    parser.add_argument("--organization", help="organization name, to disambiguate a shared name")
    parser.add_argument("--gateway", default=os.environ.get("AAP_GATEWAY", ""))
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="skip TLS certificate verification (self-signed lab certificates only)",
    )
    parser.add_argument("--sync", action="store_true", help="sync the EDA project first")
    parser.add_argument("--apply", action="store_true", help="make changes; omit for a dry run")
    parser.add_argument("--probe", action="store_true", help="post a non-matching test event after")
    parser.add_argument(
        "--force",
        action="store_true",
        help="run the stop/patch/start cycle even when the mapping is already current",
    )
    args = parser.parse_args()

    # AAP_TOKEN is the portable name; SANDBOX_AAP_PAT_TOKEN is kept for this lab's existing setup.
    token = os.environ.get("AAP_TOKEN") or os.environ.get("SANDBOX_AAP_PAT_TOKEN", "")
    if not args.gateway or not token:
        print(
            "set AAP_GATEWAY (or --gateway) and AAP_TOKEN (or SANDBOX_AAP_PAT_TOKEN)",
            file=sys.stderr,
        )
        return 2

    aap = Aap(args.gateway, token, verify=not args.insecure)

    if args.list_only:
        print_inventory(inventory(aap))
        return 0

    try:
        if args.activation_id:
            act_ref_id = args.activation_id
        elif args.activation:
            act_ref_id = resolve_activation(aap, args.activation, args.organization)["id"]
        elif sys.stdin.isatty():
            act_ref_id = choose_interactively(inventory(aap))
        else:
            # Non-interactive and nothing named: fail loudly with the table, never block on input.
            print(
                "no activation given. Pass --activation or --activation-id "
                "(stdin is not a terminal, so there is nothing to prompt). Choices:\n",
                file=sys.stderr,
            )
            print_inventory(inventory(aap), stream=sys.stderr)
            return 2
    except ApiError as exc:
        print(exc, file=sys.stderr)
        return 2

    act = aap.get(f"/api/eda/v1/activations/{act_ref_id}/")
    act_id = act["id"]
    project_id = (act.get("project") or {}).get("id")
    held_rulebook_id = (act.get("rulebook") or {}).get("id")
    original_mappings = act.get("source_mappings") or ""

    print(f"activation {act_id} {act['name']!r}")
    print(f"  status={act['status']} enabled={act['is_enabled']}")
    print(f"  rulebook={act.get('rulebook_name')} (id {held_rulebook_id}) project={project_id}")
    print(f"  warnings={json.dumps(act.get('warnings'))}")

    if args.sync:
        if not args.apply:
            print("  [dry run] would sync the project")
        else:
            sync_project(aap, project_id)

    rulebook_id = resolve_rulebook(aap, project_id, act["rulebook_name"])
    if rulebook_id != held_rulebook_id:
        print(f"  NOTE rulebook row changed: {held_rulebook_id} -> {rulebook_id}; will repoint")
    target = rulebook_hash(aap, rulebook_id)
    desired = build_mappings(original_mappings, act.get("event_streams") or [], target)

    mapping_current = same_mapping(desired, original_mappings)
    clean = mapping_current and rulebook_id == held_rulebook_id and not act.get("warnings")
    print(f"  target rulebook_hash={target}")
    print(f"  mapping already correct: {mapping_current}")

    if clean and act["status"] == "running" and not args.force:
        print("Nothing to do: mapping is current, no warnings, activation running.")
        print("Pass --force to run the cycle anyway.")
        return 0
    if not mapping_current:
        print("  mapping to be written:")
        print("".join(f"    {line}\n" for line in desired.splitlines()))

    if not args.apply:
        print("[dry run] re-run with --apply to disable, PATCH the mapping, and re-enable.")
        print("[dry run] events arriving during that window are lost silently -- see module docstring.")
        return 0

    print("APPLYING. Events arriving from now until 'running' below are lost silently.")
    window_start = time.time()

    status, payload = aap.call(f"/api/eda/v1/activations/{act_id}/disable/", method="POST")
    print(f"  disable -> HTTP {status}")
    reached, last, waited = wait_for_status(aap, act_id, "stopped", STOP_TIMEOUT_SECONDS)
    print(f"  status={last} after {waited}s")
    if not reached:
        print("  did not reach 'stopped'; nothing was changed", file=sys.stderr)
        return 1

    patch: dict[str, Any] = {"source_mappings": desired}
    if rulebook_id != held_rulebook_id:
        patch["rulebook_id"] = rulebook_id
    status, payload = aap.call(f"/api/eda/v1/activations/{act_id}/", method="PATCH", body=patch)
    print(f"  PATCH -> HTTP {status}")
    if status != 200:
        print(f"  PATCH refused: {str(payload)[:400]}", file=sys.stderr)
        aap.call(f"/api/eda/v1/activations/{act_id}/enable/", method="POST")
        return 1

    status, payload = aap.call(f"/api/eda/v1/activations/{act_id}/enable/", method="POST")
    print(f"  enable -> HTTP {status}")
    if status not in (200, 202, 204):
        # A mapping AAP will not start on leaves the activation in 'error', not merely stopped.
        # Measured: a wrong rulebook_hash is refused here rather than silently misrouting.
        print(f"  enable refused: {str(payload)[:300]}", file=sys.stderr)
        print("  rolling the mapping back", file=sys.stderr)
        aap.call(f"/api/eda/v1/activations/{act_id}/disable/", method="POST")
        wait_for_status(aap, act_id, "stopped", STOP_TIMEOUT_SECONDS)
        aap.call(
            f"/api/eda/v1/activations/{act_id}/",
            method="PATCH",
            body={"source_mappings": original_mappings},
        )
        aap.call(f"/api/eda/v1/activations/{act_id}/enable/", method="POST")
        wait_for_status(aap, act_id, "running", START_TIMEOUT_SECONDS)
        return 1

    reached, last, waited = wait_for_status(aap, act_id, "running", START_TIMEOUT_SECONDS)
    window = time.time() - window_start
    print(f"  status={last} after {waited}s")
    print(f"  data-loss window: {window:.0f}s")

    after = aap.get(f"/api/eda/v1/activations/{act_id}/")
    warnings = after.get("warnings") or []
    print(f"  warnings={json.dumps(warnings)}")
    ok = reached and not warnings

    if args.probe:
        stream_token = os.environ.get("EDA_STREAM_TOKEN", "")
        streams = after.get("event_streams") or []
        if not stream_token or not streams:
            print("  probe skipped (EDA_STREAM_TOKEN unset or no stream attached)")
        else:
            uuid = aap.get(f"/api/eda/v1/event-streams/{streams[0]['id']}/")["uuid"]
            label = f"apply-{int(time.time())}"
            code = probe(args.gateway, uuid, stream_token, label, verify=not args.insecure)
            print(f"  probe POST -> HTTP {code}")
            time.sleep(15)
            arrived = probe_arrived(aap, act_id, label)
            print(f"  probe routed to the activation: {arrived}")
            ok = ok and arrived

    print("OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
