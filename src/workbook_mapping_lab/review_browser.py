"""Local-only browser review desk over the existing accountant-reviewed engine.

No cloud, login, network binding, telemetry, client-data upload, or external API.
The browser is a presentation layer; all workbook/approval rules are reused.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import secrets
import socket
import threading
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .advisories import (advisory, check_advisories, evaluate_evidence_rules,
                         load_evidence_rules, evidence_digest, warning_review_key)
from .fs_extract import extract_profile, load_profile, scan_sheet
from .layout_resolver import resolve_layout, merge_approved_routes, write_private_layout
from .learning import propose_mappings
from .mapping import load_csv
from .pipeline import controlled_build
from .review import ReviewSession, require_private_directory
from .simulator import WorkbookSnapshot
from .template_contract import detail_coverage
from .manual_benchmark import compare_completed_return
from .import_intake import inspect_native_import_coverage
from .export_preflight import preflight_export
from .entity_schema import (load_entity_profile, inspect_entity_profile,
                            require_approved_entity_schema)
from .schema_discovery import (discover_entity_fields, set_candidate_decision,
                               reviewed_profile, save_private_profile)
from .warning_journal import save_journal, load_journal, reviewed_identity

CONFIG_KEYS = frozenset((
    "source", "previous", "profile", "layout", "prior_rules",
    "previous_target", "folder", "source_controls", "output_controls",
    "template", "output", "detail_routes", "companion_details", "advisory_rules",
    "benchmark_generated", "completed_reference", "benchmark_contract",
    "entity_schema_profile", "entity_key", "assessment_year", "itr_form",
    "intake_template",
))
STATIC = {
    "/": ("review_browser.html", "text/html; charset=utf-8"),
    "/app.css": ("review_browser.css", "text/css; charset=utf-8"),
    "/app.js": ("review_browser.js", "text/javascript; charset=utf-8"),
    "/zoom.js": ("review_browser_zoom.js", "text/javascript; charset=utf-8"),
}


class Workspace:
    def __init__(self, session: str | None = None):
        self.config = {key: "" for key in CONFIG_KEYS}
        if session:
            data = json.loads(Path(session).read_text(encoding="utf-8-sig"))
            if not isinstance(data, dict) or data.get("version") != 1:
                raise ValueError("Invalid private session file")
            for key, value in data.get("paths", {}).items():
                if key in CONFIG_KEYS and isinstance(value, str):
                    self.config[key] = value
        self.review: ReviewSession | None = None
        self.issues: list[dict] = []
        self.warnings: list[dict] = []
        self.decisions: dict[str, dict] = {}
        self._warning_evidence_signature = ""
        self.latest_saved: dict | None = None
        self.latest_benchmark: dict | None = None
        self.latest_preflight: dict | None = None
        self.latest_entity_schema: dict | None = None
        self.latest_import_intake: dict | None = None
        self.entity_discovery: dict | None = None
        self.profile = None
        self.lock = threading.RLock()

    def file(self, key: str, required: bool = True) -> str:
        value = self.config[key].strip()
        if required and not value:
            raise ValueError("Select " + key.replace("_", " "))
        return value

    def data(self) -> dict:
        return {
            "config": dict(self.config),
            "entries": list(self.review.entries.values()) if self.review else [],
            "fields": list(self.review.layout.values()) if self.review else [],
            "warnings": [
                dict(item, **self.decisions.get(self.warning_key(item), {}))
                for item in self.warnings
            ],
            "issues": self.issues,
            "unresolved": self.review.unresolved() if self.review else [],
            "latest_saved": self.latest_saved,
            "latest_benchmark": self.latest_benchmark,
            "latest_preflight": self.latest_preflight,
            "latest_entity_schema": self.latest_entity_schema,
            "latest_import_intake": self.latest_import_intake,
            "entity_discovery": self.entity_discovery,
        }

    def warning_key(self, item: dict) -> str:
        return warning_review_key(item, self._warning_evidence_signature)

    def set_config(self, updates: dict) -> dict:
        if not isinstance(updates, dict) or any(key not in CONFIG_KEYS for key in updates):
            raise ValueError("Unrecognised configuration field")
        if any(not isinstance(value, str) or len(value) > 4096 for value in updates.values()):
            raise ValueError("Invalid path field")
        changed = {key for key, value in updates.items()
                   if self.config[key] != value.strip()}
        self.config.update({key: value.strip() for key, value in updates.items()})
        if changed.intersection({
            "source", "previous", "profile", "layout", "prior_rules", "previous_target"
        }):
            self.review = None
            self.profile = None
            self.issues = []
        if changed.intersection({
            "source", "previous", "previous_target", "advisory_rules",
            "entity_key", "assessment_year", "itr_form"
        }):
            # A decision must never silently follow another entity or a
            # newly selected set of evidence workbooks.
            self.decisions.clear()
            self.warnings = []
            self._warning_evidence_signature = ""
        if changed.intersection({"template", "layout", "entity_key", "assessment_year", "itr_form"}):
            self.entity_discovery = None
        if changed:
            self.latest_saved = None
            self.latest_benchmark = None
            self.latest_preflight = None
            self.latest_entity_schema = None
            self.latest_import_intake = None
        return self.data()

    def refresh_warnings(self) -> dict:
        try:
            signature = evidence_digest({
                "previous_fs": self.file("previous", False),
                "previous_return": self.file("previous_target", False),
                "current_fs": self.file("source", False),
                "additional_rules": self.file("advisory_rules", False),
            })
            if signature != self._warning_evidence_signature:
                self.decisions.clear()
            self._warning_evidence_signature = signature
            notes = check_advisories(self.file("previous", False),
                                     self.file("previous_target", False),
                                     self.file("source", False) or None)
            if self.file("advisory_rules", False):
                custom = load_evidence_rules(self.file("advisory_rules"))
                notes += evaluate_evidence_rules({
                    "previous_fs": self.file("previous", False),
                    "previous_return": self.file("previous_target", False),
                    "current_fs": self.file("source", False),
                }, custom)
            self.warnings = notes
        except (OSError, ValueError, KeyError) as e:
            self.decisions.clear()
            self._warning_evidence_signature = ""
            self.warnings = [advisory(
                "EVIDENCE_CHECK_INCOMPLETE",
                "Evidence could not be checked",
                str(e),
                "Review the provided files and their year/sheet labels.",
                severity="Info",
            )]
        # Even with unchanged files, changed rule interpretation must never
        # retain a decision for a warning that disappeared and later returned.
        active = {self.warning_key(item) for item in self.warnings}
        self.decisions = {key: value for key, value in self.decisions.items()
                          if key in active}
        return self.data()

    def extract(self) -> dict:
        profile = load_profile(self.file("profile"))
        fields = load_csv(self.file("layout"),
                          ("field_id", "section", "sheet", "cell",
                           "anchor_cell", "anchor_text"))
        prior = (load_csv(self.file("prior_rules"),
                          ("source_id", "field_id", "approved"))
                 if self.file("prior_rules", False) else [])
        rows, issues = extract_profile(self.file("source"), profile,
                     previous_workbook_path=self.file("previous", False) or None)
        if self.file("previous_target", False) and self.file("template", False):
            contract = detail_coverage(self.file("previous_target"),
                                       self.file("template"))
            for sheet in contract["missing_active_detail_sheets"]:
                issues.append({
                    "issue": "VENDOR_TEMPLATE_DETAIL_MISSING",
                    "source_id": "",
                    "detail": sheet["sheet"] + ": export this detailed schedule from the application",
                })
        proposals = []
        if self.file("previous_target", False):
            proposals, prior_issues = propose_mappings(
                rows, self.file("previous_target"), fields)
            # Distinguish historical suggestions from structural blockers.
            # Historical lookup misses are optional hints, not structural blockers.
            # Proposed mappings still require explicit human confirmation.
        self.profile = profile
        self.issues = issues
        self.review = ReviewSession(rows, issues, fields, prior,
                                    suggestions=proposals)
        self.latest_saved = None
        self.refresh_warnings()
        return self.data()

    def approve(self, args: dict) -> dict:
        if not self.review:
            raise ValueError("Extract financial-statement rows first")
        sid = str(args.get("source_id", ""))
        fid = str(args.get("field_id", ""))
        self.review.approve(
            sid, fid, portion=str(args.get("portion", "1")),
            sign=str(args.get("sign", "keep")),
            acknowledge_risks=args.get("acknowledge_risks") is True,
        )
        self.latest_saved = None
        return self.data()

    def revoke(self, args: dict) -> dict:
        if not self.review:
            raise ValueError("No active review")
        self.review.revoke(str(args.get("source_id", "")))
        self.latest_saved = None
        return self.data()

    def warning_decision(self, args: dict) -> dict:
        index = args.get("index")
        if not isinstance(index, int) or not 0 <= index < len(self.warnings):
            raise ValueError("Select a valid warning")
        item = self.warnings[index]
        self.decisions[self.warning_key(item)] = {
            "acknowledged": args.get("acknowledged") is True,
            "reviewer_note": str(args.get("note", ""))[:600],
        }
        return self.data()

    def _new_file(self, prefix: str, suffix: str) -> Path:
        private = require_private_directory(self.file("folder"))
        return private / (prefix + datetime.now().strftime("%Y%m%d_%H%M%S_%f") + suffix)

    def export_warnings(self) -> dict:
        path = self._new_file("advisory_warnings_PRIVATE_", ".json")
        if path.exists():
            raise FileExistsError("Cannot replace prior warnings report")
        records = [
            dict(w, **self.decisions.get(self.warning_key(w), {}))
            for w in self.warnings
        ]
        path.write_text(json.dumps({
            "purpose": "Non-blocking evidence warnings",
            "evidence_sha256": self._warning_evidence_signature,
            "warnings": records,
        }, indent=2), encoding="utf-8")
        return {"path": str(path), "count": len(records)}

    def save_warning_journal(self) -> dict:
        """Save explicit non-blocking decisions only to the private folder."""
        identity = reviewed_identity(self.config)
        self.refresh_warnings()
        result = save_journal(self.file("folder"), identity,
                              self._warning_evidence_signature,
                              self.warnings, self.decisions)
        return {"journal": result, **self.data()}

    def load_warning_journal(self, args: dict) -> dict:
        """Fail closed on any source/identity/warning mismatch; no auto-build."""
        identity = reviewed_identity(self.config)
        journal_path = args.get("path", "")
        if not isinstance(journal_path, str) or not journal_path.strip():
            raise ValueError("Select the private warning review journal JSON")
        self.refresh_warnings()
        restored = load_journal(journal_path, self.file("folder"), identity,
                                self._warning_evidence_signature, self.warnings)
        self.decisions = restored
        return {"journal": {"loaded_count": len(restored)}, **self.data()}

    def save_review(self) -> dict:
        if not self.review:
            raise ValueError("Extract financial statements before saving")
        prefix = "browser_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self.latest_saved = self.review.save_review(self.file("folder"), prefix=prefix)
        return {"result": self.latest_saved, **self.data()}

    def resolve_details(self) -> dict:
        template = self.file("template")
        if self.file("previous_target", False):
            contract = detail_coverage(self.file("previous_target"), template)
            if contract["status"] != "READY_FOR_REVIEW":
                absent = ", ".join(x["sheet"] for x in contract["missing_active_detail_sheets"])
                raise ValueError("Official export lacks required detail schedules: " + absent)
        routes = load_csv(self.file("detail_routes"),
                          ("field_id", "section", "sheet", "caption"))
        old_layout = load_csv(self.file("layout"),
                              ("field_id", "section", "sheet", "cell",
                               "anchor_cell", "anchor_text"))
        resolved = resolve_layout(template, routes)
        if resolved["status"] != "READY":
            problems = "; ".join(x["field_id"] + ": " + x["code"]
                                for x in resolved["exceptions"])
            raise ValueError("Cannot safely find detailed fields: " + problems)
        result = merge_approved_routes(old_layout, resolved)
        dest = self._new_file("vendor_resolved_layout_PRIVATE_", ".csv")
        write_private_layout(result, str(dest))
        self.config["layout"] = str(dest)
        self.review = None
        self.latest_saved = None
        return {"path": str(dest), **self.data()}

    def scan(self, args: dict) -> dict:
        sheet = str(args.get("sheet", ""))
        first, last = int(args.get("first", 1)), int(args.get("last", 350))
        if first < 1 or last < first or last > 2000:
            raise ValueError("Choose a valid range between rows 1 and 2000")
        with WorkbookSnapshot(self.file("source")) as w:
            return {"rows": scan_sheet(w, sheet, start_row=first, end_row=last)}

    def check_template_readiness(self) -> dict:
        """Read-only validation of native export and configured detail slots."""
        self.latest_preflight = preflight_export(
            self.file("template"),
            self.file("previous_target", False),
            self.file("detail_routes", False),
        )
        return self.data()

    def check_native_import_intake(self) -> dict:
        """Read-only 13-field-style import target and completed return comparison."""
        template = self.file("intake_template", False) or self.file("template")
        result = inspect_native_import_coverage(
            template, self.file("completed_reference"),
            self.file("benchmark_contract"),
        )
        private = self._new_file("native_import_coverage_PRIVATE_", ".json")
        with private.open("x", encoding="utf-8") as out:
            json.dump(result, out, indent=2, ensure_ascii=False)
        self.latest_import_intake = {
            "status": result["status"],
            "field_count": result["field_count"],
            "import_cells_available": result["import_cells_available"],
            "import_cells_unavailable": result["import_cells_unavailable"],
            "reference_mismatches": result["reference_mismatches"],
            "ready_for_accountant_review": result["ready_for_accountant_review"],
            "rows": result["rows"],
            "private_report": str(private),
        }
        return self.data()

    def benchmark_completed(self) -> dict:
        """Independent reference check with no workbook writes or approvals."""
        selected = self.file("benchmark_generated", False) or self.file("output")
        reference = self.file("completed_reference")
        contract = self.file("benchmark_contract")
        result = compare_completed_return(selected, reference, contract)
        report = self._new_file("completed_return_benchmark_PRIVATE_", ".json")
        if report.exists():
            raise FileExistsError("Benchmark report already exists")
        report.write_text(json.dumps(result,indent=2),encoding="utf-8")
        self.latest_benchmark = {
            "status":result["status"], "contract_fields":result["contract_fields"],
            "fully_matched":result["fully_matched"],
            "review_count":result["require_review"],
            "unavailable_targets":result["generated_target_unavailable"],
            "details":result["details"], "private_report":str(report),
        }
        return self.data()

    def discover_entity_candidates(self) -> dict:
        """Read-only native workbook scan; no applicability guessed."""
        self.entity_discovery = discover_entity_fields(
            self.file("template"), self.file("layout", False),
        )
        self.latest_entity_schema = None
        return self.data()

    def review_entity_candidate(self, request: dict) -> dict:
        if not self.entity_discovery:
            raise ValueError("Scan the current-year export first")
        set_candidate_decision(
            self.entity_discovery,
            candidate_id=str(request.get("candidate_id", "")),
            selected=request.get("selected"),
            field_id=str(request.get("field_id", "")),
            section=str(request.get("section", "")),
            applicability=str(request.get("applicability", "review")),
        )
        return self.data()

    def export_entity_candidate_profile(self) -> dict:
        if not self.entity_discovery:
            raise ValueError("Scan the current-year export first")
        profile = reviewed_profile(
            self.entity_discovery,
            entity_key=self.file("entity_key"),
            assessment_year=self.file("assessment_year"),
            itr_form=self.file("itr_form"),
            native_template=self.file("template"),
            layout_path=self.file("layout", False),
        )
        destination = self._new_file("entity_schema_reviewed_PRIVATE_", ".json")
        saved = save_private_profile(profile, str(destination))
        self.config["entity_schema_profile"] = saved
        self.latest_entity_schema = inspect_entity_profile(
            self.file("template"), profile,
            expected_entity_key=self.file("entity_key"),
            expected_assessment_year=self.file("assessment_year"),
            expected_itr_form=self.file("itr_form"),
        )
        return {"path": saved, **self.data()}

    def check_entity_schema(self) -> dict:
        """Fail closed: validate identity, exact workbook, and approved layout."""
        profile = load_entity_profile(self.file("entity_schema_profile"))
        result = inspect_entity_profile(
            self.file("template"), profile,
            expected_entity_key=self.file("entity_key"),
            expected_assessment_year=self.file("assessment_year"),
            expected_itr_form=self.file("itr_form"),
        )
        self.latest_entity_schema = result
        return self.data()

    def _require_entity_schema_for_build(self) -> None:
        # Re-evaluate the exact template, profile and approved layout on build.
        self.latest_entity_schema = require_approved_entity_schema(
            template=self.file("template"), layout=self.file("layout"),
            profile_path=self.file("entity_schema_profile"),
            expected_entity_key=self.file("entity_key"),
            expected_assessment_year=self.file("assessment_year"),
            expected_itr_form=self.file("itr_form"),
        )

    def build(self) -> dict:
        if not self.review or self.review.unresolved():
            raise ValueError("All source classifications require approval before building")
        if not self.latest_saved or self.latest_saved["status"] != "PASS":
            raise ValueError("Export a PASS mapping review before building")
        self._require_entity_schema_for_build()
        report = self._new_file("browser_build_exceptions_PRIVATE_", ".json")
        result = controlled_build(
            source=self.latest_saved["sources"],
            rules=self.latest_saved["rules"],
            layout=self.file("layout"),
            template=self.file("template"),
            source_controls=self.file("source_controls"),
            output_controls=self.file("output_controls"),
            output=self.file("output"),
            exception_report=str(report),
            rounding="whole_rupees",
            previous_export=self.file("previous_target", False) or None,
            companion_details=self.file("companion_details", False) or None,
        )
        return {"result": result, "report": str(report), **self.data()}


def create_server(workspace: Workspace, *, port: int = 0):
    token = secrets.token_urlsafe(32)
    base = Path(__file__).resolve().parent
    allowed_actions = {
        "/api/config": workspace.set_config,
        "/api/extract": lambda _: workspace.extract(),
        "/api/warnings": lambda _: workspace.refresh_warnings(),
        "/api/warning-decision": workspace.warning_decision,
        "/api/warnings-export": lambda _: workspace.export_warnings(),
        "/api/warnings-journal-save": lambda _: workspace.save_warning_journal(),
        "/api/warnings-journal-load": workspace.load_warning_journal,
        "/api/approve": workspace.approve,
        "/api/revoke": workspace.revoke,
        "/api/save-review": lambda _: workspace.save_review(),
        "/api/build": lambda _: workspace.build(),
        "/api/benchmark-completed": lambda _: workspace.benchmark_completed(),
        "/api/native-import-intake": lambda _: workspace.check_native_import_intake(),
        "/api/template-readiness": lambda _: workspace.check_template_readiness(),
        "/api/entity-schema-check": lambda _: workspace.check_entity_schema(),
        "/api/entity-discover": lambda _: workspace.discover_entity_candidates(),
        "/api/entity-review-candidate": workspace.review_entity_candidate,
        "/api/entity-export-profile": lambda _: workspace.export_entity_candidate_profile(),
        "/api/resolve-details": lambda _: workspace.resolve_details(),
        "/api/scan": workspace.scan,
    }

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "LocalWorkbookReview/1.0"

        def log_message(self, *_):
            # Avoid client names or private file paths in server logs.
            pass

        def _safe_host(self):
            host = self.headers.get("Host", "")
            return host in (f"127.0.0.1:{self.server.server_port}",
                            f"localhost:{self.server.server_port}")

        def _reply(self, status: int, data: bytes, content_type="application/json; charset=utf-8"):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy",
                             "default-src 'self'; script-src 'self'; style-src 'self'; "
                             "connect-src 'self'; img-src 'self' data:; object-src 'none'; "
                             "base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(data)

        def _json(self, status: int, payload):
            raw = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
            self._reply(status, raw)

        def do_GET(self):
            if not self._safe_host():
                return self._json(403, {"error": "Loopback host required"})
            uri = urlsplit(self.path).path
            if uri == "/api/state":
                if self.headers.get("X-Session-Token", "") != token:
                    return self._json(403, {"error": "Invalid session"})
                with workspace.lock:
                    return self._json(200, workspace.data())
            if uri not in STATIC:
                return self._json(404, {"error": "Page not found"})
            filename, mime = STATIC[uri]
            data = (base / filename).read_bytes()
            if uri == "/":
                data = data.replace(b"__LOCAL_SESSION_TOKEN__", token.encode("ascii"))
            return self._reply(200, data, mime)

        def do_POST(self):
            if not self._safe_host():
                return self._json(403, {"error": "Loopback host required"})
            if self.headers.get("X-Session-Token", "") != token:
                return self._json(403, {"error": "Invalid session"})
            origin = self.headers.get("Origin")
            expected = (f"http://127.0.0.1:{self.server.server_port}",
                        f"http://localhost:{self.server.server_port}")
            if origin and origin not in expected:
                return self._json(403, {"error": "Cross-site request blocked"})
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                return self._json(415, {"error": "JSON request required"})
            path = urlsplit(self.path).path
            if path not in allowed_actions:
                return self._json(404, {"error": "Action not found"})
            try:
                size = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                return self._json(400, {"error": "Invalid message length"})
            if size < 2 or size > 262144:
                return self._json(413, {"error": "Request exceeds local limit"})
            try:
                args = json.loads(self.rfile.read(size))
                if not isinstance(args, dict):
                    raise ValueError("Request requires an object")
                with workspace.lock:
                    result = allowed_actions[path](args)
                return self._json(200, {"ok": True, "data": result})
            except (ValueError, OSError, KeyError, TypeError) as error:
                return self._json(422, {"ok": False, "error": str(error)})
            except Exception:
                # Never leak tracebacks or private paths into response.
                return self._json(500, {"ok": False, "error": "Internal local application error"})

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server



def open_local_chrome(url: str) -> str:
    """Use installed Chrome when available; fall back to the system browser."""
    candidates = []
    for base in (
        os.environ.get("PROGRAMFILES", ""),
        os.environ.get("PROGRAMFILES(X86)", ""),
        os.environ.get("LOCALAPPDATA", ""),
    ):
        if base:
            candidates.append(Path(base) / "Google" / "Chrome" /
                              "Application" / "chrome.exe")
    for executable in candidates:
        if executable.is_file():
            subprocess.Popen([str(executable), "--new-tab", url],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, close_fds=True)
            return "Chrome"
    webbrowser.open(url)
    return "Default browser"


def main():
    parser = argparse.ArgumentParser(description="Private local browser UI for reviewed workbook mappings")
    parser.add_argument("--session", help="Private local paths JSON")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    if args.port < 0 or args.port > 65535:
        parser.error("Port out of range")
    workspace = Workspace(args.session)
    server = create_server(workspace, port=args.port)
    url = f"http://127.0.0.1:{server.server_port}/"
    print("Workbook Mapping Lab is running locally:", url, flush=True)
    if not args.no_browser:
        open_local_chrome(url)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

