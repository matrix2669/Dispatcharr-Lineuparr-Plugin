#!/usr/bin/env python3
"""Offline regression checks for generated lineup URL imports."""

import ast
import io
import json
import os
import sys
import tempfile
from contextlib import nullcontext
from email.message import Message
from pathlib import Path
from types import SimpleNamespace
from urllib.error import URLError
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "Lineuparr"))

from lineup_import import LineupImportError, import_generated_lineup  # noqa: E402


class FakeResponse:
    def __init__(self, payload, url, filename=None):
        self._body = io.BytesIO(payload)
        self._url = url
        self.status = 200
        self.headers = Message()
        self.headers["Content-Length"] = str(len(payload))
        if filename:
            self.headers["Content-Disposition"] = f'attachment; filename="{filename}"'

    def read(self, size=-1):
        return self._body.read(size)

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


def opener_for(payload, filename=None, final_url="http://gracenotescraper/export"):
    def open_response(request, timeout):
        assert request.full_url == "http://gracenotescraper/api/lineuparr/export"
        assert timeout == 30
        return FakeResponse(payload, final_url, filename)
    return open_response


def lineup(package="Test Cable", channel="Test Network"):
    return json.dumps({
        "package": package,
        "date": "2026-09-04",
        "categories": {
            "Entertainment": [{"name": channel, "number": 10, "aliases": ["TEST"]}],
        },
    }).encode("utf-8")


def require_raises(callable_):
    try:
        callable_()
    except LineupImportError:
        return
    raise AssertionError("expected LineupImportError")


def captured_error(callable_):
    try:
        callable_()
    except LineupImportError as exc:
        return str(exc)
    raise AssertionError("expected LineupImportError")


def check_import_settings():
    """Exercise the real action boundary with a stale-but-stable UI selection."""
    from lineup_import import current_import_filename
    source = ROOT / "Lineuparr" / "plugin.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    plugin = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Plugin")
    methods = [n for n in plugin.body if isinstance(n, ast.FunctionDef)
               and n.name in {"_import_generated_lineup", "_effective_lineup_settings", "run"}]
    assert len(methods) == 3
    with tempfile.TemporaryDirectory() as directory:
        namespace = {
            "__file__": str(source), "os": os,
            "PluginConfig": SimpleNamespace(PERSISTENT_LINEUPS_DIR=directory,
                PERSISTENT_LINEUP_PREFIX="persistent:", URL_LINEUP_VALUE="url:latest"),
            "LOG_PREFIX": "test", "LOGGER": Mock(), "LineupImportError": LineupImportError,
            "current_import_filename": current_import_filename,
            "result_text": lambda result: str(result),
            "displayed_action_error": lambda message, **kw: dict(status="error", message=message, **kw),
        }
        exec(compile(ast.Module(body=methods, type_ignores=[]), str(source), "exec"), namespace)
        instance = SimpleNamespace()
        for method in methods:
            setattr(instance, method.name, namespace[method.name].__get__(instance))
        # Dispatcharr repeatedly sends the same settings, including its old sensitivity.
        settings = {"lineup_file": "url:latest", "match_sensitivity": "normal", "unrelated": True}
        original = dict(settings)
        require_raises(lambda: instance._effective_lineup_settings(settings))
        for name, operation in [("US_Test_lineup.json", "created"),
                                ("US_Test_lineup.json", "refreshed"),
                                ("CA_Other_lineup.json", "created")]:
            namespace["import_generated_lineup"] = lambda url, dest: import_generated_lineup(
                "http://gracenotescraper/api/lineuparr/export", dest,
                opener=opener_for(lineup(), name))
            result = instance._import_generated_lineup(settings, Mock())
            assert result["status"] == "ok" and result["operation"] == operation
            effective = instance._effective_lineup_settings(settings)
            assert effective == dict(original, lineup_file="persistent:" + name, match_sensitivity="exact")
            assert settings == original
        assert (Path(directory) / "US_Test_lineup.json").exists()
        # A fresh reader (process/restart) sees the last successful import.
        assert current_import_filename(directory) == "CA_Other_lineup.json"
        namespace["import_generated_lineup"] = Mock(side_effect=LineupImportError("Invalid lineup"))
        assert instance._import_generated_lineup(settings, Mock())["status"] == "error"
        assert current_import_filename(directory) == "CA_Other_lineup.json"
        manual = dict(settings, lineup_file="US_Manual_lineup.json", match_sensitivity="relaxed")
        assert instance._effective_lineup_settings(manual) == manual
        # Action routing must actually pass the effective selection to Preview.
        for name in ("_validate_settings", "_plugin_status", "_scan_lineups", "_preview_stream_match",
                     "_full_sync", "_sync_channels", "_apply_stream_match", "_apply_epg_match",
                     "_assign_logos", "_resort_streams", "_clear_csv_exports", "_email_report",
                     "_preview_groups", "_sync_groups", "_preview_channels"):
            setattr(instance, name, Mock(return_value={"status": "ok"}))
        # Bind every action-map handler from source, including legacy names.
        run_node = next(m for m in methods if m.name == "run")
        for node in ast.walk(run_node):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "self":
                if not hasattr(instance, node.attr):
                    setattr(instance, node.attr, Mock(return_value={"status": "ok"}))
        instance.run("preview_stream_match", {}, {"settings": settings, "logger": Mock()})
        args = instance._preview_stream_match.call_args.args
        assert args[0]["lineup_file"] == "persistent:CA_Other_lineup.json"
        assert args[0]["match_sensitivity"] == "exact" and settings == original
        # Malformed pointer cannot select paths outside persistent storage.
        (Path(directory) / ".current-url-import.json").write_text('{"filename":"../escape"}')
        require_raises(lambda: instance._effective_lineup_settings(settings))

    manifest = json.loads((ROOT / "Lineuparr" / "plugin.json").read_text(encoding="utf-8"))
    confirm = next(a for a in manifest["actions"] if a["id"] == "import_generated_lineup")["confirm"]
    assert "Lineup from URL" in confirm["message"] and "reload the plugin" in confirm["message"]


def main():
    check_import_settings()
    url = "http://gracenotescraper/api/lineuparr/export"
    with tempfile.TemporaryDirectory() as temp_dir:
        result = import_generated_lineup(
            url,
            temp_dir,
            opener=opener_for(lineup(), "US_Test-Cable_lineup.json"),
        )
        assert result["filename"] == "US_Test-Cable_lineup.json"
        assert result["channels"] == 1
        assert result["operation"] == "created"
        saved = json.loads((Path(temp_dir) / result["filename"]).read_text(encoding="utf-8"))
        assert saved["package"] == "Test Cable"

        refreshed = import_generated_lineup(
            url,
            temp_dir,
            opener=opener_for(lineup("Updated Cable", "Updated Network"), "US_Test-Cable_lineup.json"),
        )
        assert refreshed["filename"] == "US_Test-Cable_lineup.json"
        assert refreshed["operation"] == "refreshed"
        saved = json.loads((Path(temp_dir) / result["filename"]).read_text(encoding="utf-8"))
        assert saved["package"] == "Updated Cable"

        additional = import_generated_lineup(
            url,
            temp_dir,
            opener=opener_for(lineup("Other Cable", "Other Network"), "US_Other-Cable_lineup.json"),
        )
        assert additional["filename"] == "US_Other-Cable_lineup.json"
        assert additional["operation"] == "created"
        assert (Path(temp_dir) / "US_Test-Cable_lineup.json").exists()
        assert (Path(temp_dir) / "US_Other-Cable_lineup.json").exists()

    with tempfile.TemporaryDirectory() as temp_dir:
        result = import_generated_lineup(
            url,
            temp_dir,
            opener=opener_for(
                lineup(),
                final_url="http://gracenotescraper/generated/US_Path-Name_lineup.json",
            ),
        )
        assert result["filename"] == "US_Path-Name_lineup.json"

    require_raises(lambda: import_generated_lineup("file:///tmp/lineup.json", "/tmp"))
    assert captured_error(lambda: import_generated_lineup("", "/tmp")) == (
        "Generated Lineup URL is empty. Enter a URL and save settings before importing."
    )

    def unreachable(request, timeout):
        raise URLError("unreachable test host")

    assert captured_error(lambda: import_generated_lineup(
        url,
        "/tmp",
        opener=unreachable,
    )) == "The Generated Lineup URL is unreachable."
    require_raises(lambda: import_generated_lineup(
        url,
        "/tmp",
        opener=opener_for(b"not-json", "US_Bad_lineup.json"),
    ))
    require_raises(lambda: import_generated_lineup(
        url,
        "/tmp",
        opener=opener_for(json.dumps({"categories": {}}).encode(), "US_Empty_lineup.json"),
    ))
    duplicate = json.dumps({
        "categories": {
            "Entertainment": [
                {"name": "Duplicate", "number": 1},
                {"name": "Duplicate", "number": 2},
            ],
        },
    }).encode()
    require_raises(lambda: import_generated_lineup(
        url,
        "/tmp",
        opener=opener_for(duplicate, "US_Duplicate_lineup.json"),
    ))

    print("Generated lineup import checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
