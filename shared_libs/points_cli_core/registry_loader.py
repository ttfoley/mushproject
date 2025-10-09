from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Tuple


DEFAULT_REGISTRY_PATH = (
	Path(__file__).resolve().parents[2]
	/ "artifacts"
	/ "points_registry"
	/ "global_points_registry.json"
)


@dataclass(frozen=True)
class Point:
	uuid: str
	name: str
	description: Optional[str]
	function_grouping: str
	value_type: str
	data_source_layer: str
	access: str
	mqtt_topic: str
	validation_rules: Mapping[str, Any]
	writable_by: Optional[List[str]] = None
	initial_value: Optional[Any] = None
	readback_point_uuid: Optional[str] = None


class PointsRegistry:
	def __init__(
		self,
		points_by_uuid: Mapping[str, Point],
		name_index: Mapping[str, List[str]],
	):
		self._points_by_uuid = dict(points_by_uuid)
		self._name_index = dict(name_index)

	def get_by_uuid(self, uuid: str) -> Optional[Point]:
		return self._points_by_uuid.get(uuid)

	def search_by_name_substring(self, substring: str) -> List[Point]:
		key = substring.lower().strip()
		uuids = self._name_index.get(key, [])
		return [self._points_by_uuid[u] for u in uuids]

	def all_points(self) -> Iterable[Point]:
		return self._points_by_uuid.values()


def _point_from_dict(d: Mapping[str, Any]) -> Point:
	return Point(
		uuid=str(d["uuid"]),
		name=str(d["name"]),
		description=d.get("description"),
		function_grouping=str(d["function_grouping"]),
		value_type=str(d["value_type"]),
		data_source_layer=str(d["data_source_layer"]),
		access=str(d["access"]),
		mqtt_topic=str(d["mqtt_topic"]),
		validation_rules=d.get("validation_rules", {}),
		writable_by=d.get("writable_by"),
		initial_value=d.get("initial_value"),
		readback_point_uuid=d.get("readback_point_uuid"),
	)


def _build_indices(points: Mapping[str, Point]) -> Mapping[str, List[str]]:
	name_index: MutableMapping[str, List[str]] = {}
	for u, p in points.items():
		name_lower = p.name.lower()
		# Cheap substring index: index all rolling windows up to length 64
		# This keeps implementation simple; CLI will also do linear contains() scans when needed.
		max_len = min(64, len(name_lower))
		seen_keys: set[str] = set()
		for start in range(len(name_lower)):
			for length in range(1, max_len - start + 1):
				k = name_lower[start : start + length]
				if k in seen_keys:
					continue
				seen_keys.add(k)
				name_index.setdefault(k, []).append(u)
	return name_index


def load_registry(path: Optional[Path] = None) -> PointsRegistry:
	"""Load points registry JSON and build indices.

	If path is None, uses DEFAULT_REGISTRY_PATH.
	"""
	registry_path = Path(path) if path is not None else DEFAULT_REGISTRY_PATH
	with registry_path.open("r", encoding="utf-8") as f:
		obj: Mapping[str, Any] = json.load(f)
	points_obj = obj.get("points", {})
	points: Dict[str, Point] = {}
	for uuid, pdata in points_obj.items():
		p = _point_from_dict(pdata)
		points[uuid] = p
	name_index = _build_indices(points)
	return PointsRegistry(points_by_uuid=points, name_index=name_index)


