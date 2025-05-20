# build.py

import yaml
from pathlib import Path
from pydantic import ValidationError, BaseModel # BaseModel for type hinting
import sys
from typing import Optional, Dict, Any, Set, Tuple, List, get_args, get_origin, Union

# --- Model Imports ---
try:
    # Assuming core_ssot_models now defines PointUUID
    from common.config_models.core_ssot_models import (
        SystemDefinition, ComponentType, PointDefinition, PointUUID,
        ValueType, AccessMode, # Added ValueType, AccessMode
        DriverComponentDefinition, GovernorComponentDefinition, MicrocontrollerComponentDefinition
    )
    from common.config_models.component_configs import (
        DriverConfig, # Removed unused WriteAction, StateCondition, etc. for this script
        DriverPWMOutputMapping, # Kept for DriverConfig
        AnyConstraintDefinition, ConstraintDefinition, ConstraintGroup, # Kept for DriverConfig
        TransitionDefinition, BaseConstraintDefinition, # Kept for DriverConfig
        GovernorConfig, MicrocontrollerConfig,
        BangBangControllerConfig, TimeScheduleControllerConfig, PIDControllerConfig # Added controller configs
    )

except ImportError as e:
    print(f"Error: Could not import required Pydantic models or PointUUID type: {e}")
    print("Make sure build.py is in the project root ('control/') and models are in common/config_models/")
    print("Ensure __init__.py exists in common/ and common/config_models/ directories.")
    print(f"Current sys.path: {sys.path}")
    sys.exit(1)

# --- Configuration ---
SSOT_FILE_PATH = Path("system_definition.yaml")
CONFIG_BASE_DIR = Path(".")

# --- Model Mapping ---
COMPONENT_MODEL_MAP = {
    ComponentType.DRIVER: DriverConfig,
    ComponentType.GOVERNOR: GovernorConfig,
    ComponentType.MICROCONTROLLER: MicrocontrollerConfig,
}

# --- Validation Functions (validate_ssot, validate_component_configs) ---
def validate_ssot(file_path: Path) -> Optional[SystemDefinition]:
    """Loads and validates the main SSOT YAML file."""
    print(f"\n--- Validating SSOT File: {file_path} ---")
    if not file_path.is_file():
        print(f"❌ Error: SSOT file not found at '{file_path}'")
        return None
    try:
        with open(file_path, 'r') as file:
            loaded_data = yaml.safe_load(file)
            if loaded_data is None:
                print(f"❌ Error: YAML file '{file_path}' is empty or invalid.")
                return None
    except yaml.YAMLError as e:
        print(f"❌ Error parsing YAML file '{file_path}':\n{e}")
        return None
    except Exception as e:
        print(f"❌ An unexpected error occurred loading '{file_path}': {e}")
        return None
    try:
        system_config = SystemDefinition(**loaded_data)
        print("✅ SSOT Structure Validation Successful!")
        print(f"   Components Found: {len(system_config.components)}")
        print(f"   Points Found: {len(system_config.points)}")
        return system_config
    except ValidationError as e:
        print("❌ Pydantic Validation Failed for SSOT file!")
        print("   Please check system_definition.yaml against the SystemDefinition model.")
        print("   Error details:")
        print(e)
        return None
    except Exception as e:
        print(f"❌ An unexpected error occurred during SSOT Pydantic validation: {e}")
        return None

def validate_component_configs(
    system_config: SystemDefinition,
    points_by_uuid_map: Dict[PointUUID, PointDefinition] # Pass the map here
    ) -> Tuple[bool, Dict[str, Any]]:
    """
    Loads and validates specific config files for each component listed in the SSOT.
    Passes context to Pydantic models for cross-referential validation.
    """
    print("\n--- Validating Component Configuration Files ---")
    all_components_valid = True
    validated_configs = {}
    for component in system_config.components:
        print(f"\nValidating component: id='{component.id}', type='{component.type.value}'")
        component_config_path_str = component.config_file
        component_config_path = CONFIG_BASE_DIR / component_config_path_str
        if not component_config_path.is_file():
            print(f"❌ Error: Config file not found at '{component_config_path}'")
            all_components_valid = False
            continue
        config_model = COMPONENT_MODEL_MAP.get(component.type)
        if not config_model:
            print(f"⚠️ Warning: No Pydantic model defined for type '{component.type.value}'. Skipping validation for '{component_config_path_str}'.")
            continue
        try:
            print(f"   Loading component config: '{component_config_path}'")
            with open(component_config_path, 'r') as file:
                component_data = yaml.safe_load(file)
                if component_data is None:
                    print(f"❌ Error: Component YAML file '{component_config_path}' is empty or invalid.")
                    all_components_valid = False
                    continue
        except yaml.YAMLError as e:
            print(f"❌ Error parsing component YAML file '{component_config_path}':\n{e}")
            all_components_valid = False
            continue
        except Exception as e:
            print(f"❌ An unexpected error occurred loading '{component_config_path}': {e}")
            all_components_valid = False
            continue
        try:
            print(f"   Validating using {config_model.__name__} model...")
            # Pass context to the model validation
            validation_context = {"points_by_uuid_map": points_by_uuid_map, "component_id": component.id}
            # Use model_validate for Pydantic V2
            validated_component_config = config_model.model_validate(component_data, context=validation_context)
            print(f"✅ Validation Successful for '{component_config_path_str}' using {config_model.__name__}.")
            validated_configs[component.id] = validated_component_config
        except ValidationError as e:
            print(f"❌ Pydantic Validation Failed for '{component_config_path_str}'!")
            print(f"   Please check this file against the {config_model.__name__} model.")
            print("   Error details:")
            print(e)
            all_components_valid = False
        except Exception as e:
            print(f"❌ An unexpected error occurred during Pydantic validation for '{component_config_path_str}': {e}")
            all_components_valid = False
    return all_components_valid, validated_configs


# --- Generic UUID Extraction Helper using Custom PointUUID Type ---
def _extract_uuids_from_instance(instance: Optional[Any], uuids_set: Set[str]):
    """
    Recursively extracts UUIDs from a Pydantic model instance or iterable
    by checking if field annotations are PointUUID or generics containing PointUUID.
    """
    if instance is None:
        return

    if isinstance(instance, BaseModel):
        for field_name, field_definition in instance.model_fields.items(): # Pydantic v2
            field_value = getattr(instance, field_name)
            annotation = field_definition.annotation

            origin = get_origin(annotation)
            args = get_args(annotation)

            if annotation is PointUUID:
                if isinstance(field_value, str): # PointUUID is a str
                    uuids_set.add(field_value)
            elif origin is Union and PointUUID in args: # Handles Optional[PointUUID]
                if isinstance(field_value, str): # PointUUID is a str
                    uuids_set.add(field_value)
            elif origin is list and args and args[0] is PointUUID: # Handles List[PointUUID]
                if isinstance(field_value, list):
                    for item in field_value:
                        if isinstance(item, str): # PointUUID is a str
                            uuids_set.add(item)
            elif origin is Union: # Handles Optional[List[PointUUID]]
                is_optional_list_of_uuid = False
                for union_arg in args:
                    if get_origin(union_arg) is list and get_args(union_arg) and get_args(union_arg)[0] is PointUUID:
                        is_optional_list_of_uuid = True
                        break
                if is_optional_list_of_uuid and isinstance(field_value, list):
                    for item in field_value:
                        if isinstance(item, str): # PointUUID is a str
                            uuids_set.add(item)
            elif origin is dict and args and len(args) == 2: # Handles Dict[_, PointUUID] or Dict[_, Optional[PointUUID]]
                value_type_in_dict = args[1] # The type of the dictionary's values
                dict_val_origin = get_origin(value_type_in_dict)
                dict_val_args = get_args(value_type_in_dict)

                if value_type_in_dict is PointUUID:
                    if isinstance(field_value, dict):
                        for val_item in field_value.values():
                            if isinstance(val_item, str): uuids_set.add(val_item)
                elif dict_val_origin is Union and PointUUID in dict_val_args: # Optional[PointUUID] in dict values
                     if isinstance(field_value, dict):
                        for val_item in field_value.values():
                            if isinstance(val_item, str): uuids_set.add(val_item)
            elif isinstance(field_value, BaseModel): # Recurse for nested Pydantic models
                _extract_uuids_from_instance(field_value, uuids_set)
            elif isinstance(field_value, list): # Recurse for lists that might contain Pydantic models
                for item in field_value:
                    _extract_uuids_from_instance(item, uuids_set)
            elif isinstance(field_value, dict): # Recurse for dict values if they aren't PointUUID directly
                for value_in_dict in field_value.values():
                    _extract_uuids_from_instance(value_in_dict, uuids_set)
    elif isinstance(instance, list):
        for item in instance:
            _extract_uuids_from_instance(item, uuids_set)
    elif isinstance(instance, dict):
        for value in instance.values():
            _extract_uuids_from_instance(value, uuids_set)

# --- Specific Extraction Functions ---
def extract_driver_point_uuids(config: DriverConfig) -> Set[str]:
    uuids = set()
    _extract_uuids_from_instance(config, uuids)
    return uuids

def extract_microcontroller_point_uuids(config: MicrocontrollerConfig) -> Set[str]:
    uuids = set()
    _extract_uuids_from_instance(config, uuids)
    return uuids

def extract_governor_point_uuids(config: GovernorConfig) -> Set[str]:
    uuids = set()
    _extract_uuids_from_instance(config, uuids)
    return uuids

# --- Cross-Validation Function ---
def cross_validate_configs(system_config: SystemDefinition, validated_components: Dict[str, Any]) -> bool:
    """
    Performs cross-validation checks primarily focused on SSOT integrity and
    existence of referenced UUIDs. More detailed component-specific internal
    consistency checks are now handled by Pydantic model validators.
    """
    print("\n--- Performing Cross-Validation ---")
    all_checks_passed = True
    errors: Dict[str, List[str]] = {
        "point_uuid_ref": [], "component_id_ref": [], "hierarchy_ref": [],
        "uniqueness": [], "point_provision": [], "command_readback_link": []
    }

    master_point_uuids = {point.uuid for point in system_config.points}
    points_by_uuid_map = {point.uuid: point for point in system_config.points}
    master_component_ids = {comp.id for comp in system_config.components}
    master_hierarchy_levels = set(system_config.command_hierarchy)

    # 1. Check Point UUID references in component configs (ensure they exist in SSOT)
    print("\nChecking Point UUID references in component configs against SSOT master list...")
    for component_id, config_object in validated_components.items():
        component_def = next((comp for comp in system_config.components if comp.id == component_id), None)
        if not component_def: continue
        component_type_val = component_def.type.value
        component_config_file = component_def.config_file

        referenced_uuids_in_component = set()
        if isinstance(config_object, DriverConfig):
            referenced_uuids_in_component = extract_driver_point_uuids(config_object)
        elif isinstance(config_object, MicrocontrollerConfig):
            referenced_uuids_in_component = extract_microcontroller_point_uuids(config_object)
        elif isinstance(config_object, GovernorConfig):
            referenced_uuids_in_component = extract_governor_point_uuids(config_object)

        for uuid_ref in referenced_uuids_in_component:
            if uuid_ref not in master_point_uuids:
                msg = (f"Component '{component_id}' (type: {component_type_val}, config: {component_config_file}): "
                       f"References undefined Point UUID '{uuid_ref}'.")
                errors["point_uuid_ref"].append(msg)
                all_checks_passed = False
    if not errors["point_uuid_ref"]:
         print("   ✅ Point UUID references in component configs exist in SSOT.")

    # 2. Check Uniqueness of Point Names and Component IDs in SSOT
    print("\nChecking uniqueness of names and IDs in SSOT...")
    point_names = [p.name for p in system_config.points]
    duplicate_point_names = {name for name in point_names if point_names.count(name) > 1}
    if duplicate_point_names:
        errors["uniqueness"].append(f"Duplicate PointDefinition names found in SSOT: {duplicate_point_names}")
        all_checks_passed = False
    component_ids = [c.id for c in system_config.components]
    duplicate_component_ids = {cid for cid in component_ids if component_ids.count(cid) > 1}
    if duplicate_component_ids:
        errors["uniqueness"].append(f"Duplicate Component IDs found in SSOT: {duplicate_component_ids}")
        all_checks_passed = False
    if not errors["uniqueness"]:
        print("   ✅ Point names and Component IDs in SSOT are unique.")

    # 3. Check 'writable_by', 'controls_microcontroller', 'controls_drivers' in SSOT
    print("\nChecking component/hierarchy references in SSOT ('writable_by', 'controls_')...")
    for point in system_config.points:
        if point.writable_by:
            for writer_id in point.writable_by:
                if writer_id not in master_component_ids and writer_id not in master_hierarchy_levels:
                    msg = (f"Point '{point.uuid}' ({point.name}): 'writable_by' item '{writer_id}' "
                           f"is not a defined component ID or command hierarchy level.")
                    errors["hierarchy_ref"].append(msg)
                    all_checks_passed = False
    for comp in system_config.components:
        if isinstance(comp, DriverComponentDefinition):
            if comp.controls_microcontroller not in master_component_ids:
                msg = (f"DriverComponent '{comp.id}' 'controls_microcontroller' references "
                       f"undefined component ID '{comp.controls_microcontroller}'.")
                errors["component_id_ref"].append(msg)
                all_checks_passed = False
            else:
                controlled_comp_type = next((c.type for c in system_config.components if c.id == comp.controls_microcontroller), None)
                if controlled_comp_type != ComponentType.MICROCONTROLLER:
                    msg = (f"DriverComponent '{comp.id}' 'controls_microcontroller' references '{comp.controls_microcontroller}' "
                           f"which is type '{controlled_comp_type.value if controlled_comp_type else 'Unknown'}' not '{ComponentType.MICROCONTROLLER.value}'.")
                    errors["component_id_ref"].append(msg)
                    all_checks_passed = False
        elif isinstance(comp, GovernorComponentDefinition):
            for driver_id in comp.controls_drivers:
                if driver_id not in master_component_ids:
                    msg = (f"GovernorComponent '{comp.id}' 'controls_drivers' references "
                           f"undefined component ID '{driver_id}'.")
                    errors["component_id_ref"].append(msg)
                    all_checks_passed = False
                else:
                    controlled_comp_type = next((c.type for c in system_config.components if c.id == driver_id), None)
                    if controlled_comp_type != ComponentType.DRIVER:
                        msg = (f"GovernorComponent '{comp.id}' 'controls_drivers' references '{driver_id}' "
                               f"which is type '{controlled_comp_type.value if controlled_comp_type else 'Unknown'}' not '{ComponentType.DRIVER.value}'.")
                        errors["component_id_ref"].append(msg)
                        all_checks_passed = False
    if not errors["hierarchy_ref"] and not errors["component_id_ref"]:
        print("   ✅ 'writable_by' and 'controls_' references in SSOT appear valid.")

    # 4. Check Point Provisioning by components in SSOT
    print("\nChecking point provisioning by components in SSOT...")
    for comp in system_config.components:
        provided_uuids: List[PointUUID] = []
        provider_attr_name = ""
        if isinstance(comp, MicrocontrollerComponentDefinition):
            provided_uuids = comp.points_provided
            provider_attr_name = "points_provided"
        elif isinstance(comp, (DriverComponentDefinition, GovernorComponentDefinition)):
            provided_uuids = comp.virtual_points_provided or []
            provider_attr_name = "virtual_points_provided"

        for p_uuid in provided_uuids:
            if p_uuid not in master_point_uuids:
                msg = (f"Component '{comp.id}' (type: {comp.type.value}) '{provider_attr_name}' lists "
                       f"PointUUID '{p_uuid}' which is not defined in the master points list.")
                errors["point_provision"].append(msg)
                all_checks_passed = False
            else:
                point_def = points_by_uuid_map.get(p_uuid)
                if point_def and point_def.data_source_layer.value != comp.type.value:
                    msg = (f"Component '{comp.id}' (type: {comp.type.value}) provides PointUUID '{p_uuid}', "
                           f"but PointDefinition's 'data_source_layer' is '{point_def.data_source_layer.value}'.")
                    errors["point_provision"].append(msg)
                    all_checks_passed = False
    if not errors["point_provision"]:
        print("   ✅ Point provisioning by components in SSOT appears consistent.")

    # 5. Check Command/Status Point Linkages in SSOT
    print("\nChecking command/readback point linkages in SSOT...")
    for p_uuid, point_def in points_by_uuid_map.items():
        # Check 'readback_point_uuid' for command points
        if point_def.readback_point_uuid:
            rb_uuid = point_def.readback_point_uuid
            if rb_uuid == p_uuid:
                msg = f"Point '{p_uuid}' ({point_def.name}): 'readback_point_uuid' cannot be its own UUID."
                errors["command_readback_link"].append(msg)
                all_checks_passed = False
            elif rb_uuid not in points_by_uuid_map:
                msg = (f"Point '{p_uuid}' ({point_def.name}): 'readback_point_uuid' references "
                       f"non-existent PointUUID '{rb_uuid}'.")
                errors["command_readback_link"].append(msg)
                all_checks_passed = False
            else:
                # Optional: Further checks on the nature of the linked points
                command_point = point_def
                readback_target_point = points_by_uuid_map[rb_uuid]

                if command_point.access != AccessMode.READ_WRITE:
                    msg = (f"Point '{p_uuid}' ({command_point.name}) has 'readback_point_uuid' set, "
                           f"but its access is '{command_point.access.value}', not '{AccessMode.READ_WRITE.value}'. "
                           f"Typically, points with readbacks are command/write points.")
                    # This might be a warning rather than a hard error depending on strictness
                    errors["command_readback_link"].append(msg)
                    # all_checks_passed = False # Decide if this is a fatal error

                if readback_target_point.access != AccessMode.READ_ONLY:
                    msg = (f"Point '{rb_uuid}' ({readback_target_point.name}), targeted by 'readback_point_uuid' from '{p_uuid}', "
                           f"has access '{readback_target_point.access.value}', not '{AccessMode.READ_ONLY.value}'. "
                           f"Readback points are typically read-only.")
                    # This might be a warning
                    errors["command_readback_link"].append(msg)
                    # all_checks_passed = False # Decide if this is a fatal error
                
                if readback_target_point.readback_point_uuid is not None:
                    msg = (f"Point '{rb_uuid}' ({readback_target_point.name}), targeted by 'readback_point_uuid' from '{p_uuid}', "
                           f"also has a 'readback_point_uuid' defined ('{readback_target_point.readback_point_uuid}'). "
                           f"A readback/status point should not itself point to another readback point.")
                    errors["command_readback_link"].append(msg)
                    all_checks_passed = False
        
        # The old logic for command_point_uuid (on status points pointing back to command) is removed
        # as PointDefinition no longer has command_point_uuid. The linkage is now one-way
        # from command point to its readback via readback_point_uuid.

    if not errors["command_readback_link"]:
        print("   ✅ Command/readback point linkages in SSOT appear consistent with 'readback_point_uuid'.")

    # Checks for internal consistency of component configs (e.g., initial_state, PWM point properties,
    # governor controller point properties) are now handled by Pydantic model validators
    # when `validate_component_configs` is called with the appropriate context.
    # If `validate_component_configs` passed, those checks are implicitly done.

    # --- Report Overall Results ---
    if not all_checks_passed:
        print("\n❌ Cross-Validation Failed!")
        for category, error_list in errors.items():
            if error_list:
                print(f"   --- Errors found in '{category}' checks ---")
                for error in error_list:
                    print(f"      - {error}")
    else:
        print("\n✅ All Cross-Validation Checks Passed (SSOT integrity and component UUID existence).")
        print("   (Detailed component-specific internal validations are handled by Pydantic models.)")
    return all_checks_passed

# --- Main Execution ---
def main():
    print(f"Running build script from CWD: {Path.cwd()}")
    system_config = validate_ssot(SSOT_FILE_PATH)
    if system_config is None:
        print("\nAborting build due to errors in SSOT file.")
        sys.exit(1)

    # Create points_by_uuid_map to pass as context for component config validation
    points_by_uuid_map = {point.uuid: point for point in system_config.points}

    components_ok, validated_component_configs = validate_component_configs(system_config, points_by_uuid_map)
    if not components_ok:
        print("\nAborting build due to errors in component configurations (see Pydantic errors above).")
        sys.exit(1)
    print(f"\nSuccessfully validated {len(validated_component_configs)} component configuration file(s) using Pydantic models.")

    # Perform remaining cross-SSOT validation checks
    cross_validation_ok = cross_validate_configs(system_config, validated_component_configs)
    if not cross_validation_ok:
        print("\nBuild process completed with cross-validation errors (see details above).")
        sys.exit(1)

    print("\n--- Generation Steps (Not Yet Implemented) ---")
    print("\nBuild process completed successfully!")


if __name__ == "__main__":
    print("--- Starting Mushroom System Build/Validation ---")
    main()
    print("\n--- Build/Validation Script Finished ---")
