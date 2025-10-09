from __future__ import annotations

from typing import Iterable, List, Optional

from .registry_loader import PointsRegistry, Point


def resolve_by_uuid_or_name(registry: PointsRegistry, *, uuid: Optional[str] = None, name_substring: Optional[str] = None) -> List[Point]:
	if uuid:
		p = registry.get_by_uuid(uuid)
		return [p] if p else []
	if name_substring:
		name_key = name_substring.lower().strip()
		# Try indexed lookup first; if empty, fall back to linear scan contains()
		indexed = registry.search_by_name_substring(name_key)
		if indexed:
			return indexed
		return [p for p in registry.all_points() if name_key in p.name.lower()]
	return []


