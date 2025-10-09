"""Core utilities for SSOT-aware points CLI.

Modules:
- registry_loader: Load the global points registry and build indices
- validation: Access control and value validation helpers
- payload: ADR-10 payload builder with optional trace fields
- mqtt_client: Lightweight MQTT publisher configured from secrets
- search: Resolve points by uuid or name substring
"""

__all__ = [
	"registry_loader",
	"validation",
	"payload",
	"mqtt_client",
	"search",
]


