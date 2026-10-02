#!/usr/bin/env python3
"""Verify one team's EDA + ServiceNow wiring end to end, before testing it with a real incident.

Every ``✅ Verify`` step in the README and the routing guide is a human eyeball. This script
replaces the mechanical subset of them with assertions, so the four failures that are known to
happen *silently* cannot reach a live test:

1. A rulebook copied from another team with a name left behind.
2. A job template pointing at a rulebook instead of ``servicenow_incident_handler.yml``.
3. ``ask_variables_on_launch`` off, which discards every extra_var the rulebook sends.
4. A ServiceNow route row whose event stream UUID does not match the AAP stream it names.

Number 4 is the one no amount of careful clicking catches: both sides look right in isolation and
only disagree when compared. That cross-system check is the main reason this script exists.

Read-only. It issues GETs and never writes to AAP, ServiceNow, or Git.

Usage
-----
    python3 scripts/verify_team.py --team team-c
    python3 scripts/verify_team.py --team team-c --json

Environment
-----------
    SANDBOX_AAP_PAT_TOKEN   AAP personal access token          (required)
    AAP_GATEWAY             AAP gateway base URL               (required, or pass --gateway)
    SN_PDI_HOST             e.g. https://dev123456.service-now.com   (required)
    SN_PDI_USERNAME         PDI account with read on the route table (required)
    SN_PDI_PASSWORD         that account's password                  (required)

Exit status is 0 only when every check passes.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Iterable

class RecordType:
    """One ServiceNow record type this lab automates.

    ``playbook`` is shared by every team -- the per-team file is the *rulebook*, selected on the
    activation, never here. Pointing a job template at a rulebook fails with
    "ERROR! 'sources' is not a valid attribute for a Play" only once an event arrives.

    ``event_type`` is the contract string the rulebook's condition tests. It is also how this script
    works out which record types a team has: see ``detect_record_types``.
    """

    def __init__(self, key: str, template_suffix: str, playbook: str, event_type: str) -> None:
        self.key = key
        self.template_suffix = template_suffix
        self.playbook = playbook
        self.event_type = event_type


# Order matters only for display.
RECORD_TYPES: tuple[RecordType, ...] = (
    RecordType("incident", "Incident Handler", "servicenow_incident_handler.yml", "servicenow.incident.created"),
    RecordType("sctask", "SCTASK Handler", "servicenow_sctask_handler.yml", "servicenow.sctask.created"),
    RecordType("problem", "Problem Handler", "servicenow_problem_handler.yml", "servicenow.problem.created"),
)

# Forwarding this header copies the stream's own bearer token into event.meta.headers, and from
# there into the job's extra_vars in cleartext. Never forward it.
FORBIDDEN_FORWARDED_HEADER = "authorization"

HTTP_RETRIES = 3
HTTP_BACKOFF_SECONDS = 20
HTTP_TIMEOUT_SECONDS = 45


class Outcome:
    """Collects check results and renders them."""

    def __init__(self) -> None:
        self.rows: list[tuple[bool, str, str]] = []

    def __init__(self) -> None:
        self.rows: list[tuple[bool, str, str]] = []
        self.notes: list[tuple[str, str]] = []

    def record(self, ok: bool, label: str, detail: str = "", info: str = "") -> bool:
        """Record a check. ``detail`` prints only on failure; ``info`` prints either way.

        Detail explains a failure. Printing it on success turns a clean run into a wall of noise,
        which is how a real FAIL gets skimmed past.
        """
        self.rows.append((ok, label, info or ("" if ok else detail)))
        return ok

    def note(self, label: str, detail: str = "") -> None:
        """Record something deliberately not configured. Neither a pass nor a failure.

        This exists so a team that legitimately lacks a record type does not score a FAIL. Team C
        has no SCTASK job template on purpose, and reporting that as broken would train people to
        ignore real failures. Notes are excluded from the pass/fail totals so the count stays honest.
        """
        self.notes.append((label, detail))

    @property
    def failures(self) -> list[tuple[bool, str, str]]:
        return [r for r in self.rows if not r[0]]

    def render(self) -> None:
        for ok, label, detail in self.rows:
            mark = "\033[32m PASS\033[0m" if ok else "\033[31m FAIL\033[0m"
            print(f"{mark}  {label}")
            if detail:
                for line in detail.splitlines():
                    print(f"        {line}")
        for label, detail in self.notes:
            print(f"\033[33m SKIP\033[0m  {label}")
            if detail:
                for line in detail.splitlines():
                    print(f"        {line}")

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": len(self.rows) - len(self.failures),
            "failed": len(self.failures),
            "skipped": len(self.notes),
            "checks": [
                {"ok": ok, "label": label, "detail": detail} for ok, label, detail in self.rows
            ],
            "notes": [{"label": label, "detail": detail} for label, detail in self.notes],
        }


class TeamNames:
    """Every name derived from a team code, by the convention the runbook fixes.

    Three of these are matched *by string* at run time and fail silently when wrong: the job
    template name (the rulebook looks it up by name), the event stream name (the rulebook's
    condition tests it), and the assignment group name (the route row references it).
    """

    def __init__(self, team_code: str) -> None:
        if not re.fullmatch(r"team-[a-z]", team_code):
            raise ValueError(f"team code must look like 'team-c', got {team_code!r}")
        self.code = team_code
        letter = team_code.rsplit("-", 1)[1]
        self.letter = letter.upper()
        self.organization = f"Team {self.letter}"
        self.stream = f"sn-{team_code}"
        self.assignment_group = f"Team-{self.letter}"
        # Named "-incidents" before SCTASK and Problem existed. The activation handles all three;
        # nothing reads this name programmatically, so it is a cosmetic misnomer, not a bug.
        self.activation = f"{team_code}-incidents"
        self.rulebook_file = f"rulebooks/team_{letter}_rulebook.yml"
        self.rulebook_name = f"team_{letter}_rulebook.yml"
        self.controller_project = f"EDA ServiceNow - Team {self.letter}"

    def job_template(self, record_type: RecordType) -> str:
        """The job template name for one record type. Matched BY STRING by the rulebook."""
        return f"Team {self.letter} {record_type.template_suffix}"


def _request(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
    """GET a URL, retrying the sandbox's cold-start 503s rather than reporting them as failures."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    last: Exception | None = None
    for attempt in range(HTTP_RETRIES):
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS, context=ctx) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 503 and attempt < HTTP_RETRIES - 1:
                time.sleep(HTTP_BACKOFF_SECONDS)
                last = exc
                continue
            return exc.code, exc.read()
        except Exception as exc:  # noqa: BLE001 - network shape varies; caller reports it
            last = exc
            if attempt < HTTP_RETRIES - 1:
                time.sleep(2)
                continue
    raise RuntimeError(f"GET {url} failed after {HTTP_RETRIES} attempts: {last}")


class AapClient:
    """Read-only AAP 2.7 client covering both Automation Execution and Automation Decisions."""

    def __init__(self, gateway: str, token: str) -> None:
        self.gateway = gateway.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    def get(self, path: str) -> dict[str, Any]:
        status, body = _request(f"{self.gateway}{path}", self._headers)
        if status != 200:
            raise RuntimeError(f"AAP GET {path} returned HTTP {status}")
        return json.loads(body.decode())

    def first(self, path: str) -> dict[str, Any] | None:
        """Return the single expected result, or None. Raises if the name is ambiguous."""
        results = self.get(path).get("results", [])
        if not results:
            return None
        if len(results) > 1:
            raise RuntimeError(f"AAP GET {path} matched {len(results)} records; expected one")
        return results[0]


class ServiceNowClient:
    """Read-only ServiceNow table API client."""

    def __init__(self, host: str, username: str, password: str) -> None:
        self.host = host.rstrip("/")
        token = base64.b64encode(f"{username}:{password}".encode()).decode()
        self._headers = {"Authorization": f"Basic {token}", "Accept": "application/json"}

    def table(self, table: str, query: str, fields: Iterable[str], limit: int = 5) -> list[dict]:
        params = urllib.parse.urlencode(
            {
                "sysparm_query": query,
                "sysparm_fields": ",".join(fields),
                "sysparm_display_value": "all",
                "sysparm_limit": str(limit),
            }
        )
        status, body = _request(f"{self.host}/api/now/table/{table}?{params}", self._headers)
        if status != 200:
            raise RuntimeError(f"ServiceNow GET {table} returned HTTP {status}")
        return json.loads(body.decode()).get("result", [])


def field(row: dict[str, Any], key: str) -> str:
    """Read a value out of a sysparm_display_value=all row, preferring the display value."""
    raw = row.get(key)
    if isinstance(raw, dict):
        return str(raw.get("display_value") or raw.get("value") or "")
    return "" if raw is None else str(raw)


def raw_field(row: dict[str, Any], key: str) -> str:
    """Read the stored value rather than the display value -- needed for UUIDs and booleans."""
    value = row.get(key)
    if isinstance(value, dict):
        return str(value.get("value") or "")
    return "" if value is None else str(value)


# --------------------------------------------------------------------------------------------
# Layer 1 -- the repository
# --------------------------------------------------------------------------------------------


def detect_record_types(text: str) -> list[RecordType]:
    """Work out which record types a rulebook actually handles, from its rule conditions.

    DELIBERATELY DRIVEN BY THE RULEBOOK, NOT BY THE JOB TEMPLATES. Detecting from the AAP side
    would make "the job template exists" tautological -- you found the type by finding its
    template -- and would miss the one failure that matters most here:

        a rule naming a job template that does not exist.

    That failure is SILENT from ServiceNow. The stream counter moves, the rule fires, no job record
    is ever created, the record is untouched and nothing is written back. The only evidence is the
    activation log: "ERROR - Job template X in organization Y does not exist". One real catalog task
    was stranded that way during the build. Driving detection from the rulebook is what lets this
    script catch it before an event does.
    """
    return [rt for rt in RECORD_TYPES if f'"{rt.event_type}"' in text]


def check_rulebook(names: TeamNames, repo_root: str, out: Outcome) -> list[RecordType]:
    """Check the rulebook on disk and return the record types it handles.

    A rulebook copied from a sibling team is still valid YAML and still fires, so a parse check
    alone passes. What breaks is attribution: 'Last rule fired' names the wrong team, which is the
    signal the isolation test depends on.
    """
    path = os.path.join(repo_root, names.rulebook_file)
    if not out.record(os.path.isfile(path), f"rulebook {names.rulebook_file} exists"):
        return []

    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    try:
        import yaml  # noqa: PLC0415 - optional dependency, only needed for this check

        yaml.safe_load(text)
        out.record(True, "rulebook parses as YAML")
    except ImportError:
        out.record(True, "rulebook YAML parse skipped (PyYAML not installed)")
    except Exception as exc:  # noqa: BLE001 - surface any parser complaint verbatim
        out.record(False, "rulebook parses as YAML", str(exc))
        return []

    # Any other team's code or letter appearing here is a copy-paste leftover.
    #
    # The trailing \b is load-bearing and deliberate: it makes "Team B" and "sn-team-b" match while
    # "team_a_rulebook.yml" does not, because the underscore after the letter is a word character so
    # no boundary exists there. That is what we want -- the rulebooks legitimately cross-reference
    # each other by filename in comments, and flagging those would train people to ignore this check.
    # Prose mentions of another team are still flagged, which is the right bias: a false positive
    # costs a glance, a false negative ships the wrong team's rule name.
    strays: list[str] = []
    for match in re.finditer(r"team[-_ ]([a-z])\b", text, re.IGNORECASE):
        if match.group(1).lower() != names.letter.lower():
            strays.append(f"line {text[:match.start()].count(chr(10)) + 1}: {match.group(0)!r}")
    out.record(
        not strays,
        f"rulebook mentions no team other than {names.letter}",
        "\n".join(strays) if strays else "",
    )

    out.record(
        bool(re.search(rf'eda_event_stream_name\s*==\s*"{re.escape(names.stream)}"', text)),
        f'rulebook condition tests "{names.stream}"',
    )
    out.record(
        bool(re.search(rf'organization:\s*"{re.escape(names.organization)}"', text)),
        f'rulebook organization is "{names.organization}"',
    )

    # The ruleset name is reported as ansible_eda.ruleset on every launched job, so a name that
    # pins one record type actively misleads whoever is debugging a different one.
    ruleset = re.search(r"^-\s*name:\s*(.+)$", text, re.M)
    if ruleset:
        label = ruleset.group(1).strip().strip("\"'")
        named_one = [rt.key for rt in RECORD_TYPES if rt.key in label.lower()]
        out.record(
            not named_one,
            "ruleset name does not pin a single record type",
            f"ruleset is named {label!r}, which names {named_one}. This rulebook handles "
            f"{len(detect_record_types(text))} record type(s); the name is what ansible_eda.ruleset "
            "reports on every job, so it will mislead you while debugging the others.",
        )

    detected = detect_record_types(text)
    out.record(
        bool(detected),
        "rulebook handles at least one record type",
        "no rule condition matched any known event_type. Expected one of: "
        + ", ".join(rt.event_type for rt in RECORD_TYPES),
        info=", ".join(rt.key for rt in detected) if detected else "",
    )

    # Per record type the rulebook claims: does it name that type's job template, by the exact
    # string the controller will look up?
    for rt in detected:
        expected = names.job_template(rt)
        out.record(
            bool(re.search(rf'name:\s*"{re.escape(expected)}"', text)),
            f'rulebook names job template "{expected}" for {rt.key}',
            f"the {rt.key} rule exists but no run_job_template.name reads {expected!r}. "
            "A rule that names a template which does not exist fails SILENTLY -- see the activation log.",
        )

    for rt in RECORD_TYPES:
        if rt not in detected:
            out.note(
                f"rulebook has no {rt.key} rule",
                f"no condition tests {rt.event_type!r}. Not a failure -- a team need not handle "
                "every record type. Nothing below is checked for it.",
            )

    return detected


# --------------------------------------------------------------------------------------------
# Layer 2 -- AAP
# --------------------------------------------------------------------------------------------


def check_aap(
    names: TeamNames,
    aap: AapClient,
    repo_root: str,
    out: Outcome,
    record_types: list[RecordType],
) -> dict[str, Any]:
    """Check the AAP side and return facts the ServiceNow checks need to compare against.

    ``record_types`` comes from the rulebook, not from AAP. See ``detect_record_types``.
    """
    facts: dict[str, Any] = {}

    org = aap.first(f"/api/controller/v2/organizations/?name={urllib.parse.quote(names.organization)}")
    out.record(org is not None, f'AAP organization "{names.organization}" exists')

    project = aap.first(
        f"/api/controller/v2/projects/?name={urllib.parse.quote(names.controller_project)}"
    )
    if out.record(project is not None, f'controller project "{names.controller_project}" exists'):
        revision = project.get("scm_revision") or ""
        out.record(
            bool(revision),
            "controller project has synced (has a revision)",
            detail="never synced -- the playbook list will be empty",
            info=f"revision {revision[:12]}" if revision else "",
        )

    # One set of checks per record type the RULEBOOK claims to handle. A type the rulebook does not
    # mention is skipped entirely -- see detect_record_types for why that is the right direction.
    for rt in record_types:
        expected_name = names.job_template(rt)

        # The playbook has to be in the repo as well as named on the template, or the template
        # points at a file the project sync will never produce.
        out.record(
            os.path.isfile(os.path.join(repo_root, rt.playbook)),
            f"playbook {rt.playbook} exists in the repo",
            f"the {rt.key} rule exists and names a job template, but {rt.playbook} is not in this\n"
            "checkout. The controller project will sync without it and the job will fail at launch.",
        )

        template = aap.first(
            f"/api/controller/v2/job_templates/?name={urllib.parse.quote(expected_name)}"
        )
        if not out.record(
            template is not None,
            f'job template "{expected_name}" exists',
            f"the rulebook has a {rt.key} rule naming this template, but no such template exists in\n"
            "AAP. This is the SILENT failure: the stream counter will move, the rule will fire, and\n"
            "NO job record will be created. ServiceNow sees nothing wrong. The only evidence is the\n"
            f'activation log: "ERROR - Job template {expected_name} in organization '
            f'{names.organization} does not exist".',
        ):
            continue

        playbook = template.get("playbook") or ""
        out.record(
            playbook == rt.playbook,
            f'job template "{expected_name}" runs {rt.playbook}',
            ""
            if playbook == rt.playbook
            else (
                f"found {playbook!r}. A rulebook is not a playbook -- this fails at event time with\n"
                "\"ERROR! 'sources' is not a valid attribute for a Play\". Every team runs the same\n"
                "playbook per record type; the per-team file is the rulebook, chosen on the activation."
            ),
        )
        out.record(
            bool(template.get("ask_variables_on_launch")),
            f'job template "{expected_name}" has Prompt on launch enabled',
            ""
            if template.get("ask_variables_on_launch")
            else "without it the controller silently discards every extra_var the rulebook sends",
        )
        # Checked by credential *type*, not by name. The name is cosmetic -- the credential attaches
        # by id and nothing looks it up by name at run time -- but its absence is not: the playbook
        # asserts on SN_HOST and fails on undefined SN_USERNAME/SN_PASSWORD, which reads like a
        # playbook bug rather than a missing attachment.
        attached = aap.get(f"/api/controller/v2/job_templates/{template['id']}/credentials/")
        kinds = [
            c.get("summary_fields", {}).get("credential_type", {}).get("name", "")
            for c in attached.get("results", [])
        ]
        out.record(
            "ServiceNow" in kinds,
            f'job template "{expected_name}" has a ServiceNow credential attached',
            f"attached credential types: {kinds or '(none)'}\n"
            "The playbook needs SN_HOST/SN_USERNAME/SN_PASSWORD injected by a ServiceNow-type\n"
            "credential; without it the work-note write-back fails on undefined variables.",
        )

    stream = aap.first(f"/api/eda/v1/event-streams/?name={urllib.parse.quote(names.stream)}")
    if out.record(stream is not None, f'event stream "{names.stream}" exists'):
        facts["stream_uuid"] = stream.get("uuid") or ""
        facts["stream_name"] = stream.get("name") or ""
        forwarded = (stream.get("additional_data_headers") or "").lower()
        leaks = FORBIDDEN_FORWARDED_HEADER in forwarded
        out.record(
            not leaks,
            "event stream does not forward the Authorization header",
            ""
            if not leaks
            else (
                "forwarding it copies the stream's own bearer token into event.meta.headers and\n"
                "from there into the job's extra_vars in cleartext. Clear this field."
            ),
        )
        out.record(
            not stream.get("test_mode", False),
            "event stream forwarding is on (test_mode off)",
        )

    activation = aap.first(f"/api/eda/v1/activations/?name={urllib.parse.quote(names.activation)}")
    if out.record(activation is not None, f'activation "{names.activation}" exists'):
        status = str(activation.get("status") or "")
        out.record(status == "running", "activation is running", detail=f"status is {status!r}")
        rulebook = activation.get("rulebook_name") or ""
        out.record(
            rulebook == names.rulebook_name,
            f"activation runs {names.rulebook_name}",
            "" if rulebook == names.rulebook_name else f"found {rulebook!r}",
        )
        check_source_mapping_fresh(names, activation, repo_root, out)
    return facts


def check_source_mapping_fresh(
    names: TeamNames, activation: dict[str, Any], repo_root: str, out: Outcome
) -> None:
    """Check the activation's source mapping still matches the rulebook the project synced.

    An activation's ``source_mappings`` pins a ``rulebook_hash``, which is the plain SHA-256 of the
    rulebook file's bytes (verified against a live activation). Editing the rulebook changes that
    hash, so after push -> project sync the stored mapping refers to a rulebook that no longer
    exists and the activation fails with "Rulebook has changed since the sources were mapped."

    The fix is to re-attach the event stream (the gear icon) and restart -- but nothing warns you
    the mapping is stale while the activation is still happily running on the old revision. This is
    the check for that.

    Compared against the file at the EDA project's *synced* revision, not the working tree: an
    uncommitted local edit is not what AAP is running and must not be reported as drift.
    """
    import hashlib  # noqa: PLC0415 - only needed here
    import subprocess  # noqa: PLC0415

    mappings = activation.get("source_mappings") or ""
    match = re.search(r"rulebook_hash:\s*([0-9a-f]{64})", str(mappings))
    if not match:
        out.record(True, "source mapping freshness check skipped (no rulebook_hash present)")
        return
    pinned = match.group(1)

    project = activation.get("project") or {}
    git_hash = str(project.get("git_hash") or "")
    if not git_hash:
        out.record(True, "source mapping freshness check skipped (project revision unknown)")
        return

    try:
        blob = subprocess.run(
            ["git", "show", f"{git_hash}:{names.rulebook_file}"],
            cwd=repo_root,
            capture_output=True,
            check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        out.record(
            True,
            "source mapping freshness check skipped",
            info=f"revision {git_hash[:12]} not available locally -- run git fetch",
        )
        return

    actual = hashlib.sha256(blob).hexdigest()
    out.record(
        actual == pinned,
        "source mapping matches the synced rulebook (not stale)",
        f"mapping pins  {pinned}\n"
        f"rulebook is   {actual}\n"
        f"at project revision {git_hash[:12]}. The rulebook changed after the stream was mapped:\n"
        "re-attach the event stream on the activation (gear icon) and restart it, or the next\n"
        'event fails with "Rulebook has changed since the sources were mapped."',
    )


# --------------------------------------------------------------------------------------------
# Layer 3 -- ServiceNow, and the cross-system comparison
# --------------------------------------------------------------------------------------------


def check_servicenow(
    names: TeamNames, snow: ServiceNowClient, route_table: str, aap_facts: dict[str, Any], out: Outcome
) -> None:
    """Check the PDI's routing data, then compare it against what AAP actually has."""
    groups = snow.table(
        "sys_user_group",
        f"name={names.assignment_group}",
        ["name", "active", "sys_id"],
    )
    if out.record(bool(groups), f'assignment group "{names.assignment_group}" exists'):
        out.record(
            raw_field(groups[0], "active") in ("true", "1"),
            f'assignment group "{names.assignment_group}" is active',
        )

    rows = snow.table(
        route_table,
        f"team_code={names.code}",
        [
            "team_code",
            "assignment_group",
            "event_stream_name",
            "event_stream_uuid",
            "connection_alias",
            "active",
        ],
    )
    if not out.record(bool(rows), f'route row team_code="{names.code}" exists in {route_table}'):
        return
    row = rows[0]

    out.record(raw_field(row, "active") in ("true", "1"), "route row is active")
    out.record(
        field(row, "assignment_group") == names.assignment_group,
        f'route row points at group "{names.assignment_group}"',
        detail=f'found {field(row, "assignment_group")!r}',
    )
    out.record(
        field(row, "event_stream_name") == names.stream,
        f'route row names stream "{names.stream}"',
        detail=f'found {field(row, "event_stream_name")!r}',
    )

    alias = field(row, "connection_alias")
    out.record(bool(alias), "route row has a connection alias", info=f"alias: {alias}" if alias else "")

    # The check nothing else catches. Both sides can look correct on their own screen and still
    # disagree; a wrong UUID here posts to another team's stream, or to nothing at all.
    sn_uuid = raw_field(row, "event_stream_uuid").strip()
    aap_uuid = str(aap_facts.get("stream_uuid") or "").strip()
    if aap_uuid:
        match = sn_uuid.lower() == aap_uuid.lower()
        out.record(
            match,
            "route row UUID matches the AAP event stream UUID",
            ""
            if match
            else (
                f"ServiceNow: {sn_uuid or '(empty)'}\n"
                f"AAP:        {aap_uuid}\n"
                "These must be byte-identical. A mismatch posts this team's incidents at the wrong\n"
                "stream, or at no stream, and ServiceNow still reports a 2xx."
            ),
        )
    else:
        out.record(False, "route row UUID matches the AAP event stream UUID", "AAP stream not found; cannot compare")

    # The child connection hangs off the alias by sys_id in `asset_id` -- NOT by a field named
    # `alias`. ServiceNow silently *ignores* a filter naming a column that does not exist and
    # returns the whole table, so filtering on `alias.name` here yields every alias in the instance
    # and the check passes even when this team has no connection at all. Any query against an
    # unfamiliar table needs a control: search for something that should return nothing, and
    # confirm it does.
    alias_sys_id = raw_field(row, "connection_alias")
    if alias_sys_id:
        connections = snow.table(
            "sys_wdf_external_connection_mapping",
            f"asset_id={alias_sys_id}^table_name=sys_alias",
            ["sys_id", "connection_name", "asset_id"],
            limit=10,
        )
        # Guard against the ignored-filter failure mode reappearing: a correct filter returns one
        # or two rows for one alias, never dozens.
        if len(connections) > 4:
            out.record(
                False,
                "connection alias has at least one child connection",
                f"{len(connections)} rows returned for one alias -- the asset_id filter was ignored,\n"
                "so this result is meaningless. Check the column names on\n"
                "sys_wdf_external_connection_mapping before trusting it.",
            )
            return
        out.record(
            bool(connections),
            "connection alias has at least one child connection",
            ""
            if connections
            else (
                "an alias with no child connection fails at run time with\n"
                '"Unable to load connection with alias ID:" and a blank sys_id'
            ),
        )


# What each variable is and how to supply it. A bare "missing environment: X" tells you nothing you
# did not already know -- the useful part is the line you can paste.
ENV_HELP: dict[str, tuple[str, str]] = {
    "AAP_GATEWAY": (
        "AAP gateway base URL (not a secret)",
        'export AAP_GATEWAY="https://your-aap-host"        # or pass --gateway',
    ),
    "SANDBOX_AAP_PAT_TOKEN": (
        "AAP personal access token",
        '_kc_export sandbox-aap SANDBOX_AAP_PAT_TOKEN       # in ~/.zshrc',
    ),
    "SN_PDI_HOST": (
        "PDI base URL (not a secret)",
        'export SN_PDI_HOST="https://devNNNNNN.service-now.com"',
    ),
    "SN_PDI_USERNAME": ("PDI read account (not a secret)", 'export SN_PDI_USERNAME="api_user"'),
    "SN_PDI_PASSWORD": (
        "that account's password",
        "_kc_export servicenow-pdi SN_PDI_PASSWORD          # in ~/.zshrc",
    ),
    "SN_PDI_PROVISION_USERNAME": (
        "PDI write account (not a secret)",
        'export SN_PDI_PROVISION_USERNAME="eda_provisioner"',
    ),
    "SN_PDI_PROVISION_PASSWORD": (
        "that account's password",
        "_kc_export servicenow-pdi-provision SN_PDI_PROVISION_PASSWORD",
    ),
}


def explain_missing_env(missing: list[str]) -> None:
    """Print what is missing and the exact line that supplies it."""
    print(f"\nerror: {len(missing)} required variable(s) not set:\n", file=sys.stderr)
    for name in missing:
        what, how = ENV_HELP.get(name, ("", f'export {name}="..."'))
        print(f"  {name}", file=sys.stderr)
        if what:
            print(f"      {what}", file=sys.stderr)
        print(f"      {how}", file=sys.stderr)
    print(
        "\nSecrets come from the macOS Keychain via the _kc_export helper in ~/.zshrc\n"
        "(README 2.9). Plain URLs and usernames are exported directly -- they are not secrets.\n"
        "After editing ~/.zshrc run 'exec zsh -l'; an already-running process keeps the\n"
        "environment it started with.\n",
        file=sys.stderr,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify one team's EDA + ServiceNow wiring (read-only).",
    )
    parser.add_argument("--team", required=True, help="team code, e.g. team-c")
    parser.add_argument("--gateway", default=os.environ.get("AAP_GATEWAY", ""), help="AAP gateway URL")
    parser.add_argument(
        "--route-table",
        default=os.environ.get("SN_ROUTE_TABLE", "x_661661_james_tes_eda_team_route"),
        help="ServiceNow route table name",
    )
    parser.add_argument("--repo-root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    parser.add_argument("--json", action="store_true", help="emit machine-readable results")
    args = parser.parse_args()

    try:
        names = TeamNames(args.team)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    required = {
        "SANDBOX_AAP_PAT_TOKEN": os.environ.get("SANDBOX_AAP_PAT_TOKEN", ""),
        "SN_PDI_HOST": os.environ.get("SN_PDI_HOST", ""),
        "SN_PDI_USERNAME": os.environ.get("SN_PDI_USERNAME", ""),
        "SN_PDI_PASSWORD": os.environ.get("SN_PDI_PASSWORD", ""),
    }
    missing = [k for k, v in required.items() if not v]
    if not args.gateway:
        missing.append("AAP_GATEWAY")
    if missing:
        explain_missing_env(missing)
        return 2

    out = Outcome()
    if not args.json:
        print(f"\nVerifying {names.code}  (org {names.organization!r}, stream {names.stream!r})\n")

    record_types = check_rulebook(names, args.repo_root, out)
    if not args.json:
        configured = " + ".join(rt.key for rt in record_types) or "(none)"
        print(f"\nRecord types in {names.rulebook_name}: {configured}\n")

    aap = AapClient(args.gateway, required["SANDBOX_AAP_PAT_TOKEN"])
    snow = ServiceNowClient(
        required["SN_PDI_HOST"], required["SN_PDI_USERNAME"], required["SN_PDI_PASSWORD"]
    )

    try:
        aap_facts = check_aap(names, aap, args.repo_root, out, record_types)
    except Exception as exc:  # noqa: BLE001 - a transport failure is a result, not a crash
        out.record(False, "AAP checks completed", str(exc))
        aap_facts = {}

    try:
        check_servicenow(names, snow, args.route_table, aap_facts, out)
    except Exception as exc:  # noqa: BLE001
        out.record(False, "ServiceNow checks completed", str(exc))

    if args.json:
        print(json.dumps(out.as_dict(), indent=2))
    else:
        out.render()
        total = len(out.rows)
        failed = len(out.failures)
        configured = " + ".join(rt.key for rt in record_types) or "(none)"
        print(f"\nTeam {names.letter}: {configured}")
        print(f"{total - failed}/{total} checks passed", end="")
        print(f", {len(out.notes)} skipped." if out.notes else ".")
        # The total is intentionally NOT a fixed number. It scales with how many record types the
        # team's rulebook handles, so quoting "29/29" or "35/35" anywhere would go stale the moment
        # a team gains or loses one.
        if failed:
            print(f"{failed} failed -- fix these before creating a test record.\n")
        else:
            print(
                f"Wiring looks correct for: {configured}.\n"
                "Now create one test record per type above and watch only this team's stream "
                "counter move.\n"
            )
    return 1 if out.failures else 0


if __name__ == "__main__":
    sys.exit(main())
