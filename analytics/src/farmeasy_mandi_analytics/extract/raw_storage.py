"""Immutable storage for raw source receipts.

Raw receipts are intentionally kept outside the validation and transformation
layers.  This allows a pipeline run to be replayed from precisely the bytes it
received from an official source, while a small per-run manifest records the
receipt fingerprint and non-sensitive operational context.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

MANIFEST_FILENAME = "manifest.json"
MANIFEST_SCHEMA_VERSION = 1

_SAFE_PATH_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SAFE_SUFFIX = re.compile(r"^\.[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")
_SENSITIVE_KEY_PARTS = (
    "apikey",
    "authorization",
    "credential",
    "password",
    "secret",
    "token",
    "privatekey",
)
_INLINE_SECRET = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|auth(?:orization)?|password|secret|token)"
    r"\s*=\s*([^&\s,;]+)"
)


class RawReceiptError(ValueError):
    """Raised when an immutable raw receipt cannot be stored safely."""


@dataclass(frozen=True, slots=True)
class RawReceipt:
    """An immutable raw artifact and its content fingerprint."""

    run_id: str
    source_name: str
    sha256: str
    byte_count: int
    captured_at: str
    receipt_path: Path
    manifest_path: Path
    content_type: str | None = None


def _utc_timestamp(value: datetime | None = None) -> str:
    timestamp = value or datetime.now(UTC)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    return timestamp.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _require_safe_component(value: str, label: str) -> str:
    if not _SAFE_PATH_COMPONENT.fullmatch(value):
        raise RawReceiptError(
            f"{label} must contain only letters, numbers, dots, underscores, or hyphens "
            "and must not contain path separators."
        )
    return value


def _safe_suffix(value: str | None) -> str:
    if value is None or not value:
        return ".bin"
    suffix = value if value.startswith(".") else f".{value}"
    if not _SAFE_SUFFIX.fullmatch(suffix):
        raise RawReceiptError("suffix must be a simple file extension, such as '.csv' or '.json'.")
    return suffix.lower()


def _normalise_metadata_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).casefold())


def _is_sensitive_key(value: object) -> bool:
    key = _normalise_metadata_key(value)
    return key == "key" or key.endswith("key") or any(part in key for part in _SENSITIVE_KEY_PARTS)


def _redact_url(value: str) -> str:
    """Remove known sensitive query parameters without discarding useful URL context."""
    try:
        parsed = urlsplit(value)
    except ValueError:
        return value
    if not parsed.query:
        return value

    query = [
        (name, "***redacted***" if _is_sensitive_key(name) else item)
        for name, item in parse_qsl(parsed.query, keep_blank_values=True)
    ]
    return urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment)
    )


def _safe_metadata_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): "***redacted***" if _is_sensitive_key(key) else _safe_metadata_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [_safe_metadata_value(item) for item in value]
    if isinstance(value, Path):
        return value.name
    if isinstance(value, datetime):
        return _utc_timestamp(value)
    if isinstance(value, str):
        redacted_url = _redact_url(value)
        if redacted_url != value:
            return redacted_url
        return _INLINE_SECRET.sub(r"\1=***redacted***", value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)


def redact_manifest_metadata(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return JSON-safe metadata with credentials removed or redacted.

    The raw receipt itself remains byte-for-byte unchanged.  This function only
    guards the human-readable manifest, where request URLs and headers are most
    likely to accidentally expose a credential.
    """
    if metadata is None:
        return {}
    return _safe_metadata_value(metadata)


class RawReceiptStore:
    """Write content-addressed raw receipts and one manifest per pipeline run."""

    def __init__(self, raw_dir: Path | str) -> None:
        self.raw_dir = Path(raw_dir)

    def manifest_path_for(self, run_id: str) -> Path:
        """Return the manifest location for a validated pipeline run identifier."""
        safe_run_id = _require_safe_component(run_id, "run_id")
        return self.raw_dir / safe_run_id / MANIFEST_FILENAME

    def read_manifest(self, run_id: str) -> dict[str, Any]:
        """Read a run manifest, returning an empty receipt list before the first write."""
        manifest_path = self.manifest_path_for(run_id)
        if not manifest_path.exists():
            return {
                "schema_version": MANIFEST_SCHEMA_VERSION,
                "run_id": run_id,
                "receipts": [],
            }
        try:
            contents = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise RawReceiptError(
                f"Could not read raw receipt manifest {manifest_path}."
            ) from error
        if not isinstance(contents, dict) or contents.get("run_id") != run_id:
            raise RawReceiptError(
                f"Raw receipt manifest {manifest_path} does not match run {run_id!r}."
            )
        if not isinstance(contents.get("receipts"), list):
            raise RawReceiptError(
                f"Raw receipt manifest {manifest_path} has an invalid receipts list."
            )
        return contents

    def store_bytes(
        self,
        raw_bytes: bytes | bytearray | memoryview,
        *,
        run_id: str,
        source_name: str,
        suffix: str | None = None,
        content_type: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        captured_at: datetime | None = None,
    ) -> RawReceipt:
        """Persist raw bytes exactly once per source/fingerprint within a run.

        ``raw_bytes`` is not decoded, reformatted, or otherwise changed before
        writing.  A SHA-256 digest supplies both the receipt filename and the
        idempotency key in the run manifest.
        """
        if not isinstance(raw_bytes, (bytes, bytearray, memoryview)):
            raise TypeError("raw_bytes must be bytes, bytearray, or memoryview.")

        safe_run_id = _require_safe_component(run_id, "run_id")
        safe_source_name = _require_safe_component(source_name, "source_name")
        artifact_suffix = _safe_suffix(suffix)
        payload = bytes(raw_bytes)
        fingerprint = sha256(payload).hexdigest()
        timestamp = _utc_timestamp(captured_at)

        run_directory = self.raw_dir / safe_run_id
        receipt_directory = run_directory / "receipts"
        receipt_directory.mkdir(parents=True, exist_ok=True)
        filename = f"{safe_source_name}-{fingerprint}{artifact_suffix}"
        receipt_path = receipt_directory / filename
        self._write_bytes_once(receipt_path, payload)

        manifest_path = run_directory / MANIFEST_FILENAME
        relative_path = receipt_path.relative_to(run_directory).as_posix()
        manifest = self.read_manifest(safe_run_id)
        receipt_entry = {
            "source_name": source_name,
            "sha256": fingerprint,
            "byte_count": len(payload),
            "captured_at": timestamp,
            "content_type": content_type,
            "raw_file": relative_path,
            "metadata": redact_manifest_metadata(metadata),
        }
        existing = manifest["receipts"]
        if not any(
            item.get("source_name") == source_name
            and item.get("sha256") == fingerprint
            and item.get("raw_file") == relative_path
            for item in existing
            if isinstance(item, dict)
        ):
            existing.append(receipt_entry)
            manifest.setdefault("created_at", timestamp)
            manifest["updated_at"] = timestamp
            self._write_manifest(manifest_path, manifest)

        return RawReceipt(
            run_id=safe_run_id,
            source_name=source_name,
            sha256=fingerprint,
            byte_count=len(payload),
            captured_at=timestamp,
            receipt_path=receipt_path,
            manifest_path=manifest_path,
            content_type=content_type,
        )

    def store_file(
        self,
        source_path: Path | str,
        *,
        run_id: str,
        source_name: str,
        content_type: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        captured_at: datetime | None = None,
    ) -> RawReceipt:
        """Store a local source file without decoding or changing its bytes."""
        path = Path(source_path)
        try:
            payload = path.read_bytes()
        except OSError as error:
            raise RawReceiptError(f"Could not read raw source file {path}.") from error
        combined_metadata = {"source_filename": path.name, **(metadata or {})}
        return self.store_bytes(
            payload,
            run_id=run_id,
            source_name=source_name,
            suffix=path.suffix or ".bin",
            content_type=content_type,
            metadata=combined_metadata,
            captured_at=captured_at,
        )

    # Clear, short aliases for call sites that prefer ``save`` terminology.
    save_bytes = store_bytes
    save_file = store_file

    @staticmethod
    def _write_bytes_once(destination: Path, payload: bytes) -> None:
        try:
            with destination.open("xb") as receipt_file:
                receipt_file.write(payload)
        except FileExistsError:
            try:
                existing_fingerprint = sha256(destination.read_bytes()).hexdigest()
            except OSError as error:
                raise RawReceiptError(
                    f"Could not verify existing raw receipt {destination}."
                ) from error
            expected_fingerprint = sha256(payload).hexdigest()
            if existing_fingerprint != expected_fingerprint:
                raise RawReceiptError(
                    f"Existing raw receipt {destination} does not match its "
                    "content-addressed filename."
                ) from None
        except OSError as error:
            raise RawReceiptError(f"Could not write raw receipt {destination}.") from error

    @staticmethod
    def _write_manifest(destination: Path, manifest: Mapping[str, Any]) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=destination.parent,
                prefix=".manifest-",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                json.dump(manifest, temporary_file, ensure_ascii=False, indent=2, sort_keys=True)
                temporary_file.write("\n")
                temporary_name = temporary_file.name
            os.replace(temporary_name, destination)
        except (OSError, TypeError, ValueError) as error:
            try:
                Path(temporary_name).unlink(missing_ok=True)
            except (OSError, UnboundLocalError):
                pass
            raise RawReceiptError(f"Could not write raw receipt manifest {destination}.") from error


def store_raw_receipt(
    raw_dir: Path | str,
    raw_bytes: bytes | bytearray | memoryview,
    *,
    run_id: str,
    source_name: str,
    suffix: str | None = None,
    content_type: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    captured_at: datetime | None = None,
) -> RawReceipt:
    """Convenience wrapper for a one-off immutable raw receipt write."""
    return RawReceiptStore(raw_dir).store_bytes(
        raw_bytes,
        run_id=run_id,
        source_name=source_name,
        suffix=suffix,
        content_type=content_type,
        metadata=metadata,
        captured_at=captured_at,
    )
