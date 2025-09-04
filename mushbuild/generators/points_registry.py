from pathlib import Path
from typing import Dict

from shared_libs.config_models.core_ssot_models import SystemDefinition
from mushbuild.utils.topics import TopicGenerator


def write_json(file_path: Path, data: Dict) -> bool:
    try:
        import json
        with open(file_path, "w") as f:
            json.dump(data, f, indent=2)
        print(f"✅ Successfully wrote to {file_path}")
        return True
    except Exception as e:
        print(f"❌ Error writing to {file_path}: {e}")
        return False


class PointsRegistryGenerator:
    """Generates the global points registry JSON file (SSOT-derived topics)."""

    def __init__(self, system_config: SystemDefinition, output_path: Path):
        self.system_config = system_config
        self.output_path = output_path

    def generate(self) -> bool:
        print(f"\n--- Generating Global Points Registry (refactor) ---")
        topic_generator = TopicGenerator(self.system_config)
        topics_by_uuid = {p.uuid: topic_generator.generate_topic_for_point(p) for p in self.system_config.points}

        registry: Dict = {
            "metadata": {
                "generated_at": "placeholder_timestamp",
                "total_points": len(self.system_config.points),
                "mqtt_topic_prefix": self.system_config.global_settings.mqtt_topic_prefix,
            },
            "points": {},
        }

        for point in self.system_config.points:
            point_data: Dict = {
                "uuid": point.uuid,
                "name": point.name,
                "description": point.description,
                "function_grouping": point.function_grouping.value,
                "value_type": point.value_type.value,
                "units": point.units,
                "data_source_layer": point.data_source_layer.value,
                "access": point.access.value,
                "mqtt_topic": topics_by_uuid.get(point.uuid),
                "persist_to_db": point.persist_to_db,
            }
            if point.validation_rules:
                point_data["validation_rules"] = point.validation_rules.model_dump()
            if point.initial_value is not None:
                point_data["initial_value"] = point.initial_value
            if point.readback_point_uuid:
                point_data["readback_point_uuid"] = point.readback_point_uuid
            if point.writable_by:
                point_data["writable_by"] = point.writable_by

            registry["points"][point.uuid] = point_data

        return write_json(self.output_path, registry)


