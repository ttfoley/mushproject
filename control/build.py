# build.py

import yaml
from pathlib import Path
from pydantic import ValidationError
import sys
from typing import Optional, Dict, Any, Set, Tuple, List # Added Set, Tuple, Dict, Any, List

# --- Model Imports ---
# Assuming build.py is in the project root ('control/') and models are in common/config_models
# Adjust import if your structure is different
try:
    from common.config_models.core_ssot_models import SystemDefinition, ComponentType, PointDefinition
    from common.config_models.component_configs import (
        DriverConfig, WriteAction, StateCondition, ValueConstraintDefinition,
        StateTimeConstraintDefinition, DriverPWMOutputMapping, AnyAction,
        AnyConstraintDefinition, ConstraintDefinition, ConstraintGroup,
        TransitionDefinition, BaseConstraintDefinition, GovernorConfig, MicrocontrollerConfig # Added missing base/container models
    )
    from common.config_models.core_ssot_models import (
        DriverComponentDefinition, GovernorComponentDefinition, MicrocontrollerComponentDefinition
    )
    # Add imports for GovernorConfig, MicrocontrollerConfig etc. when defined
except ImportError as e:
    print(f"Error: Could not import required Pydantic models: {e}")
    print("Make sure build.py is in the project root ('control/') and models are in common/config_models/")
    print("Ensure __init__.py exists in common/ and common/config_models/ directories.")
    sys.exit(1) # Exit if core models can't be imported

# --- Configuration ---
SSOT_FILE_PATH = Path("system_definition.yaml")
# Base directory for relative config file paths within system_definition.yaml
# Assumes paths like 'config/drivers/...' are relative to the project root (where build.py is)
CONFIG_BASE_DIR = Path(".") # Current directory (should be 'control/')

# --- Model Mapping ---
# Map component type Enum/string to the Pydantic model used for its config file
# Add other mappings here when models are created
COMPONENT_MODEL_MAP = {
    ComponentType.DRIVER: DriverConfig,
    ComponentType.GOVERNOR: GovernorConfig,
    ComponentType.MICROCONTROLLER: MicrocontrollerConfig,
}

# --- Validation Functions ---

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

def validate_component_configs(system_config: SystemDefinition) -> Tuple[bool, Dict[str, Any]]:
    """
    Loads and validates specific config files for each component listed in the SSOT.
    Returns a tuple: (overall_success_boolean, dictionary_of_validated_configs)
    """
    print("\n--- Validating Component Configuration Files ---")
    all_components_valid = True
    validated_configs = {} # Dictionary to store validated model instances

    for component in system_config.components:
        print(f"\nValidating component: id='{component.id}', type='{component.type.value}'")
        component_config_path_str = component.config_file # Get the relative path string
        component_config_path = CONFIG_BASE_DIR / component_config_path_str # Construct path relative to CWD

        # Optional Debug Block (keep or remove as needed)
        # print(f"   DEBUG: Current Working Directory: {Path.cwd()}")
        # print(f"   DEBUG: Raw config path from SSOT: '{component_config_path_str}'")
        # try:
        #     resolved_path_debug = component_config_path.resolve()
        # except FileNotFoundError:
        #     resolved_path_debug = f"Error resolving path: {component_config_path}"
        # print(f"   DEBUG: Resolved absolute path being checked: '{resolved_path_debug}'")
        # print(f"   DEBUG: Checking existence of relative path: '{component_config_path}'")
        # --- END DEBUG BLOCK ---

        # 1. Check if the component config file exists
        if not component_config_path.is_file():
            print(f"❌ Error: Config file not found at '{component_config_path}'")
            all_components_valid = False
            continue # Skip to the next component in the loop

        # 2. Find the correct Pydantic model for this component type
        config_model = COMPONENT_MODEL_MAP.get(component.type)

        if not config_model:
            print(f"⚠️ Warning: No Pydantic model defined in COMPONENT_MODEL_MAP for type '{component.type.value}'. Skipping validation for '{component_config_path_str}'.")
            # Don't mark as invalid overall, just skip this component's config validation
            continue # Skip to the next component

        # 3. Load the component's YAML file
        try:
            print(f"   Loading component config: '{component_config_path}'")
            with open(component_config_path, 'r') as file:
                component_data = yaml.safe_load(file)
                if component_data is None:
                    print(f"❌ Error: Component YAML file '{component_config_path}' is empty or invalid.")
                    all_components_valid = False
                    continue # Skip to the next component
        except yaml.YAMLError as e:
            print(f"❌ Error parsing component YAML file '{component_config_path}':\n{e}")
            all_components_valid = False
            continue
        except Exception as e:
            print(f"❌ An unexpected error occurred loading '{component_config_path}': {e}")
            all_components_valid = False
            continue

        # 4. Validate the loaded data using the specific Pydantic model
        try:
            print(f"   Validating using {config_model.__name__} model...")
            validated_component_config = config_model(**component_data)
            print(f"✅ Validation Successful for '{component_config_path_str}' using {config_model.__name__}.")
            # Store the validated object using component ID as key
            validated_configs[component.id] = validated_component_config
        except ValidationError as e:
            print(f"❌ Pydantic Validation Failed for '{component_config_path_str}'!")
            print(f"   Please check this file against the {config_model.__name__} model.")
            print("   Error details:")
            print(e)
            all_components_valid = False
            # Continue to validate next component even if this one fails
        except Exception as e:
            print(f"❌ An unexpected error occurred during component Pydantic validation for '{component_config_path_str}': {e}")
            all_components_valid = False
            # Continue to validate next component

    # End of the loop through components
    return all_components_valid, validated_configs


# --- Helper function to extract UUIDs from DriverConfig ---
def extract_driver_point_uuids(config: DriverConfig) -> Set[str]:
    """Extracts all Point UUIDs referenced within a DriverConfig object."""
    uuids = set()
    if config.states:
        for state_def in config.states.values():
            if state_def.defining_conditions:
                for condition in state_def.defining_conditions:
                    if condition.point_uuid: uuids.add(condition.point_uuid)
            if state_def.entry_actions:
                for action in state_def.entry_actions:
                    if isinstance(action, WriteAction):
                        if action.point_uuid: uuids.add(action.point_uuid)
            if state_def.exit_actions:
                 for action in state_def.exit_actions:
                    if isinstance(action, WriteAction):
                        if action.point_uuid: uuids.add(action.point_uuid)

    if config.transitions:
        for from_state, to_states in config.transitions.items():
            for to_state, transition_def in to_states.items():
                if transition_def.constraint_groups:
                    for group in transition_def.constraint_groups:
                        if group.constraints:
                            for constraint in group.constraints:
                                definition = constraint.definition
                                if isinstance(definition, (ValueConstraintDefinition, StateTimeConstraintDefinition)):
                                    if definition.value_A_point_uuid: uuids.add(definition.value_A_point_uuid)
                                    if definition.comparand_B_point_uuid: uuids.add(definition.comparand_B_point_uuid)
                                # Add checks here if other constraint types reference points

    if config.pwm_outputs:
        for pwm_map in config.pwm_outputs:
            if pwm_map.input_point_uuid: uuids.add(pwm_map.input_point_uuid)
            if pwm_map.output_actuator_uuid: uuids.add(pwm_map.output_actuator_uuid)

    return uuids
def extract_microcontroller_point_uuids(config: MicrocontrollerConfig) -> Set[str]:
    """Extracts all Point UUIDs referenced within a MicrocontrollerConfig."""
    uuids = set()
    if config.i2c_devices:
        for device in config.i2c_devices:
            if device.point_uuids:
                uuids.update(device.point_uuids.values())
    if config.onewire_devices:
        for device in config.onewire_devices:
            if device.point_uuid:
                uuids.add(device.point_uuid)
    if config.dht_sensors:
        for sensor in config.dht_sensors:
            if sensor.point_uuids:
                uuids.update(sensor.point_uuids.values())
    if config.digital_outputs:
        for output in config.digital_outputs:
            if output.point_uuid: # This is the command point UUID
                uuids.add(output.point_uuid)
            # If we added status_point_uuid here later, uncomment below
            # if output.status_point_uuid: 
            #     uuids.add(output.status_point_uuid) 
    return uuids

def extract_governor_point_uuids(config: GovernorConfig) -> Set[str]:
    """Extracts all Point UUIDs referenced within a GovernorConfig."""
    uuids = set()
    if config.controllers:
        for controller_conf in config.controllers:
            # Check common fields first if any, then type-specific
            if hasattr(controller_conf, 'sensor_point_uuid'):
                uuids.add(controller_conf.sensor_point_uuid)
            if hasattr(controller_conf, 'target_setpoint_point_uuid'):
                uuids.add(controller_conf.target_setpoint_point_uuid)

            # BangBang Specific
            if hasattr(controller_conf, 'controller_type') and controller_conf.controller_type == 'bang_bang':
                 if hasattr(controller_conf, 'hysteresis_point_uuid'):
                    uuids.add(controller_conf.hysteresis_point_uuid)
                 if hasattr(controller_conf, 'output_command_point_uuid'):
                    uuids.add(controller_conf.output_command_point_uuid)
            # PID Specific
            elif hasattr(controller_conf, 'controller_type') and controller_conf.controller_type == 'pid':
                if hasattr(controller_conf, 'output_pwm_setpoint_point_uuid'):
                   uuids.add(controller_conf.output_pwm_setpoint_point_uuid)
                if hasattr(controller_conf, 'output_on_duration_point_uuid'):
                   uuids.add(controller_conf.output_on_duration_point_uuid)
                if hasattr(controller_conf, 'output_off_duration_point_uuid'):
                    uuids.add(controller_conf.output_off_duration_point_uuid)
                if hasattr(controller_conf, 'mode_command_point_uuid'):
                   uuids.add(controller_conf.mode_command_point_uuid)
            # Add elif for other controller types here...
    return uuids
# --- Cross-Validation Function ---
def cross_validate_configs(system_config: SystemDefinition, validated_components: Dict[str, Any]) -> bool:
    """Performs cross-validation checks between SSOT and component configs."""
    print("\n--- Performing Cross-Validation ---")
    all_checks_passed = True
    # Store errors by category
    cross_validation_errors = {
        "point_uuid": [],
        "component_id": [],
        "hierarchy": [],
        "internal": []
    }

    # --- Pre-computation for checks ---
    master_point_uuids = {point.uuid for point in system_config.points}
    master_component_details = {comp.id: comp.type for comp in system_config.components}
    master_hierarchy_levels = set(system_config.command_hierarchy)
    # --- End Pre-computation ---

    # 1. Check Point UUID references (as before)
    print("\nChecking Point UUID references in component configs...")
    point_uuid_errors_found = False
    for component_id, config_object in validated_components.items():
        component_def = next((comp for comp in system_config.components if comp.id == component_id), None)
        if not component_def: continue
        component_type = component_def.type.value
        component_config_file = component_def.config_file

        print(f"   Checking component '{component_id}' (type: {component_type})...") # Moved print here
        referenced_uuids = set()
        if isinstance(config_object, DriverConfig):
            referenced_uuids = extract_driver_point_uuids(config_object)
            
        elif isinstance(config_object, MicrocontrollerConfig): # <<< ADDED Check
            referenced_uuids = extract_microcontroller_point_uuids(config_object)
        elif isinstance(config_object, GovernorConfig):      # <<< ADDED Check
            referenced_uuids = extract_governor_point_uuids(config_object)
        # print(f"      Referenced UUIDs found: {referenced_uuids}") # Optional debug
        # Add elif for other component types here...

        for uuid in referenced_uuids:
            if uuid not in master_point_uuids:
                error_msg = f"Component '{component_id}' (type: {component_type}, config: {component_config_file}): References undefined Point UUID '{uuid}'."
                cross_validation_errors["point_uuid"].append(error_msg)
                all_checks_passed = False; point_uuid_errors_found = True # Set flag

    if not point_uuid_errors_found:
         print("   ✅ Point UUID references appear valid.")
    # --- End Point UUID Check ---


    # 2. Check Component ID references (as before)
    print("\nChecking component ID references (controls_*, writable_by)...")
    component_id_errors_found_flag = False
    # 2a. Relationships
    for component in system_config.components:
        component_id_making_ref = component.id # Component making the reference
        if isinstance(component, DriverComponentDefinition):
            referenced_id = component.controls_microcontroller
            expected_type = ComponentType.MICROCONTROLLER
            if referenced_id not in master_component_details:
                error_msg = f"Component '{component_id_making_ref}': 'controls_microcontroller' references undefined component ID '{referenced_id}'."
                cross_validation_errors["component_id"].append(error_msg)
                all_checks_passed = False; component_id_errors_found_flag=True
            elif master_component_details[referenced_id] != expected_type:
                error_msg = f"Component '{component_id_making_ref}': 'controls_microcontroller' references component '{referenced_id}' which has wrong type ({master_component_details[referenced_id].value}), expected {expected_type.value}."
                cross_validation_errors["component_id"].append(error_msg)
                all_checks_passed = False; component_id_errors_found_flag=True
        # Add elif for Governor etc.
    # 2b. writable_by Component IDs
    for point in system_config.points:
        if point.writable_by:
            for writer_id in point.writable_by:
                is_hierarchy = writer_id in master_hierarchy_levels
                is_component = writer_id in master_component_details
                if not is_hierarchy and not is_component:
                    error_msg = f"Point '{point.uuid}' ({point.name}): 'writable_by' list contains undefined component ID or hierarchy level '{writer_id}'."
                    cross_validation_errors["component_id"].append(error_msg)
                    all_checks_passed = False; component_id_errors_found_flag=True

    if not component_id_errors_found_flag:
         print("   ✅ Component ID references appear valid.")
    # --- End Component ID Check ---


    # 3. Check command hierarchy references (as before)
    print("\nChecking command hierarchy references (writable_by)...")
    hierarchy_errors_found_flag = False
    for point in system_config.points:
         if point.writable_by:
             for writer_id in point.writable_by:
                 is_hierarchy = writer_id in master_hierarchy_levels
                 is_component = writer_id in master_component_details
                 if not is_component and not is_hierarchy:
                     hierarchy_errors_found_flag = True # Error already logged in step 2b

    if not hierarchy_errors_found_flag:
         print("   ✅ Command hierarchy references in 'writable_by' appear valid.")
    # --- End Command Hierarchy Check ---


    # --- NEW: Check internal component references ---
    print("\nChecking internal component references (e.g., initial_state)...")
    internal_errors_found_flag = False
    for component_id, config_object in validated_components.items():
        component_def = next((comp for comp in system_config.components if comp.id == component_id), None)
        if not component_def: continue
        component_config_file = component_def.config_file

        # Check Driver Configs
        if isinstance(config_object, DriverConfig):
            # Check initial_state
            initial_state_name = config_object.initial_state
            defined_state_names = set(config_object.states.keys()) if config_object.states else set()
            if initial_state_name not in defined_state_names:
                error_msg = f"Component '{component_id}' (config: {component_config_file}): 'initial_state' ('{initial_state_name}') is not defined as a key in the 'states' dictionary {defined_state_names}."
                cross_validation_errors["internal"].append(error_msg)
                all_checks_passed = False
                internal_errors_found_flag = True
            
            if config_object.transitions:
                for from_state in config_object.transitions.keys():
                    if from_state not in defined_state_names:
                        error_msg = (
                            f"Component '{component_id}' (config: {component_config_file}): "
                            f"Transition defined FROM non-existent state '{from_state}'. "
                            f"Defined states are: {defined_state_names or '{}'}."
                        )
                        cross_validation_errors["internal"].append(error_msg)
                        all_checks_passed = False
                        internal_errors_found_flag = True
            # <<< END NEW CHECK 'from_state' >>>

            # <<< NEW CHECK: Validate 'to_state' keys in transitions >>>
            if config_object.transitions:
                for from_state, to_states_dict in config_object.transitions.items():
                    # Optional: Check if from_state is valid before proceeding (already checked above)
                    # if from_state not in defined_state_names: continue 
                    
                    if to_states_dict: # Check if there are transitions defined from this state
                        for to_state in to_states_dict.keys():
                            if to_state not in defined_state_names:
                                error_msg = (
                                    f"Component '{component_id}' (config: {component_config_file}): "
                                    f"Transition defined FROM '{from_state}' TO non-existent state '{to_state}'. "
                                    f"Defined states are: {defined_state_names or '{}'}."
                                )
                                cross_validation_errors["internal"].append(error_msg)
                                all_checks_passed = False
                                internal_errors_found_flag = True
            # <<< END NEW CHECK 'to_state' >>>

        # Add elif for GovernorConfig internal checks later...
        # elif isinstance(config_object, GovernorConfig):
            # e.g., check if sensor UUIDs used in PID exist
    if not internal_errors_found_flag:
        print("   ✅ Internal component references appear valid (initial_state, transition states checked).") # Updated message
    # --- End Internal Checks ---


    # --- Report Overall Results ---
    if not all_checks_passed:
        print("\n❌ Cross-Validation Failed!")
        # Print collected errors by category
        for category, errors in cross_validation_errors.items():
            if errors:
                print(f"   --- Errors found in {category} checks ---")
                for error in errors:
                    print(f"      - {error}")
    else:
        # Update final success message
        print("\n✅ All Cross-Validation Checks Passed (Points, Component IDs, Hierarchy Refs, Internal Refs checked).")

    return all_checks_passed
# --- Main Execution ---
def main():
    print(f"Running build script from CWD: {Path.cwd()}")

    # Step 1: Validate the main SSOT file
    print(f"Validating SSOT file: {SSOT_FILE_PATH}")
    system_config = validate_ssot(SSOT_FILE_PATH)
    if system_config is None:
        print("\nAborting build due to errors in SSOT file.")
        sys.exit(1)

    # Step 2: Validate individual component config files
    components_ok, validated_component_configs = validate_component_configs(system_config)
    if not components_ok:
        # Specific errors already printed in the function
        print("\nAborting build due to errors in component configurations.")
        sys.exit(1)
    print(f"\nSuccessfully validated {len(validated_component_configs)} component configuration file(s).")

    # Step 3: Perform Cross-validation
    cross_validation_ok = cross_validate_configs(system_config, validated_component_configs)
    if not cross_validation_ok:
        print("\nBuild process completed with cross-validation errors.")
        sys.exit(1)

    # Future steps: Generate runtime configs, Telegraf snippets etc.
    print("\n--- Generation Steps (Not Yet Implemented) ---")

    print("\nBuild process completed successfully!")


if __name__ == "__main__":
    print("--- Starting Mushroom System Build/Validation ---")
    main()
    print("\n--- Build/Validation Script Finished ---")