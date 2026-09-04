#!/usr/bin/env python3
"""Offline regression checks for generated lineup URL imports."""

import io
import json
import sys
import tempfile
from email.message import Message
from pathlib import Path


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


def main():
    url = "http://gracenotescraper/api/lineuparr/export"
    with tempfile.TemporaryDirectory() as temp_dir:
        result = import_generated_lineup(
            url,
            temp_dir,
            opener=opener_for(lineup(), "US_Test-Cable_lineup.json"),
        )
        assert result["filename"] == "US_Test-Cable_lineup.json"
        assert result["channels"] == 1
        saved = json.loads((Path(temp_dir) / result["filename"]).read_text(encoding="utf-8"))
        assert saved["package"] == "Test Cable"

        refreshed = import_generated_lineup(
            url,
            temp_dir,
            opener=opener_for(lineup("Other Cable", "Other Network"), "US_Other-Cable_lineup.json"),
        )
        assert refreshed["filename"] == "US_Other-Cable_lineup.json"
        assert not (Path(temp_dir) / "US_Test-Cable_lineup.json").exists()
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
