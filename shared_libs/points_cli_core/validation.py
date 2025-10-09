from __future__ import annotations

from typing import Any, Iterable, Mapping, Optional

from .registry_loader import Point


class ValidationError(ValueError):
	pass


def check_access(point: Point) -> None:
	if point.function_grouping != "command" or point.access != "READ_WRITE":
		raise ValidationError(
			f"Point {point.uuid} is not writable: function_grouping={point.function_grouping}, access={point.access}"
		)


def check_acl(point: Point, role: str, *, superuser: bool = False, force: bool = False) -> None:
	allowed = point.writable_by or []
	if role in allowed:
		return
	if superuser and force:
		return
	raise ValidationError(
		f"Role '{role}' not permitted to write {point.uuid}. Allowed: {allowed or '[]'}."
	)


def coerce_and_validate_value(point: Point, value_str: str) -> Any:
	vtype = point.value_type
	rules: Mapping[str, Any] = point.validation_rules or {}
	if vtype == "DISCRETE":
		allowed: Optional[Iterable[Any]] = rules.get("allowed_values")
		value = value_str
		if allowed is not None and value not in allowed:
			raise ValidationError(
				f"Invalid value '{value}'. Allowed: {sorted(allowed)}"
			)
		return value
	elif vtype == "CONTINUOUS":
		try:
			value = float(value_str)
		except ValueError as e:
			raise ValidationError(f"Invalid number '{value_str}'") from e
		min_v = rules.get("min_value")
		max_v = rules.get("max_value")
		if min_v is not None and value < float(min_v):
			raise ValidationError(f"Value {value} < min {min_v}")
		if max_v is not None and value > float(max_v):
			raise ValidationError(f"Value {value} > max {max_v}")
		return value
	else:
		raise ValidationError(f"Unsupported value_type '{vtype}' for point {point.uuid}")


