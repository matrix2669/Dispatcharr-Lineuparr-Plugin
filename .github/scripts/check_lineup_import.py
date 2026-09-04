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
    """Exercise the actual action methods without requiring a Django install."""
    source = ROOT / "Lineuparr" / "plugin.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    plugin = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Plugin")
    methods = [n for n in plugin.body if isinstance(n, ast.FunctionDef)
               and n.name in {"_import_generated_lineup", "_select_imported_lineup"}]
    assert len(methods) == 2
    namespace = {
        "__file__": str(source), "os": os, "transaction": SimpleNamespace(atomic=nullcontext),
        "PluginConfig": SimpleNamespace(PERSISTENT_LINEUPS_DIR="/unused", PERSISTENT_LINEUP_PREFIX="persistent:"),
        "LOG_PREFIX": "test", "LineupImportError": LineupImportError,
        "displayed_action_error": lambda message, **kw: dict(status="error", message=message, **kw),
    }
    exec(compile(ast.Module(body=methods, type_ignores=[]), str(source), "exec"), namespace)
    action = namespace["_import_generated_lineup"]
    select = namespace["_select_imported_lineup"]
    old = {"lineup_file": "old.json", "match_sensitivity": "relaxed", "unrelated": True}
    for operation in ("created", "refreshed"):
        config = SimpleNamespace(settings=dict(old), save=Mock())
        manager = Mock()
        manager.select_for_update.return_value.get.return_value = config
        model = SimpleNamespace(PluginConfig=SimpleNamespace(objects=manager))
        instance = SimpleNamespace()
        instance._select_imported_lineup = lambda value: select(instance, value)
        namespace["import_generated_lineup"] = Mock(return_value={
            "filename": "US_Test_lineup.json", "operation": operation,
            "package": "Test", "channels": 1, "categories": 1,
        })
        settings = dict(old)
        with patch.dict(sys.modules, {"apps.plugins.models": model}):
            result = action(instance, settings, Mock())
        expected = dict(old, lineup_file="persistent:US_Test_lineup.json", match_sensitivity="exact")
        assert config.settings == settings == expected
        config.save.assert_called_once_with(update_fields=["settings", "updated_at"])
        manager.select_for_update.return_value.get.assert_called_once_with(key="lineuparr")
        assert result["status"] == "ok" and "Exact" in result["message"]

    namespace["import_generated_lineup"] = Mock(side_effect=LineupImportError("Invalid lineup"))
    instance = SimpleNamespace(_select_imported_lineup=Mock())
    settings = dict(old)
    assert action(instance, settings, Mock())["status"] == "error"
    assert settings == old
    instance._select_imported_lineup.assert_not_called()

    namespace["import_generated_lineup"] = Mock(return_value={
        "filename": "US_Test_lineup.json", "operation": "refreshed",
    })
    instance._select_imported_lineup = Mock(side_effect=RuntimeError("save failed"))
    result = action(instance, settings, Mock())
    assert result["status"] == "error" and result["operation"] == "refreshed"
    assert "Exact" in result["message"] and settings == old

    manifest = json.loads((ROOT / "Lineuparr" / "plugin.json").read_text(encoding="utf-8"))
    confirm = next(a for a in manifest["actions"] if a["id"] == "import_generated_lineup")["confirm"]
    assert "Match Sensitivity" in confirm["message"] and "Exact" in confirm["message"]


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
