from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional
from uuid6 import uuid7

from .registry_loader import Point


def _generate_command_id() -> str:
	return str(uuid7())


def _now_iso8601_utc_ms() -> str:
	now = datetime.now(tz=timezone.utc)
	# Ensure milliseconds and trailing Z
	return now.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def build_payload(
    point: Point,
    value: Any,
    *,
    role: Optional[str] = None,
    trace: bool = False,
    strict_embedded: bool = False,
) -> Dict[str, Any]:
	base: Dict[str, Any] = {
		"timestamp_utc": _now_iso8601_utc_ms(),
		"uuid": point.uuid,
		"value": value,
	}
	if strict_embedded:
		return base
	if trace and role:
		base["source"] = role
		base["command_id"] = _generate_command_id()
	return base


