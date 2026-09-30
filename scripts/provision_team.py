#!/usr/bin/env python3
"""Provision one team's AAP objects, and render its rulebook and ServiceNow checklist.

Why this exists
---------------
`verify_team.py` *checks* for the failures the runbook warns about. This script removes several of
them from existence:

* **Token mismatch** -- the token is generated once here and used for both sides, so there is no
  paste step to get wrong.
* **UUID mismatch** -- the event stream is created here, so its UUID is known rather than copied.
* **Playbook vs rulebook** -- a constant, not a dropdown.
* **`ask_variables_on_launch` off** -- a constant.
* **A leftover team name in a copied rulebook** -- the rulebook is rendered and then checked.

Safety
------
* **Dry run is the default.** Nothing is written without ``--apply``.
* Every step is **check-then-create**, so re-running after a partial failure resumes rather than
  duplicating.
* Everything created is recorded in a **manifest**, which is what makes ``--destroy`` exact.
* Secrets are never printed. Payload previews mask them.

ServiceNow
----------
By default this script does **not** write the five ServiceNow objects -- it prints a checklist with
fully resolved values for you to enter. ``--servicenow-apply`` performs the inserts instead.

Verified 2026-09-30 by provisioning a real team end to end: the event stream counter moved for the new
team only, the job ran, the incident closed, and the flow and action were **not modified**. One known
cosmetic quirk: ``sys_scope`` cannot be set through the Table API, so the alias is created in *global*
rather than in the scoped application and its ``id`` lacks the ``x_<scope>.`` prefix. Routing is
unaffected -- the flow resolves the alias by sys_id at run time.

**This never touches the flow or the action.** Adding a team creates new records only; if something
here ever seems to need a Workflow Studio edit, that is a bug in this script, not a missing feature.

Usage
-----
    # 1. render the rulebook, then commit and push it yourself
    python3 scripts/provision_team.py --team team-d --render-rulebook

    # 2. preview everything (writes nothing)
    python3 scripts/provision_team.py --team team-d

    # 3. build the AAP side for real
    python3 scripts/provision_team.py --team team-d --apply

    # remove everything this script created
    python3 scripts/provision_team.py --team team-d --destroy --apply

Environment
-----------
    SANDBOX_AAP_PAT_TOKEN          AAP token; also used as the EDA controller credential
    AAP_GATEWAY                    AAP gateway base URL (or --gateway)
    SN_PDI_HOST                    PDI base URL
    SN_PDI_PROVISION_USERNAME      write-capable PDI account
    SN_PDI_PROVISION_PASSWORD      its password
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import secrets
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

SHARED_PLAYBOOK = "servicenow_incident_handler.yml"
DE_IMAGE = "registry.redhat.io/ansible-automation-platform-27/de-supported-rhel9:latest"
REPO_URL = "https://github.com/drumforgod82/Ansible_EDA_Test.git"
DEFAULT_BRANCH = "main"
SECRET_KEYS = {"token", "password", "oauth_token", "api_key", "secret"}
SYNC_TIMEOUT_SECONDS = 300


def mask(payload: Any) -> Any:
    """Recursively replace secret values so a payload can be printed."""
    if isinstance(payload, dict):
        return {k: ("<redacted>" if k in SECRET_KEYS and v else mask(v)) for k, v in payload.items()}
    if isinstance(payload, list):
        return [mask(v) for v in payload]
    return payload


class Names:
    """All names for a team, derived from its code by the runbook's convention."""

    def __init__(self, code: str) -> None:
        if not re.fullmatch(r"team-[a-z]", code):
            raise ValueError(f"team code must look like 'team-d', got {code!r}")
        self.code = code
        letter = code.rsplit("-", 1)[1]
        self.lower = letter
        self.letter = letter.upper()
        self.org = f"Team {self.letter}"
        self.inventory = f"Team {self.letter} Inventory"
        # Matches what is actually deployed, and the stock "ServiceNow PDI Admin" naming.
        # An earlier §9 table said "Team X ServiceNow PDI"; reality won.
        self.sn_credential = f"ServiceNow PDI - Team {self.letter}"
        self.controller_project = f"EDA ServiceNow - Team {self.letter}"
        self.job_template = f"Team {self.letter} Incident Handler"
        self.controller_credential = f"AAP Controller - Team {self.letter}"
        self.decision_environment = f"DE Supported RHEL9 - Team {self.letter}"
        self.eda_project = f"Ansible EDA Test - Team {self.letter}"
        self.stream_credential = f"{code}-stream-token"
        self.stream = f"sn-{code}"
        self.activation = f"{code}-incidents"
        self.rulebook_name = f"team_{letter}_rulebook.yml"
        self.rulebook_path = f"rulebooks/team_{letter}_rulebook.yml"
        self.group = f"Team-{self.letter}"
        self.sn_token_credential = f"Ansible EDA Team {self.letter} Token"
        self.sn_alias = f"Ansible EDA Team {self.letter} Alias"
        self.sn_connection = f"Ansible EDA Team {self.letter} Connection"


class Manifest:
    """Records what was created so --destroy can undo exactly that and nothing else."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.data: dict[str, Any] = {"created": []}
        if os.path.exists(path):
            with open(path, encoding="utf-8") as handle:
                self.data = json.load(handle)

    def add(self, kind: str, endpoint: str, identifier: Any, name: str) -> None:
        entry = {"kind": kind, "endpoint": endpoint, "id": identifier, "name": name}
        if entry not in self.data["created"]:
            self.data["created"].append(entry)
            self.save()

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump(self.data, handle, indent=2)


class Http:
    """Minimal JSON HTTP client that retries the sandbox's cold-start 503s."""

    def __init__(self, base: str, headers: dict[str, str], insecure: bool = False) -> None:
        self.base = base.rstrip("/")
        self.headers = {"Accept": "application/json", **headers}
        self.ctx = ssl.create_default_context()
        if insecure:
            self.ctx.check_hostname = False
            self.ctx.verify_mode = ssl.CERT_NONE

    def call(self, method: str, path: str, body: dict | None = None) -> tuple[int, Any]:
        data = json.dumps(body).encode() if body is not None else None
        headers = dict(self.headers)
        if data:
            headers["Content-Type"] = "application/json"
        for attempt in range(3):
            req = urllib.request.Request(
                f"{self.base}{path}", data=data, headers=headers, method=method
            )
            try:
                with urllib.request.urlopen(req, timeout=60, context=self.ctx) as resp:
                    raw = resp.read()
                    return resp.status, (json.loads(raw) if raw else None)
            except urllib.error.HTTPError as exc:
                raw = exc.read()
                if exc.code == 503 and attempt < 2:
                    time.sleep(20)
                    continue
                try:
                    return exc.code, json.loads(raw)
                except Exception:  # noqa: BLE001
                    return exc.code, raw.decode(errors="replace")[:400]
            except Exception as exc:  # noqa: BLE001
                if attempt < 2:
                    time.sleep(3)
                    continue
                raise RuntimeError(f"{method} {path}: {exc}") from exc
        raise RuntimeError(f"{method} {path}: exhausted retries")

    def get(self, path: str) -> Any:
        status, body = self.call("GET", path)
        if status != 200:
            raise RuntimeError(f"GET {path} -> {status}: {body}")
        return body


class Provisioner:
    def __init__(self, args: argparse.Namespace, names: Names) -> None:
        self.args = args
        self.names = names
        self.apply = args.apply
        self.aap = Http(
            args.gateway,
            {"Authorization": f"Bearer {os.environ['SANDBOX_AAP_PAT_TOKEN']}"},
            insecure=True,
        )
        self.manifest = Manifest(os.path.join(args.repo_root, ".provision", f"{names.code}.json"))
        self.facts: dict[str, Any] = {}

    # -- plumbing ---------------------------------------------------------------------------

    def step(self, label: str) -> None:
        print(f"\n\033[1m{label}\033[0m")

    def note(self, text: str) -> None:
        print(f"    {text}")

    def ensure(self, kind: str, list_path: str, create_path: str, payload: dict, name: str) -> Any:
        """Find an object by name, or create it. Returns its id.

        Check-then-create is what makes a re-run after a partial failure safe.
        """
        found = self.aap.get(f"{list_path}?name={urllib.parse.quote(name)}")
        results = found.get("results", []) if isinstance(found, dict) else []
        if results:
            identifier = results[0].get("id")
            self.note(f"exists  {kind}: {name} (id {identifier})")
            return identifier
        if not self.apply:
            self.note(f"CREATE  {kind}: {name}")
            self.note(f"        POST {create_path}")
            self.note(f"        {json.dumps(mask(payload))[:400]}")
            return f"<{kind}-id>"
        status, body = self.aap.call("POST", create_path, payload)
        if status not in (200, 201):
            raise RuntimeError(f"creating {kind} {name!r} -> {status}: {body}")
        identifier = body.get("id")
        self.note(f"created {kind}: {name} (id {identifier})")
        self.manifest.add(kind, create_path, identifier, name)
        return identifier

    def credential_type_id(self, api: str, name: str) -> Any:
        """Resolve a credential type by name. Ids differ per instance -- ServiceNow is custom."""
        path = f"/api/{api}/v2/credential_types/" if api == "controller" else "/api/eda/v1/credential-types/"
        listing = self.aap.get(f"{path}?page_size=200")
        for item in listing.get("results", []):
            if item.get("name") == name:
                return item.get("id")
        raise RuntimeError(f"credential type {name!r} not found via {path}")

    # -- phase A ----------------------------------------------------------------------------

    def render_rulebook(self) -> str:
        """Render this team's rulebook from an existing one, then prove nothing was left behind.

        Rendering from a real rulebook rather than an embedded template keeps one source of truth --
        the template cannot drift from what is actually running. The substitution is then *checked*,
        which is the part a human copy-paste skips.
        """
        src = os.path.join(self.args.repo_root, f"rulebooks/team_{self.args.template}_rulebook.yml")
        dst = os.path.join(self.args.repo_root, self.names.rulebook_path)

        # Never silently overwrite an existing rulebook. A team's rulebook is where per-team
        # automation diverges -- extra rules, different conditions -- and re-rendering from the
        # template would throw all of that away. This matters most on a re-run, which is exactly
        # when the file already exists.
        if os.path.exists(dst) and not self.args.force_render:
            self.note(f"exists  {self.names.rulebook_path} (not re-rendering; --force-render to overwrite)")
            return dst

        with open(src, encoding="utf-8") as handle:
            text = handle.read()

        up, lo = self.args.template.upper(), self.args.template.lower()
        rendered = text
        for old, new in (
            (f"Team {up} - ServiceNow", f"Team {self.names.letter} - ServiceNow"),
            (f"Launch Team {up} incident handler", f"Launch Team {self.names.letter} incident handler"),
            (f'"sn-team-{lo}"', f'"{self.names.stream}"'),
            (f'"Team {up} Incident Handler"', f'"{self.names.job_template}"'),
            (f'organization: "Team {up}"', f'organization: "{self.names.org}"'),
            (f"# Team {up} incident automation", f"# Team {self.names.letter} incident automation"),
        ):
            rendered = rendered.replace(old, new)

        # The check a copy-paste never gets. A cross-reference like "team_a_rulebook.yml" is fine --
        # the \b does not match before an underscore -- but prose naming another team is not.
        strays = [
            m.group(0)
            for m in re.finditer(r"team[-_ ]([a-z])\b", rendered, re.IGNORECASE)
            if m.group(1).lower() != self.names.lower
        ]
        if strays:
            raise RuntimeError(
                f"rendered rulebook still mentions another team: {sorted(set(strays))}. "
                "Fix the substitution table in render_rulebook() rather than editing by hand."
            )
        try:
            import yaml  # noqa: PLC0415

            yaml.safe_load(rendered)
        except ImportError:
            pass

        if not self.apply:
            self.note(f"WRITE   {self.names.rulebook_path} ({len(rendered)} bytes, from team_{lo})")
            return dst
        with open(dst, "w", encoding="utf-8") as handle:
            handle.write(rendered)
        self.note(f"wrote   {self.names.rulebook_path}")
        self.note(f"sha256  {hashlib.sha256(rendered.encode()).hexdigest()}")
        return dst

    def require_pushed(self) -> str:
        """Refuse to continue until the rulebook is on the remote branch.

        The EDA project can only offer a rulebook that the *remote* has, so a local-only file
        produces a confusing "no rulebooks found" later. Gating is better than trusting.
        """
        root, branch = self.args.repo_root, self.args.branch
        subprocess.run(["git", "fetch", "origin", branch], cwd=root, capture_output=True, check=False)
        rev = f"origin/{branch}:{self.names.rulebook_path}"
        probe = subprocess.run(["git", "cat-file", "-e", rev], cwd=root, capture_output=True)
        if probe.returncode != 0:
            raise SystemExit(
                f"\n{self.names.rulebook_path} is not on origin/{branch} yet.\n"
                f"Commit and push it, then re-run. (git add {self.names.rulebook_path} && "
                'git commit -m "add ' + self.names.rulebook_name + '" && git push)\n'
            )
        blob = subprocess.run(
            ["git", "show", rev], cwd=root, capture_output=True, check=True
        ).stdout
        digest = hashlib.sha256(blob).hexdigest()
        self.note(f"on origin/{branch}, sha256 {digest}")
        return digest

    # -- phase B: AAP -----------------------------------------------------------------------

    def build_aap(self, rulebook_sha: str) -> None:
        names = self.names

        description = f"{names.org} - EDA event stream routing"

        self.step("AAP 1/11  organization (via the gateway -- see the note below)")
        # Organizations belong to the **gateway**, which fans them out to the controller and to EDA.
        # Both of the other routes are wrong, and each fails differently and late:
        #
        #   POST /api/controller/v2/organizations/  -> 201. Appears on the gateway and the
        #       controller, and **never reaches EDA** -- still absent after 90s of polling. The
        #       first EDA object you create then fails with
        #       "Organization with id N does not exist", by which point you have already built
        #       five controller objects.
        #   POST /api/eda/v1/organizations/         -> 403
        #       "Create should be done through the platform ingress".
        #
        # Both measured on AAP 2.7, 2026-09-30. Create through the gateway and let it propagate.
        self.ensure(
            "organization",
            "/api/gateway/v1/organizations/",
            "/api/gateway/v1/organizations/",
            {"name": names.org, "description": description},
            names.org,
        )
        # Resolve the id each service assigned. They usually agree, but nothing guarantees it, so
        # never reuse one id across APIs.
        org = self.await_org("/api/controller/v2/organizations/", "controller")
        eda_org = self.await_org("/api/eda/v1/organizations/", "EDA")
        self.facts["organization"] = org

        self.step("AAP 2/11  inventory + localhost")
        inventory = self.ensure(
            "inventory",
            "/api/controller/v2/inventories/",
            "/api/controller/v2/inventories/",
            {"name": names.inventory, "organization": org, "variables": "ansible_connection: local"},
            names.inventory,
        )
        if self.apply:
            hosts = self.aap.get(f"/api/controller/v2/inventories/{inventory}/hosts/")
            if not hosts.get("results"):
                self.aap.call(
                    "POST", f"/api/controller/v2/inventories/{inventory}/hosts/", {"name": "localhost"}
                )
                self.note("created host: localhost")
            else:
                self.note("exists  host: localhost")

        self.step("AAP 3/11  ServiceNow credential (playbook write-back)")
        sn_type = self.credential_type_id("controller", "ServiceNow")
        sn_cred = self.ensure(
            "credential",
            "/api/controller/v2/credentials/",
            "/api/controller/v2/credentials/",
            {
                "name": names.sn_credential,
                "credential_type": sn_type,
                "organization": org,
                "inputs": {
                    "host": os.environ["SN_PDI_HOST"],
                    "username": os.environ["SN_PDI_PROVISION_USERNAME"],
                    "password": os.environ["SN_PDI_PROVISION_PASSWORD"],
                },
            },
            names.sn_credential,
        )

        self.step("AAP 4/11  controller project (+ sync)")
        project = self.ensure(
            "project",
            "/api/controller/v2/projects/",
            "/api/controller/v2/projects/",
            {
                "name": names.controller_project,
                "organization": org,
                "scm_type": "git",
                "scm_url": self.args.repo_url,
                "scm_branch": self.args.branch,
            },
            names.controller_project,
        )
        if self.apply:
            self.wait_controller_sync(project)

        self.step("AAP 5/11  job template")
        template = self.ensure(
            "job_template",
            "/api/controller/v2/job_templates/",
            "/api/controller/v2/job_templates/",
            {
                "name": names.job_template,
                "description": f"{names.org} - launched by {names.rulebook_name}",
                "job_type": "run",
                "organization": org,
                "inventory": inventory,
                "project": project,
                "playbook": SHARED_PLAYBOOK,
                "ask_variables_on_launch": True,
            },
            names.job_template,
        )
        if self.apply:
            attached = self.aap.get(f"/api/controller/v2/job_templates/{template}/credentials/")
            if not any(c.get("id") == sn_cred for c in attached.get("results", [])):
                status, body = self.aap.call(
                    "POST", f"/api/controller/v2/job_templates/{template}/credentials/", {"id": sn_cred}
                )
                if status not in (200, 201, 204):
                    raise RuntimeError(f"attaching credential -> {status}: {body}")
                self.note("attached ServiceNow credential")

        self.step("AAP 6/11  EDA controller credential (uses the PAT, not a password)")
        aap_type = self.credential_type_id("eda", "Red Hat Ansible Automation Platform")
        controller_cred = self.ensure(
            "eda_credential",
            "/api/eda/v1/eda-credentials/",
            "/api/eda/v1/eda-credentials/",
            {
                "name": names.controller_credential,
                "credential_type_id": aap_type,
                "organization_id": eda_org,
                "inputs": {
                    # Host must end at /api/controller/ -- adding v2 doubles the version segment
                    # and the job-template lookup 404s.
                    "host": f"{self.args.gateway.rstrip('/')}/api/controller/",
                    "oauth_token": os.environ["SANDBOX_AAP_PAT_TOKEN"],
                    "verify_ssl": False,
                    "request_timeout": "10",
                },
            },
            names.controller_credential,
        )

        self.step("AAP 7/11  decision environment")
        decision_env = self.ensure(
            "decision_environment",
            "/api/eda/v1/decision-environments/",
            "/api/eda/v1/decision-environments/",
            {"name": names.decision_environment, "image_url": DE_IMAGE, "organization_id": eda_org},
            names.decision_environment,
        )

        self.step("AAP 8/11  EDA project (+ sync)")
        eda_project = self.ensure(
            "eda_project",
            "/api/eda/v1/projects/",
            "/api/eda/v1/projects/",
            {
                "name": names.eda_project,
                "url": self.args.repo_url,
                "scm_branch": self.args.branch,
                "organization_id": eda_org,
            },
            names.eda_project,
        )
        if self.apply:
            self.wait_eda_sync(eda_project)

        self.step("AAP 9/11  event stream credential (token generated here)")
        token = secrets.token_hex(32)
        stream_type = self.credential_type_id("eda", "ServiceNow Event Stream")
        stream_cred = self.ensure(
            "eda_credential",
            "/api/eda/v1/eda-credentials/",
            "/api/eda/v1/eda-credentials/",
            {
                "name": names.stream_credential,
                "credential_type_id": stream_type,
                "organization_id": eda_org,
                # Bare token, no "Bearer " prefix -- the type compares the header verbatim.
                "inputs": {"auth_type": "token", "token": token, "http_header_key": "Authorization"},
            },
            names.stream_credential,
        )
        self.facts["token"] = token

        self.step("AAP 10/11  event stream")
        existing = self.aap.get(f"/api/eda/v1/event-streams/?name={urllib.parse.quote(names.stream)}")
        results = existing.get("results", [])
        if results:
            stream = results[0]
            self.note(f"exists  event_stream: {names.stream} (id {stream['id']})")
            self.facts["stream_uuid"] = stream.get("uuid")
            self.facts["stream_id"] = stream.get("id")
            self.facts["token"] = None  # the stored token is the old one; do not claim otherwise
        elif not self.apply:
            self.note(f"CREATE  event_stream: {names.stream}")
            self.facts["stream_uuid"] = "<assigned-on-create>"
            self.facts["stream_id"] = "<assigned-on-create>"
        else:
            status, body = self.aap.call(
                "POST",
                "/api/eda/v1/event-streams/",
                {
                    "name": names.stream,
                    "eda_credential_id": stream_cred,
                    "organization_id": eda_org,
                    "test_mode": False,
                    # Never forward Authorization: it copies the bearer token into
                    # event.meta.headers and from there into the job's extra_vars in cleartext.
                    "additional_data_headers": "",
                },
            )
            if status not in (200, 201):
                raise RuntimeError(f"creating event stream -> {status}: {body}")
            self.note(f"created event_stream: {names.stream} (id {body['id']})")
            self.manifest.add("event_stream", "/api/eda/v1/event-streams/", body["id"], names.stream)
            self.facts["stream_uuid"] = body.get("uuid")
            self.facts["stream_id"] = body.get("id")

        self.step("AAP 11/11  rulebook activation")
        if self.args.no_activate:
            self.note("skipped (--no-activate). Create it in the UI when you have pod capacity.")
            return
        rulebook_id = None
        if self.apply:
            books = self.aap.get(f"/api/eda/v1/rulebooks/?project_id={eda_project}&page_size=200")
            for book in books.get("results", []):
                if book.get("name") == names.rulebook_name:
                    rulebook_id = book.get("id")
            if rulebook_id is None:
                raise RuntimeError(
                    f"{names.rulebook_name} not found in EDA project {eda_project}. "
                    "Is it pushed and did the sync complete?"
                )
        source_mappings = (
            "- source_name: __SOURCE_1\n"
            f"  event_stream_id: {self.facts['stream_id']}\n"
            f"  event_stream_name: {names.stream}\n"
            f"  rulebook_hash: {rulebook_sha}\n"
        )
        self.ensure(
            "activation",
            "/api/eda/v1/activations/",
            "/api/eda/v1/activations/",
            {
                "name": names.activation,
                "project_id": eda_project,
                "rulebook_id": rulebook_id or "<rulebook-id>",
                "decision_environment_id": decision_env,
                "organization_id": eda_org,
                "eda_credentials": [controller_cred],
                "source_mappings": source_mappings,
                "log_level": "debug",
                "restart_policy": "on-failure",
                "is_enabled": True,
            },
            names.activation,
        )

    def await_org(self, list_path: str, service: str, timeout: int = 90) -> Any:
        """Wait for the gateway's organization to appear in one service, and return its local id.

        Propagation is not instant, and an EDA object created a moment too early fails with a
        confusing "Organization with id N does not exist" rather than a retryable error.
        """
        if not self.apply:
            self.note(f"RESOLVE {service} org id for {self.names.org}")
            return f"<{service}-org-id>"
        deadline = time.time() + timeout
        while True:
            listing = self.aap.get(f"{list_path}?name={urllib.parse.quote(self.names.org)}")
            results = listing.get("results", [])
            if results:
                identifier = results[0]["id"]
                self.note(f"{service} org id: {identifier}")
                return identifier
            if time.time() > deadline:
                raise RuntimeError(
                    f"{self.names.org} never appeared in {service} after {timeout}s. "
                    "If it exists on the gateway but not here, it was created on the wrong API -- "
                    "delete it and let this script create it through the gateway."
                )
            time.sleep(5)

    def wait_controller_sync(self, project: Any) -> None:
        status, body = self.aap.call("POST", f"/api/controller/v2/projects/{project}/update/", {})
        if status not in (200, 201, 202):
            self.note(f"sync request returned {status}: {body}")
        deadline = time.time() + SYNC_TIMEOUT_SECONDS
        while time.time() < deadline:
            current = self.aap.get(f"/api/controller/v2/projects/{project}/")
            if current.get("status") in ("successful", "failed", "error", "canceled"):
                self.note(f"sync {current.get('status')}, revision {str(current.get('scm_revision'))[:12]}")
                if current.get("status") != "successful":
                    raise RuntimeError(f"controller project sync {current.get('status')}")
                return
            time.sleep(5)
        raise RuntimeError("controller project sync timed out")

    def wait_eda_sync(self, project: Any) -> None:
        deadline = time.time() + SYNC_TIMEOUT_SECONDS
        while time.time() < deadline:
            current = self.aap.get(f"/api/eda/v1/projects/{project}/")
            state = current.get("import_state")
            if state in ("completed", "failed"):
                self.note(f"sync {state}, revision {str(current.get('git_hash'))[:12]}")
                if state != "completed":
                    raise RuntimeError(f"EDA project sync failed: {current.get('import_error')}")
                return
            time.sleep(5)
        raise RuntimeError("EDA project sync timed out (check the default_worker memory limit)")

    # -- ServiceNow -------------------------------------------------------------------------

    def servicenow(self) -> None:
        names, facts = self.names, self.facts
        gateway = self.args.gateway.rstrip("/") + "/"
        uuid = facts.get("stream_uuid", "<create the stream first>")
        token_line = (
            "the token generated in step 9 of this run"
            if facts.get("token")
            else "the existing token for this stream (this run did not create it)"
        )
        heading = "5 objects" if self.args.servicenow_apply else "5 objects -- CHECKLIST (nothing written)"
        self.step(f"ServiceNow  {heading}")
        print(
            f"""
    Set the application picker to your scoped app, except where noted.

    1. Assignment group          {names.group}
       User Administration > Groups > New, **in Global** (sys_user_group is a platform table)
       Add at least one member, or the flow's trigger condition never fires.

    2. API Key credential        {names.sn_token_credential}
       Header name               Authorization
       API key value             {token_line}
       API Key Prefix            LEAVE EMPTY -- a "Bearer " prefix breaks this credential type

    3. Connection & Credential Alias   {names.sn_alias}
       Type                      Connection and Credential
       Connection type           HTTP

    4. HTTP connection           {names.sn_connection}
       Create from the alias's **HTTP Connections related list**, not the Connections table
       Connection URL            {gateway}   (base URL only)
       Credential                {names.sn_token_credential}

    5. Route row in {self.args.route_table}
       team_code                 {names.code}
       assignment_group          {names.group}
       event_stream_name         {names.stream}
       event_stream_uuid         {uuid}
       connection_alias          {names.sn_alias}
       active                    true
"""
        )
        if not self.args.servicenow_apply:
            self.note("Re-run with --servicenow-apply to create these automatically instead.")
            return
        self.servicenow_apply(uuid)

    def servicenow_apply(self, uuid: str) -> None:
        """Insert the five ServiceNow objects. Verified end to end 2026-09-30.

        Field values come from reading working records with sysparm_display_value=false. Display
        values are rejected on insert and the raw forms are not guessable -- see the comments inline.
        """
        host = os.environ["SN_PDI_HOST"].rstrip("/")
        cred = base64.b64encode(
            f"{os.environ['SN_PDI_PROVISION_USERNAME']}:{os.environ['SN_PDI_PROVISION_PASSWORD']}".encode()
        ).decode()
        snow = Http(host, {"Authorization": f"Basic {cred}"})
        names, token = self.names, self.facts.get("token")
        # The token is needed ONLY to create the API Key credential. On a resume the event stream
        # already exists, so this run has no token (AAP stores it encrypted and will not give it
        # back) -- but the credential was created by the earlier run, so nothing is missing. Bailing
        # out here would strand the remaining objects, which is what it used to do.

        def insert(table: str, payload: dict, label: str, key: str = "name") -> str:
            """Find by `key`, else insert. `key` is not always 'name'.

            The route table has no `name` column -- it is keyed on team_code. Querying a column a
            scoped table does not have returns **403 "Field(s) present in the query do not have
            permission to be read"**, which reads like a rights problem rather than a typo. Note
            this differs from platform tables, where an unknown query field is silently ignored and
            you get the whole table back instead.
            """
            found = snow.get(
                f"/api/now/table/{table}?sysparm_query={key}={urllib.parse.quote(label)}"
                "&sysparm_fields=sys_id&sysparm_limit=1"
            )
            rows = found.get("result", [])
            if rows:
                self.note(f"exists  {table}: {label}")
                return rows[0]["sys_id"]
            if not self.apply:
                self.note(f"CREATE  {table}: {label}  {json.dumps(mask(payload))[:220]}")
                return f"<{table}-sys_id>"
            status, body = snow.call("POST", f"/api/now/table/{table}", payload)
            if status not in (200, 201):
                raise RuntimeError(f"insert {table} {label!r} -> {status}: {body}")
            sys_id = body["result"]["sys_id"]
            self.note(f"created {table}: {label} ({sys_id})")
            self.manifest.add(f"sn:{table}", f"/api/now/table/{table}", sys_id, label)
            return sys_id

        # Every value below was read off the working Team C records with
        # sysparm_display_value=false. Display values are NOT accepted on insert, and the raw forms
        # are not guessable: type is 'connection' (not 'connection_and_credential'), connection_type
        # is 'http_connection' (not 'http'). Do not "tidy" these into what the UI shows.
        scope = self.sn_scope_sys_id(snow)
        self.note(f"scope sys_id: {scope}")

        insert("sys_user_group", {"name": names.group, "active": "true"}, names.group)

        # Look first: if it exists we do not need a token at all.
        existing_cred = snow.get(
            f"/api/now/table/api_key_credentials?sysparm_query=name="
            f"{urllib.parse.quote(names.sn_token_credential)}&sysparm_fields=sys_id&sysparm_limit=1"
        ).get("result", [])
        if not existing_cred and not token:
            raise SystemExit(
                f"\n{names.sn_token_credential} does not exist and this run has no token.\n"
                "AAP will not reveal an existing stream's token, so the credential cannot be set "
                "from a resume.\nEither create the credential by hand with the token you saved, or "
                "--destroy and provision the team in one pass.\n"
            )
        credential_id = insert(
            "api_key_credentials",
            {
                "name": names.sn_token_credential,
                "type": "api_key",
                "classification": "api_key",
                "api_key": token,
                # Bare token: the 'API Key Prefix' field is simply never set.
                "api_key_header_name": "Authorization",
                "credential_store_type": "other",
                "lookup_key": "credential_id",
                "applies_to": "all",
                "order": "100",
                "active": "true",
                "application": scope,
            },
            names.sn_token_credential,
        )
        alias_id = insert(
            "sys_alias",
            {
                "name": names.sn_alias,
                "type": "connection",
                "connection_type": "http_connection",
                "multiple_connections": "false",
                "is_internal": "false",
                "retry_policy": self.args.retry_policy,
                "sys_scope": scope,
            },
            names.sn_alias,
        )
        insert(
            "http_connection",
            {
                "name": names.sn_connection,
                "connection_alias": alias_id,
                "connection_url": self.args.gateway.rstrip("/") + "/",
                "credential": credential_id,
                "active": "true",
                "use_mid": "false",
                "mid_selection": "auto_select",
                "is_internal": "false",
                "url_builder": "false",
                "order": "100",
                "app_scope": scope,
            },
            names.sn_connection,
        )
        # The sys_wdf_external_connection_mapping row is created by a business rule when the
        # connection is saved. Verify rather than insert, or you get a duplicate.
        mapping = snow.get(
            f"/api/now/table/sys_wdf_external_connection_mapping"
            f"?sysparm_query=asset_id={alias_id}^table_name=sys_alias&sysparm_fields=sys_id&sysparm_limit=5"
        )
        count = len(mapping.get("result", []))
        self.note(
            f"connection mapping rows for this alias: {count}"
            + ("" if count else "  <-- expected 1; the alias has no child connection")
        )
        insert(
            self.args.route_table,
            {
                "team_code": names.code,
                "assignment_group": names.group,
                "event_stream_name": names.stream,
                "event_stream_uuid": uuid,
                "connection_alias": alias_id,
                "active": "true",
            },
            names.code,
            key="team_code",
        )

    # -- destroy ----------------------------------------------------------------------------

    def sn_scope_sys_id(self, snow: Http) -> str:
        """Resolve the scoped application's sys_scope sys_id from the route table's scope prefix.

        The alias, credential and connection all have to land inside the application; a record
        created without it goes to global and the flow's pill will not resolve it.
        """
        prefix = self.args.route_table.split("_eda_team_route")[0]
        found = snow.get(
            f"/api/now/table/sys_scope?sysparm_query=scope={urllib.parse.quote(prefix)}"
            "&sysparm_fields=sys_id,scope,name&sysparm_limit=1"
        )
        rows = found.get("result", [])
        if not rows:
            raise RuntimeError(
                f"no sys_scope with scope={prefix!r}. Pass --route-table matching your scoped app, "
                "or the records would be created in global."
            )
        return rows[0]["sys_id"]

    def destroy(self) -> int:
        entries = list(reversed(self.manifest.data.get("created", [])))
        if not entries:
            print(f"nothing recorded in {self.manifest.path}; nothing to remove.")
            return 0
        print(f"\n{len(entries)} object(s) recorded for {self.names.code}, newest first:\n")
        for entry in entries:
            print(f"    {entry['kind']:<22} {entry['name']:<38} id={entry['id']}")
        if not self.apply:
            print("\ndry run -- re-run with --apply to delete these.")
            return 0
        host = os.environ["SN_PDI_HOST"].rstrip("/")
        cred = base64.b64encode(
            f"{os.environ['SN_PDI_PROVISION_USERNAME']}:{os.environ['SN_PDI_PROVISION_PASSWORD']}".encode()
        ).decode()
        snow = Http(host, {"Authorization": f"Basic {cred}"})
        # Teardown is not instantaneous: deleting an activation returns success while the pod is
        # still being reaped, and for a few seconds afterwards its event stream, credentials and
        # decision environment all refuse deletion with 409 "is being referenced by...". So make
        # several passes, retrying only what is still blocked, rather than declaring failure on the
        # first attempt. Order alone cannot fix this -- the dependency is released asynchronously.
        remaining = entries
        for attempt in range(4):
            if not remaining:
                break
            if attempt:
                print(f"\n    retrying {len(remaining)} blocked deletion(s) after 15s...")
                time.sleep(15)
            remaining = self._delete_pass(remaining, snow)
        failures = len(remaining)
        if not failures:
            os.remove(self.manifest.path)
            print(f"\nall removed; manifest {self.manifest.path} deleted.")
        else:
            self.manifest.data["created"] = list(reversed(remaining))
            self.manifest.save()
            print(f"\n{failures} deletion(s) still failing; manifest kept with just those.")
        return 1 if failures else 0

    def _delete_pass(self, entries: list[dict], snow: Http) -> list[dict]:
        """Attempt each deletion once. Returns the entries that are still present."""
        blocked: list[dict] = []
        print()
        for entry in entries:
            is_snow = str(entry["kind"]).startswith("sn:")
            client = snow if is_snow else self.aap
            if is_snow:
                path = f"{entry['endpoint']}/{entry['id']}"
            else:
                # The trailing slash is required. Without it the EDA and gateway APIs answer a
                # DELETE with 301 to the slash-terminated URL, and urllib does not re-issue the
                # DELETE across a redirect -- so the object silently survives. The controller API
                # tolerates the omission, which is exactly why this looked fine until a gateway or
                # EDA object was in the manifest.
                path = f"{entry['endpoint'].rstrip('/')}/{entry['id']}/"
            status, body = client.call("DELETE", path)
            if status in (200, 202, 204):
                print(f"    deleted {entry['kind']:<20} {entry['name']}")
            elif status == 404:
                # Already gone -- a partial destroy that is retried, or someone removed it in the
                # UI. The desired end state is reached either way, so this is success. Treating it
                # as a failure keeps the manifest forever and makes a clean run impossible.
                print(f"    absent  {entry['kind']:<20} {entry['name']} (already deleted)")
            elif status == 409:
                blocked.append(entry)
                print(f"    blocked {entry['kind']:<20} {entry['name']} (still referenced)")
            else:
                blocked.append(entry)
                print(f"    FAILED  {entry['kind']:<20} {entry['name']} -> {status}: {str(body)[:120]}")
        return blocked


def explain_missing_env(missing: list[str]) -> None:
    """Delegate to verify_team.py's table so the guidance cannot drift between the two scripts."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        from verify_team import explain_missing_env as explain  # noqa: PLC0415

        explain(missing)
    except ImportError:
        print(f"error: missing environment: {', '.join(missing)}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="Provision one team's EDA objects.")
    parser.add_argument("--team", required=True, help="team code, e.g. team-d")
    parser.add_argument("--gateway", default=os.environ.get("AAP_GATEWAY", ""))
    parser.add_argument("--repo-url", default=REPO_URL)
    parser.add_argument("--branch", default=DEFAULT_BRANCH)
    parser.add_argument("--template", default="a", help="team letter to render the rulebook from")
    parser.add_argument("--route-table", default=os.environ.get("SN_ROUTE_TABLE", "x_661661_james_tes_eda_team_route"))
    parser.add_argument("--repo-root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    parser.add_argument("--apply", action="store_true", help="actually write (default is dry run)")
    parser.add_argument("--render-rulebook", action="store_true", help="phase A only: render and stop")
    parser.add_argument("--force-render", action="store_true", help="overwrite an existing rulebook")
    parser.add_argument("--no-activate", action="store_true", help="skip creating the activation pod")
    parser.add_argument("--aap-only", action="store_true", help="skip the ServiceNow section entirely")
    parser.add_argument("--servicenow-apply", action="store_true", help="attempt the ServiceNow inserts")
    parser.add_argument(
        "--retry-policy",
        default="ef751ff07301330025d71afe2ff6a7f9",
        help="sys_retry_policy sys_id for the alias (default: Default HTTP Retry Policy)",
    )
    parser.add_argument("--destroy", action="store_true", help="remove what the manifest records")
    args = parser.parse_args()

    try:
        names = Names(args.team)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    needed = ["SANDBOX_AAP_PAT_TOKEN", "SN_PDI_HOST", "SN_PDI_PROVISION_USERNAME", "SN_PDI_PROVISION_PASSWORD"]
    missing = [v for v in needed if not os.environ.get(v)] + ([] if args.gateway else ["AAP_GATEWAY"])
    if missing:
        explain_missing_env(missing)
        return 2

    provisioner = Provisioner(args, names)
    mode = "APPLY -- writes are real" if args.apply else "DRY RUN -- nothing will be written"
    print(f"\n{names.code}  ({names.org})   \033[1m{mode}\033[0m")

    if args.destroy:
        return provisioner.destroy()

    try:
        provisioner.step("Phase A  rulebook")
        provisioner.render_rulebook()
        if args.render_rulebook:
            print(f"\nNow commit and push {names.rulebook_path}, then re-run without --render-rulebook.\n")
            return 0
        rulebook_sha = provisioner.require_pushed()
        provisioner.build_aap(rulebook_sha)
        if not args.aap_only:
            provisioner.servicenow()
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 - report, do not traceback at the user
        print(f"\n\033[31mfailed:\033[0m {exc}\n", file=sys.stderr)
        print(f"Manifest kept at {provisioner.manifest.path}; re-run to resume, or --destroy.", file=sys.stderr)
        return 1

    print(f"\nNext: python3 scripts/verify_team.py --team {names.code}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
