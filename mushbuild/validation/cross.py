from typing import Any, Dict, List, Set

from shared_libs.config_models.core_ssot_models import (
    SystemDefinition,
    PointUUID,
    DriverComponentDefinition,
    GovernorComponentDefinition,
    MicrocontrollerComponentDefinition,
    ManualSourceComponentDefinition,
)
from shared_libs.config_models.component_configs import (
    DriverConfig,
    GovernorConfig,
    MicrocontrollerConfig,
)


class CrossValidator:
    """Performs cross-validation checks between components and SSOT."""

    def __init__(self, system_config: SystemDefinition):
        self.system_config = system_config

    def validate(self, validated_components: Dict[str, Any]) -> bool:
        print("\n--- Performing Cross-Validation ---")
        all_checks_passed = True
        errors: Dict[str, List[str]] = {
            "point_uuid_ref": [],
            "component_id_ref": [],
            "hierarchy_ref": [],
            "uniqueness": [],
            "point_provision": [],
            "command_readback_link": [],
            "orphaned_points": [],
            "multiply_provided_points": [],
        }

        master_point_uuids = {p.uuid for p in self.system_config.points}
        points_by_uuid_map = {p.uuid: p for p in self.system_config.points}
        master_component_ids = {c.id for c in self.system_config.components}
        master_hierarchy_levels = set(self.system_config.command_hierarchy)

        # Point UUID references in component configs exist in SSOT
        print("\nChecking Point UUID references in component configs against SSOT master list...")
        for component_id, config_object in validated_components.items():
            component_def = next((c for c in self.system_config.components if c.id == component_id), None)
            if not component_def:
                continue

            referenced_uuids_in_component: Set[PointUUID] = set()
            if isinstance(config_object, DriverConfig):
                from mushbuild.utils.uuid_utils import UUIDUtils
                referenced_uuids_in_component = UUIDUtils.extract_driver_point_uuids(config_object)
            elif isinstance(config_object, MicrocontrollerConfig):
                from mushbuild.utils.uuid_utils import UUIDUtils
                referenced_uuids_in_component = UUIDUtils.extract_microcontroller_point_uuids(config_object)
            elif isinstance(config_object, GovernorConfig):
                from mushbuild.utils.uuid_utils import UUIDUtils
                referenced_uuids_in_component = UUIDUtils.extract_governor_point_uuids(config_object)

            for uuid_ref in referenced_uuids_in_component:
                if uuid_ref not in master_point_uuids:
                    errors["point_uuid_ref"].append(
                        f"Component '{component_id}' references undefined Point UUID '{uuid_ref}'."
                    )
                    all_checks_passed = False
        if not errors["point_uuid_ref"]:
            print("   ✅ Point UUID references in component configs exist in SSOT.")

        # Uniqueness checks
        print("\nChecking uniqueness of names and IDs in SSOT...")
        point_names = [p.name for p in self.system_config.points]
        duplicate_point_names = {n for n in point_names if point_names.count(n) > 1}
        if duplicate_point_names:
            errors["uniqueness"].append(f"Duplicate PointDefinition names found in SSOT: {duplicate_point_names}")
            all_checks_passed = False
        component_ids = [c.id for c in self.system_config.components]
        duplicate_component_ids = {cid for cid in component_ids if component_ids.count(cid) > 1}
        if duplicate_component_ids:
            errors["uniqueness"].append(f"Duplicate Component IDs found in SSOT: {duplicate_component_ids}")
            all_checks_passed = False
        if not errors["uniqueness"]:
            print("   ✅ Point names and Component IDs in SSOT are unique.")

        # 'writable_by' and controls_* references
        print("\nChecking component/hierarchy references in SSOT ('writable_by', 'controls_')...")
        for point in self.system_config.points:
            if point.writable_by:
                for writer_id in point.writable_by:
                    if writer_id not in master_component_ids and writer_id not in master_hierarchy_levels:
                        errors["hierarchy_ref"].append(
                            f"Point '{point.uuid}' ({point.name}): 'writable_by' item '{writer_id}' is not a defined component ID or command hierarchy level."
                        )
                        all_checks_passed = False

        for comp in self.system_config.components:
            if isinstance(comp, DriverComponentDefinition):
                if comp.controls_microcontroller not in master_component_ids:
                    errors["component_id_ref"].append(
                        f"DriverComponent '{comp.id}' 'controls_microcontroller' references undefined component ID '{comp.controls_microcontroller}'."
                    )
                    all_checks_passed = False
            elif isinstance(comp, GovernorComponentDefinition):
                for driver_id in comp.controls_drivers:
                    if driver_id not in master_component_ids:
                        errors["component_id_ref"].append(
                            f"GovernorComponent '{comp.id}' 'controls_drivers' references undefined component ID '{driver_id}'."
                        )
                        all_checks_passed = False
        if not errors["hierarchy_ref"] and not errors["component_id_ref"]:
            print("   ✅ 'writable_by' and 'controls_' references in SSOT appear valid.")

        # Point provisioning
        print("\nChecking point provisioning by components in SSOT...")
        master_point_uuids_set = set(master_point_uuids)
        claimed_list: List[PointUUID] = []
        for comp in self.system_config.components:
            if isinstance(comp, MicrocontrollerComponentDefinition):
                claimed_list.extend(comp.points_provided)
            elif isinstance(comp, (DriverComponentDefinition, GovernorComponentDefinition, ManualSourceComponentDefinition)):
                if comp.virtual_points_provided:
                    claimed_list.extend(comp.virtual_points_provided)

        claimed_set = set(claimed_list)
        orphaned = master_point_uuids_set - claimed_set
        if orphaned:
            for p_uuid in orphaned:
                name = points_by_uuid_map[p_uuid].name if p_uuid in points_by_uuid_map else "N/A"
                errors["orphaned_points"].append(
                    f"Point UUID '{p_uuid}' (Name: {name}) is not provided by any component."
                )
            all_checks_passed = False

        from collections import Counter
        multi = {uuid for uuid, count in Counter(claimed_list).items() if count > 1}
        if multi:
            for m_uuid in multi:
                errors["multiply_provided_points"].append(
                    f"Point UUID '{m_uuid}' is provided by multiple components."
                )
            all_checks_passed = False

        if not errors["orphaned_points"] and not errors["multiply_provided_points"]:
            print("   ✅ All system-provided points are uniquely claimed by a component.")

        # Command/readback linkages
        print("\nChecking command/readback point linkages in SSOT...")
        for p_uuid, p_def in points_by_uuid_map.items():
            if p_def.readback_point_uuid:
                rb_uuid = p_def.readback_point_uuid
                if rb_uuid == p_uuid or rb_uuid not in points_by_uuid_map:
                    errors["command_readback_link"].append(
                        f"Invalid readback link from '{p_uuid}' to '{rb_uuid}'."
                    )
                    all_checks_passed = False
        if not errors["command_readback_link"]:
            print("   ✅ Command/readback point linkages appear consistent.")

        if not all_checks_passed:
            print("\n❌ Cross-Validation Failed!")
            for category, msgs in errors.items():
                if msgs:
                    print(f"   --- {category} ---")
                    for msg in msgs:
                        print(f"      - {msg}")
        else:
            print("\n✅ All Cross-Validation Checks Passed.")

        return all_checks_passed


