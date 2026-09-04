"""Download and persist a generated Lineuparr lineup.

This module intentionally uses only the Python standard library so it can be
tested without Django or a running Dispatcharr instance.
"""

import json
import os
import re
import tempfile
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlsplit
from urllib.request import Request, urlopen


LINEUP_FILENAME_RE = re.compile(r"^[A-Z]{2}_.+_lineup\.json$")
DEFAULT_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 30


class LineupImportError(ValueError):
    """A generated lineup could not be downloaded or validated."""


def _validated_http_url(value):
    url = str(value or "").strip()
    if not url:
        raise LineupImportError(
            "Generated Lineup URL is empty. Enter a URL and save settings before importing."
        )
    if len(url) > 4096:
        raise LineupImportError("The generated lineup URL is too long.")

    parsed = urlsplit(url)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise LineupImportError("The generated lineup URL must use HTTP or HTTPS.")
    if parsed.username is not None or parsed.password is not None:
        raise LineupImportError("Do not embed credentials in the generated lineup URL.")
    return url


def _response_filename(response):
    candidates = []
    get_filename = getattr(response.headers, "get_filename", None)
    if callable(get_filename):
        candidates.append(get_filename())

    final_url = _validated_http_url(response.geturl())
    candidates.append(unquote(os.path.basename(urlsplit(final_url).path)))

    for candidate in candidates:
        if not candidate:
            continue
        candidate = str(candidate).strip()
        if (
            candidate == os.path.basename(candidate)
            and "\\" not in candidate
            and "\x00" not in candidate
            and LINEUP_FILENAME_RE.fullmatch(candidate)
        ):
            return candidate

    raise LineupImportError(
        "The response must provide a filename such as "
        "US_Provider_lineup.json in Content-Disposition or the URL path."
    )


def _read_response(response, max_bytes):
    content_length = response.headers.get("Content-Length")
    if content_length:
        try:
            if int(content_length) > max_bytes:
                raise LineupImportError(
                    f"The generated lineup is larger than the {max_bytes // (1024 * 1024)} MB limit."
                )
        except ValueError:
            pass

    payload = response.read(max_bytes + 1)
    if len(payload) > max_bytes:
        raise LineupImportError(
            f"The generated lineup is larger than the {max_bytes // (1024 * 1024)} MB limit."
        )
    if not payload:
        raise LineupImportError("The generated lineup response was empty.")
    return payload


def validate_lineup_document(payload):
    """Parse a JSON payload and validate the minimum Lineuparr contract."""
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise LineupImportError("The generated lineup is not UTF-8 JSON.") from exc

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LineupImportError(f"The generated lineup is not valid JSON: {exc.msg}.") from exc

    if not isinstance(data, dict):
        raise LineupImportError("The generated lineup must be a JSON object.")
    categories = data.get("categories")
    if not isinstance(categories, dict) or not categories:
        raise LineupImportError("The generated lineup must contain a non-empty categories object.")

    channel_count = 0
    for category, channels in categories.items():
        if not isinstance(category, str) or not category.strip():
            raise LineupImportError("Every generated lineup category must have a name.")
        if not isinstance(channels, list):
            raise LineupImportError(f"Category {category!r} must contain a list of channels.")
        seen_names = set()
        for index, channel in enumerate(channels):
            if not isinstance(channel, dict):
                raise LineupImportError(f"Channel {index + 1} in {category!r} must be an object.")
            if not isinstance(channel.get("name"), str) or not channel["name"].strip():
                raise LineupImportError(f"Channel {index + 1} in {category!r} is missing a name.")
            if channel["name"] in seen_names:
                raise LineupImportError(
                    f"Category {category!r} contains duplicate channel name {channel['name']!r}."
                )
            seen_names.add(channel["name"])
            if "number" not in channel:
                raise LineupImportError(
                    f"Channel {channel['name']!r} in {category!r} is missing a number."
                )
            channel_count += 1

    if channel_count == 0:
        raise LineupImportError("The generated lineup does not contain any channels.")
    return data, len(categories), channel_count


def _atomic_json_write(path, data, mode=0o600):
    directory = os.path.dirname(path)
    fd, temp_path = tempfile.mkstemp(prefix=".lineuparr-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_path, mode)
        os.replace(temp_path, path)
    except Exception:
        try:
            os.unlink(temp_path)
        except FileNotFoundError:
            pass
        raise


def import_generated_lineup(url, destination_dir, opener=None,
                            timeout=DEFAULT_TIMEOUT_SECONDS,
                            max_bytes=DEFAULT_MAX_BYTES):
    """Fetch one generated lineup and atomically recreate its persistent file."""
    url = _validated_http_url(url)
    opener = opener or urlopen
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "Lineuparr generated-lineup importer",
        },
    )

    try:
        with opener(request, timeout=timeout) as response:
            status = getattr(response, "status", 200)
            if status < 200 or status >= 300:
                raise LineupImportError(f"The Generated Lineup URL returned HTTP {status}.")
            filename = _response_filename(response)
            payload = _read_response(response, max_bytes)
    except LineupImportError:
        raise
    except HTTPError as exc:
        raise LineupImportError(f"The Generated Lineup URL returned HTTP {exc.code}.") from exc
    except URLError as exc:
        raise LineupImportError("The Generated Lineup URL is unreachable.") from exc
    except TimeoutError as exc:
        raise LineupImportError("The Generated Lineup URL timed out.") from exc
    except OSError as exc:
        raise LineupImportError("The Generated Lineup URL could not be downloaded.") from exc
    except Exception as exc:
        # Do not echo arbitrary request-library errors because they can contain
        # the configured URL, including private query parameters.
        raise LineupImportError("The Generated Lineup URL could not be downloaded.") from exc

    data, category_count, channel_count = validate_lineup_document(payload)

    os.makedirs(destination_dir, mode=0o700, exist_ok=True)
    destination_dir = os.path.realpath(destination_dir)
    destination_path = os.path.join(destination_dir, filename)
    operation = "refreshed" if os.path.lexists(destination_path) else "created"
    _atomic_json_write(destination_path, data)

    package = data.get("package")
    if not isinstance(package, str) or not package.strip():
        package = filename
    return {
        "filename": filename,
        "path": destination_path,
        "package": package,
        "categories": category_count,
        "channels": channel_count,
        "operation": operation,
    }
