from typing import Dict, Optional

from shared_libs.config_models.core_ssot_models import (
    SystemDefinition,
    PointUUID,
    PointDefinition,
    FunctionGrouping,
    DriverComponentDefinition,
    GovernorComponentDefinition,
    MicrocontrollerComponentDefinition,
    ManualSourceComponentDefinition,
)


class TopicGenerator:
    """Generates MQTT topics based on ADR-20 rules (copied from legacy)."""

    def __init__(self, system_config: SystemDefinition):
        self.system_config = system_config
        self.global_prefix = system_config.global_settings.mqtt_topic_prefix
        self.component_by_id = {comp.id: comp for comp in system_config.components}
        self.point_provider_map = self._build_point_provider_map()

    def _build_point_provider_map(self) -> Dict[PointUUID, str]:
        provider_map: Dict[PointUUID, str] = {}
        for comp in self.system_config.components:
            if isinstance(comp, MicrocontrollerComponentDefinition):
                for point_uuid in comp.points_provided:
                    provider_map[point_uuid] = comp.id
            elif isinstance(comp, (DriverComponentDefinition, GovernorComponentDefinition, ManualSourceComponentDefinition)):
                if comp.virtual_points_provided:
                    for point_uuid in comp.virtual_points_provided:
                        provider_map[point_uuid] = comp.id
        return provider_map

    def generate_topic_for_point(self, point: PointDefinition) -> str:
        source_component_id = self._get_source_component_id(point)

        if point.function_grouping == FunctionGrouping.SENSOR:
            units_slug = self._slugify(point.units)
            return f"{self.global_prefix}{source_component_id}/sensors/{point.topic_originator_slug}/{units_slug}"
        elif point.function_grouping == FunctionGrouping.ACTUATOR:
            return f"{self.global_prefix}{source_component_id}/actuators/{point.topic_device_slug}/readback"
        elif point.function_grouping == FunctionGrouping.STATUS:
            return f"{self.global_prefix}{source_component_id}/statuses/{point.topic_status_slug}"
        elif point.function_grouping == FunctionGrouping.COMMAND:
            target_component_id = self._get_command_target_component_id(point)
            return f"{self.global_prefix}{source_component_id}/commands/{target_component_id}/{point.topic_directive_slug}/write"
        else:
            raise ValueError(f"Unknown function_grouping: {point.function_grouping}")

    def _get_source_component_id(self, point: PointDefinition) -> str:
        component_id = self.point_provider_map.get(point.uuid)
        if component_id is None:
            raise ValueError(f"No component found that provides point UUID: {point.uuid}")
        return component_id

    def _get_command_target_component_id(self, point: PointDefinition) -> str:
        source_component_id = self._get_source_component_id(point)
        source_component = self.component_by_id.get(source_component_id)
        if source_component is None:
            raise ValueError(f"Source component not found: {source_component_id}")

        if isinstance(source_component, DriverComponentDefinition):
            return source_component.controls_microcontroller
        elif isinstance(source_component, GovernorComponentDefinition):
            if len(source_component.controls_drivers) != 1:
                raise ValueError(
                    f"Governor {source_component_id} controls multiple drivers, cannot determine single target"
                )
            controlled_driver_id = source_component.controls_drivers[0]
            controlled_driver = self.component_by_id.get(controlled_driver_id)
            if isinstance(controlled_driver, DriverComponentDefinition):
                return controlled_driver.controls_microcontroller
            else:
                raise ValueError(
                    f"Governor {source_component_id} controls non-driver component: {controlled_driver_id}"
                )
        elif hasattr(point, "target_component") and point.target_component:
            return point.target_component  # Manual commands
        else:
            raise ValueError(
                f"Command point {point.uuid} is sourced by component type that doesn't control other components"
            )

    @staticmethod
    def _slugify(text: str) -> str:
        import re
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", text.lower()).strip("_")
        return slug


class TopicResolver:
    """Thin helper around TopicGenerator with UUID-based lookups and command pairing."""

    def __init__(self, system_config: SystemDefinition):
        self.system_config = system_config
        self.points_by_uuid_map: Dict[PointUUID, PointDefinition] = {
            p.uuid: p for p in system_config.points
        }
        self.topic_generator = TopicGenerator(system_config)

    def get_topic(self, point_uuid: PointUUID) -> str:
        point = self.points_by_uuid_map.get(point_uuid)
        if point is None:
            raise ValueError(f"Point UUID not found: {point_uuid}")
        return self.topic_generator.generate_topic_for_point(point)

    def get_command_write_topic(self, readback_uuid: PointUUID) -> Optional[str]:
        for p in self.system_config.points:
            if p.readback_point_uuid == readback_uuid:
                return self.get_topic(p.uuid)
        return None


