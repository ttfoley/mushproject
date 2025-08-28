# build.py - Refactored with Builder pattern

import yaml
from pathlib import Path
from pydantic import ValidationError, BaseModel # BaseModel for type hinting
import sys
from typing import Optional, Dict, Any, Set, Tuple, List, get_args, get_origin, Union
import collections # Added for Counter
import json

# --- Add project root to sys.path for shared_libs imports ---
project_root = Path(__file__).parent.parent  # config_sources parent = project root
sys.path.insert(0, str(project_root))

# --- Model Imports ---
try:
    # Import from the new shared_libs location
    from shared_libs.config_models.core_ssot_models import (
        SystemDefinition, ComponentType, PointDefinition, PointUUID,
        AccessMode, FunctionGrouping,
        DriverComponentDefinition, GovernorComponentDefinition, MicrocontrollerComponentDefinition,
        ManualSourceComponentDefinition
    )
    from shared_libs.config_models.component_configs import (
        DriverConfig,
        GovernorConfig, MicrocontrollerConfig,
    )
    from shared_libs.config_models.secrets import InfrastructureSecrets

except ImportError as e:
    print(f"Error: Could not import required Pydantic models or PointUUID type: {e}")
    print("Make sure build.py is in config_sources/ and models are in shared_libs/config_models/")
    print("Ensure __init__.py exists in shared_libs/ and shared_libs/config_models/ directories.")
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

# --- Utility Classes ----

class UUIDUtils:
    """Utility class for UUID-related operations."""
    
    @staticmethod
    def extract_uuids_from_instance(instance: Optional[Any], uuids_set: Set[str]):
        """
        Recursively extracts UUIDs from a Pydantic model instance or iterable
        by checking if field annotations are PointUUID or generics containing PointUUID.
        """
        if instance is None:
            return

        if isinstance(instance, BaseModel):
            for field_name, field_definition in instance.model_fields.items():
                field_value = getattr(instance, field_name)
                annotation = field_definition.annotation

                origin = get_origin(annotation)
                args = get_args(annotation)

                if annotation is PointUUID:
                    if isinstance(field_value, str):
                        uuids_set.add(field_value)
                elif origin is Union and PointUUID in args:
                    if isinstance(field_value, str):
                        uuids_set.add(field_value)
                elif origin is list and args and args[0] is PointUUID:
                    if isinstance(field_value, list):
                        for item in field_value:
                            if isinstance(item, str):
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
                    UUIDUtils.extract_uuids_from_instance(field_value, uuids_set)
                elif isinstance(field_value, list): # Recurse for lists that might contain Pydantic models
                    for item in field_value:
                        UUIDUtils.extract_uuids_from_instance(item, uuids_set)
                elif isinstance(field_value, dict): # Recurse for dict values if they aren't PointUUID directly
                    for value_in_dict in field_value.values():
                        UUIDUtils.extract_uuids_from_instance(value_in_dict, uuids_set)
        elif isinstance(instance, list):
            for item in instance:
                UUIDUtils.extract_uuids_from_instance(item, uuids_set)
        elif isinstance(instance, dict):
            for value in instance.values():
                UUIDUtils.extract_uuids_from_instance(value, uuids_set)

    @staticmethod
    def extract_driver_point_uuids(config: DriverConfig) -> Set[str]:
        uuids = set()
        UUIDUtils.extract_uuids_from_instance(config, uuids)
        return uuids

    @staticmethod
    def extract_microcontroller_point_uuids(config: MicrocontrollerConfig) -> Set[str]:
        uuids = set()
        UUIDUtils.extract_uuids_from_instance(config, uuids)
        return uuids

    @staticmethod
    def extract_governor_point_uuids(config: GovernorConfig) -> Set[str]:
        uuids = set()
        UUIDUtils.extract_uuids_from_instance(config, uuids)
        return uuids


class TopicGenerator:
    """Generates MQTT topics based on ADR-20 specification."""
    
    def __init__(self, system_config: SystemDefinition):
        self.system_config = system_config
        self.global_prefix = system_config.global_settings.mqtt_topic_prefix
        # Build component lookup maps
        self.component_by_id = {comp.id: comp for comp in system_config.components}
        # Build point provider lookup map
        self.point_provider_map = self._build_point_provider_map()
        
    def _build_point_provider_map(self) -> Dict[PointUUID, str]:
        """Build a map from point UUID to the component ID that provides it."""
        provider_map = {}
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
        """Generate full MQTT topic for a given point according to ADR-20."""
        source_component_id = self._get_source_component_id(point)
        
        if point.function_grouping == FunctionGrouping.SENSOR:
            # mush/c1/sensors/sht85_0_fc/degf
            units_slug = self._slugify(point.units)
            return f"{self.global_prefix}{source_component_id}/sensors/{point.topic_originator_slug}/{units_slug}"
            
        elif point.function_grouping == FunctionGrouping.ACTUATOR:
            # mush/c2/actuators/humidifier/readback
            return f"{self.global_prefix}{source_component_id}/actuators/{point.topic_device_slug}/readback"
            
        elif point.function_grouping == FunctionGrouping.STATUS:
            # mush/c2/statuses/wifi_uptime
            return f"{self.global_prefix}{source_component_id}/statuses/{point.topic_status_slug}"
            
        elif point.function_grouping == FunctionGrouping.COMMAND:
            # mush/temperature_driver_fruiting/commands/c2/heatingpad/write
            target_component_id = self._get_command_target_component_id(point)
            return f"{self.global_prefix}{source_component_id}/commands/{target_component_id}/{point.topic_directive_slug}/write"
        
        else:
            raise ValueError(f"Unknown function_grouping: {point.function_grouping}")
            
    def _get_source_component_id(self, point: PointDefinition) -> str:
        """Find which component provides this point."""
        component_id = self.point_provider_map.get(point.uuid)
        if component_id is None:
            raise ValueError(f"No component found that provides point UUID: {point.uuid}")
        return component_id
        
    def _get_command_target_component_id(self, point: PointDefinition) -> str:
        """For command points, find the target component from controls_ relationships."""
        source_component_id = self._get_source_component_id(point)
        source_component = self.component_by_id.get(source_component_id)
        
        if source_component is None:
            raise ValueError(f"Source component not found: {source_component_id}")
            
        # For manual command points, use the target_component field if available
        if isinstance(source_component, ManualSourceComponentDefinition) and point.target_component:
            return point.target_component
            
        # Find the target component based on what this component controls
        if isinstance(source_component, DriverComponentDefinition):
            return source_component.controls_microcontroller
        elif isinstance(source_component, GovernorComponentDefinition):
            # For governors, we need to find which microcontroller the controlled driver controls
            if len(source_component.controls_drivers) != 1:
                raise ValueError(f"Governor {source_component_id} controls multiple drivers, cannot determine single target")
            controlled_driver_id = source_component.controls_drivers[0]
            controlled_driver = self.component_by_id.get(controlled_driver_id)
            if isinstance(controlled_driver, DriverComponentDefinition):
                return controlled_driver.controls_microcontroller
            else:
                raise ValueError(f"Governor {source_component_id} controls non-driver component: {controlled_driver_id}")
        elif isinstance(source_component, ManualSourceComponentDefinition):
            # Manual command points must have target_component specified
            if not point.target_component:
                raise ValueError(f"Manual command point {point.uuid} ({point.name}) is missing required 'target_component' field")
            # This should never be reached since we check for target_component above, but keeping for safety
            raise ValueError(f"Manual command point {point.uuid} ({point.name}) has no target_component specified")
            
        else:
            raise ValueError(f"Command point {point.uuid} is sourced by component type that doesn't control other components: {type(source_component)}")
            
    def _slugify(self, text: str) -> str:
        """Convert text to URL-safe slug."""
        import re
        # Convert to lowercase and replace non-alphanumeric characters with underscores
        slug = re.sub(r'[^a-zA-Z0-9]+', '_', text.lower())
        # Remove leading/trailing underscores
        slug = slug.strip('_')
        return slug
        
    def generate_all_topics(self) -> Dict[PointUUID, str]:
        """Generate topics for all points in the system."""
        topics = {}
        for point in self.system_config.points:
            try:
                topic = self.generate_topic_for_point(point)
                topics[point.uuid] = topic
            except Exception as e:
                print(f"❌ Error generating topic for point {point.uuid} ({point.name}): {e}")
                raise
        return topics


class FileUtils:
    """Utility class for file operations."""
    
    @staticmethod
    def read_yaml(file_path: Path) -> Optional[Dict]:
        """Safely reads and parses a YAML file."""
        try:
            with open(file_path, 'r') as file:
                loaded_data = yaml.safe_load(file)
                if loaded_data is None:
                    print(f"❌ Error: YAML file '{file_path}' is empty or invalid.")
                    return None
                return loaded_data
        except yaml.YAMLError as e:
            print(f"❌ Error parsing YAML file '{file_path}':\n{e}")
            return None
        except Exception as e:
            print(f"❌ An unexpected error occurred loading '{file_path}': {e}")
            return None
    
    @staticmethod
    def write_json(file_path: Path, data: Dict):
        """Writes data to a JSON file."""
        try:
            with open(file_path, 'w') as file:
                json.dump(data, file, indent=2)
            print(f"✅ Successfully wrote to {file_path}")
            return True
        except Exception as e:
            print(f"❌ Error writing to {file_path}: {e}")
            return False
            
    @staticmethod
    def write_text(file_path: Path, content: str):
        """Writes string content to a text file."""
        try:
            with open(file_path, 'w') as file:
                file.write(content)
            print(f"✅ Successfully wrote to {file_path}")
            return True
        except Exception as e:
            print(f"❌ Error writing to {file_path}: {e}")
            return False


# ---- Validation Components ----

class SSOTValidator:
    """Validates the SSOT YAML file."""
    
    def __init__(self, file_path: Path):
        self.file_path = file_path
        
    def validate(self) -> Optional[SystemDefinition]:
        """Loads and validates the main SSOT YAML file."""
        print(f"\n--- Validating SSOT File: {self.file_path} ---")
        if not self.file_path.is_file():
            print(f"❌ Error: SSOT file not found at '{self.file_path}'")
            return None
            
        loaded_data = FileUtils.read_yaml(self.file_path)
        if loaded_data is None:
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


class ComponentConfigValidator:
    """Validates component configuration files."""
    
    def __init__(self, system_config: SystemDefinition, config_base_dir: Path, infrastructure_config: Optional[Dict[str, Any]] = None, secrets_model: Optional[InfrastructureSecrets] = None):
        self.system_config = system_config
        self.config_base_dir = config_base_dir
        self.infrastructure_config = infrastructure_config
        self.secrets_model = secrets_model
        self.component_model_map = {
            ComponentType.DRIVER: DriverConfig,
            ComponentType.GOVERNOR: GovernorConfig,
            ComponentType.MICROCONTROLLER: MicrocontrollerConfig,
        }
    
    def validate(self, points_by_uuid_map: Dict[PointUUID, PointDefinition]) -> Tuple[bool, Dict[str, Any]]:
        """
        Loads and validates specific config files for each component listed in the SSOT.
        Passes context to Pydantic models for cross-referential validation.
        """
        print("\n--- Validating Component Configuration Files ---")
        all_components_valid = True
        validated_configs = {}
        for component in self.system_config.components:
            print(f"\nValidating component: id='{component.id}', type='{component.type.value}'")
            
            # Skip config file loading if component.config_file is None
            if component.config_file is None:
                if component.type == ComponentType.MANUAL: # Or any other type that legitimately has no config file
                    print(f"   Component type '{component.type.value}' with ID '{component.id}' does not have a config file. Skipping file validation.")
                    continue 
                else:
                    print(f"   Note: Component type '{component.type.value}' with ID '{component.id}' has no config_file specified. Skipping file validation.")
                    continue

            component_config_path_str = component.config_file # At this point, component.config_file is not None
            component_config_path = self.config_base_dir / component_config_path_str # This should now be safe

            if not component_config_path.is_file():
                print(f"❌ Error: Config file not found at '{component_config_path}'")
                all_components_valid = False
                continue
            config_model = self.component_model_map.get(component.type)
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
                
                # No string substitution for microcontrollers; secrets are injected via validation context
                if component.type == ComponentType.MICROCONTROLLER:
                    print(f"   DEBUG: Skipping placeholder substitution for microcontroller; using secrets model via validation context.")
                
                # Pass context to the model validation
                validation_context = {"points_by_uuid_map": points_by_uuid_map, "component_id": component.id, "infrastructure_secrets": self.secrets_model}
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


class CrossValidator:
    """Performs cross-validation checks between components."""
    
    def __init__(self, system_config: SystemDefinition):
        self.system_config = system_config
        
    def validate(self, validated_components: Dict[str, Any]) -> bool:
        """
        Performs cross-validation checks primarily focused on SSOT integrity and
        existence of referenced UUIDs. More detailed component-specific internal
        consistency checks are now handled by Pydantic model validators.
        """
        print("\n--- Performing Cross-Validation ---")
        all_checks_passed = True
        errors: Dict[str, List[str]] = {
            "point_uuid_ref": [], "component_id_ref": [], "hierarchy_ref": [],
            "uniqueness": [], "point_provision": [], "command_readback_link": [],
            "orphaned_points": [], "multiply_provided_points": [] # New error categories
        }

        master_point_uuids = {point.uuid for point in self.system_config.points}
        points_by_uuid_map = {point.uuid: point for point in self.system_config.points}
        master_component_ids = {comp.id for comp in self.system_config.components}
        master_hierarchy_levels = set(self.system_config.command_hierarchy)

        # 1. Check Point UUID references in component configs (ensure they exist in SSOT)
        print("\nChecking Point UUID references in component configs against SSOT master list...")
        for component_id, config_object in validated_components.items():
            component_def = next((comp for comp in self.system_config.components if comp.id == component_id), None)
            if not component_def: continue
            component_type_val = component_def.type.value
            component_config_file = component_def.config_file

            referenced_uuids_in_component = set()
            if isinstance(config_object, DriverConfig):
                referenced_uuids_in_component = UUIDUtils.extract_driver_point_uuids(config_object)
            elif isinstance(config_object, MicrocontrollerConfig):
                referenced_uuids_in_component = UUIDUtils.extract_microcontroller_point_uuids(config_object)
            elif isinstance(config_object, GovernorConfig):
                referenced_uuids_in_component = UUIDUtils.extract_governor_point_uuids(config_object)

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
        point_names = [p.name for p in self.system_config.points]
        duplicate_point_names = {name for name in point_names if point_names.count(name) > 1}
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

        # 3. Check 'writable_by', 'controls_microcontroller', 'controls_drivers' in SSOT
        print("\nChecking component/hierarchy references in SSOT ('writable_by', 'controls_')...")
        for point in self.system_config.points:
            if point.writable_by:
                for writer_id in point.writable_by:
                    if writer_id not in master_component_ids and writer_id not in master_hierarchy_levels:
                        msg = (f"Point '{point.uuid}' ({point.name}): 'writable_by' item '{writer_id}' "
                               f"is not a defined component ID or command hierarchy level.")
                        errors["hierarchy_ref"].append(msg)
                        all_checks_passed = False
        for comp in self.system_config.components:
            if isinstance(comp, DriverComponentDefinition):
                if comp.controls_microcontroller not in master_component_ids:
                    msg = (f"DriverComponent '{comp.id}' 'controls_microcontroller' references "
                           f"undefined component ID '{comp.controls_microcontroller}'.")
                    errors["component_id_ref"].append(msg)
                    all_checks_passed = False
                else:
                    controlled_comp_type = next((c.type for c in self.system_config.components if c.id == comp.controls_microcontroller), None)
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
                        controlled_comp_type = next((c.type for c in self.system_config.components if c.id == driver_id), None)
                        if controlled_comp_type != ComponentType.DRIVER:
                            msg = (f"GovernorComponent '{comp.id}' 'controls_drivers' references '{driver_id}' "
                                   f"which is type '{controlled_comp_type.value if controlled_comp_type else 'Unknown'}' not '{ComponentType.DRIVER.value}'.")
                            errors["component_id_ref"].append(msg)
                            all_checks_passed = False
        if not errors["hierarchy_ref"] and not errors["component_id_ref"]:
            print("   ✅ 'writable_by' and 'controls_' references in SSOT appear valid.")

        # 4. Check Point Provisioning by components in SSOT
        print("\nChecking point provisioning by components in SSOT...")
        for comp in self.system_config.components:
            provided_uuids: List[PointUUID] = []
            provider_attr_name = ""
            if isinstance(comp, MicrocontrollerComponentDefinition):
                provided_uuids = comp.points_provided
                provider_attr_name = "points_provided"
            elif isinstance(comp, (DriverComponentDefinition, GovernorComponentDefinition, ManualSourceComponentDefinition)):
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

        # 6. Check for Orphaned and Multiply-Provided Points
        print("\nChecking for orphaned and multiply-provided points in SSOT...")
        # Now, all points in the master list are expected to be provided by some component.
        # We no longer filter out MANUAL_INPUT here, as they should be provided by a ManualSourceComponent.
        expected_system_provided_uuids: Set[PointUUID] = set(master_point_uuids)

        all_claimed_provided_uuids_list: List[PointUUID] = []
        for comp in self.system_config.components:
            if isinstance(comp, MicrocontrollerComponentDefinition):
                all_claimed_provided_uuids_list.extend(comp.points_provided)
            elif isinstance(comp, (DriverComponentDefinition, GovernorComponentDefinition, ManualSourceComponentDefinition)):
                if comp.virtual_points_provided: # Ensure it's not None
                    all_claimed_provided_uuids_list.extend(comp.virtual_points_provided)
        
        all_claimed_provided_uuids_set = set(all_claimed_provided_uuids_list)

        # Check for orphaned points (defined, but not claimed by any component)
        orphaned_uuids = expected_system_provided_uuids - all_claimed_provided_uuids_set
        if orphaned_uuids:
            for o_uuid in orphaned_uuids:
                point_name = points_by_uuid_map[o_uuid].name if o_uuid in points_by_uuid_map else "N/A"
                msg = (f"Point UUID '{o_uuid}' (Name: {point_name}) is defined with a system data_source_layer "
                       f"but is not provided by any component in 'points_provided' or 'virtual_points_provided'.")
                errors["orphaned_points"].append(msg)
                all_checks_passed = False
        
        # Check for points claimed by more than one component
        uuid_counts = collections.Counter(all_claimed_provided_uuids_list)
        multiply_provided_uuids = {uuid for uuid, count in uuid_counts.items() if count > 1}
        if multiply_provided_uuids:
            for m_uuid in multiply_provided_uuids:
                providers = [comp.id for comp in self.system_config.components 
                             if (isinstance(comp, MicrocontrollerComponentDefinition) and m_uuid in comp.points_provided) or
                                (isinstance(comp, (DriverComponentDefinition, GovernorComponentDefinition)) and comp.virtual_points_provided and m_uuid in comp.virtual_points_provided)]
                point_name = points_by_uuid_map[m_uuid].name if m_uuid in points_by_uuid_map else "N/A"
                msg = (f"Point UUID '{m_uuid}' (Name: {point_name}) is provided by multiple components: {providers}.")
                errors["multiply_provided_points"].append(msg)
                all_checks_passed = False

        if not errors["orphaned_points"] and not errors["multiply_provided_points"]:
            print("   ✅ All system-provided points are uniquely claimed by a component.")
        elif not errors["orphaned_points"] and errors["multiply_provided_points"]: # Only multi-provided errors
            print("   ❌ Some points are claimed by multiple components (see details below).")
        elif errors["orphaned_points"] and not errors["multiply_provided_points"]: # Only orphaned errors
            print("   ❌ Some system-provided points are not claimed by any component (see details below).")
        else: # Both types of errors
            print("   ❌ Issues found with point provisioning: orphaned and/or multiply-provided points (see details below).")

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


# ---- Generator Components ----

class PointsRegistryGenerator:
    """Generates the global points registry JSON file."""
    
    def __init__(self, system_config: SystemDefinition, output_path: Path):
        self.system_config = system_config
        self.output_path = output_path
        
    def generate(self) -> bool:
        """Generates the global points registry JSON file."""
        print(f"\n--- Generating Global Points Registry ---")
        
        try:
            # Generate topics for all points
            topic_generator = TopicGenerator(self.system_config)
            topics_by_uuid = topic_generator.generate_all_topics()
            
            # Build the registry structure
            registry = {
                "metadata": {
                    "generated_at": "placeholder_timestamp",
                    "total_points": len(self.system_config.points),
                    "mqtt_topic_prefix": self.system_config.global_settings.mqtt_topic_prefix
                },
                "points": {}
            }
            
            # Add each point to the registry
            for point in self.system_config.points:
                point_data = {
                    "uuid": point.uuid,
                    "name": point.name,
                    "description": point.description,
                    "function_grouping": point.function_grouping.value,
                    "value_type": point.value_type.value,
                    "units": point.units,
                    "data_source_layer": point.data_source_layer.value,
                    "access": point.access.value,
                    "mqtt_topic": topics_by_uuid.get(point.uuid),
                    "persist_to_db": point.persist_to_db
                }
                
                # Add optional fields if they exist
                if point.validation_rules:
                    point_data["validation_rules"] = point.validation_rules.model_dump()
                if point.initial_value is not None:
                    point_data["initial_value"] = point.initial_value
                if point.readback_point_uuid:
                    point_data["readback_point_uuid"] = point.readback_point_uuid
                if point.writable_by:
                    point_data["writable_by"] = point.writable_by
                    
                registry["points"][point.uuid] = point_data
            
            # Write to file
            return FileUtils.write_json(self.output_path, registry)
            
        except Exception as e:
            print(f"❌ Error generating points registry: {e}")
            return False


class MicrocontrollerConfigGenerator:
    """Generates autogen_config.h for microcontrollers."""
    
    def __init__(self, system_config: SystemDefinition, output_dir: Path, infrastructure_config: Optional[Dict[str, Any]] = None):
        self.system_config = system_config
        self.output_dir = output_dir
        self.infrastructure_config = infrastructure_config
        
    def generate(self, validated_components: Dict[str, Any]) -> bool:
        """Generates autogen_config.h files for each microcontroller."""
        print(f"\n--- Microcontroller Config Header Generation ---")
        print(f"   Generating config headers in: {self.output_dir}")
        
        success = True
        microcontroller_components = [
            comp for comp in self.system_config.components 
            if comp.type == ComponentType.MICROCONTROLLER
        ]
        
        for component in microcontroller_components:
            microcontroller_id = component.id
            config = validated_components.get(microcontroller_id)
            
            if config is None:
                print(f"❌ No validated config found for microcontroller '{microcontroller_id}'")
                success = False
                continue
                
            print(f"   Generating header for microcontroller: {microcontroller_id}")
            
            try:
                header_content = self._generate_header_content(microcontroller_id, component, config)
                output_file = self.output_dir / f"autogen_config_{microcontroller_id}.h"
                
                if FileUtils.write_text(output_file, header_content):
                    print(f"   ✅ Generated: {output_file}")
                else:
                    print(f"   ❌ Failed to write: {output_file}")
                    success = False
                    
            except Exception as e:
                print(f"   ❌ Error generating header for {microcontroller_id}: {e}")
                success = False
                
        return success
        
    def _generate_header_content(self, microcontroller_id: str, 
                               component: MicrocontrollerComponentDefinition,
                               config: MicrocontrollerConfig) -> str:
        """Generates the content for the autogen_config.h file with C structs."""
        
        # Initialize topic generator for MQTT topics
        topic_generator = TopicGenerator(self.system_config)
        
        lines = []
        lines.append(f"// autogen_config.h")
        lines.append(f"// Auto-generated configuration header for microcontroller: {microcontroller_id}")
        lines.append(f"// Generated by build.py from system_definition.yaml and {microcontroller_id}_config.yaml")
        lines.append("")
        lines.append(f"#ifndef AUTOGEN_CONFIG_H")
        lines.append(f"#define AUTOGEN_CONFIG_H")
        lines.append("")
        
        # Device identification
        lines.append("// === Device Identification ===")
        lines.append(f'#define DEVICE_ID "{config.device_id}"')
        lines.append(f'#define DEVICE_DESCRIPTION "{config.description}"')
        
        # WiFi, MQTT, NTP settings using resolved infrastructure values
        lines.append(f'#define WIFI_SSID "{config.wifi.ssid}"')
        lines.append(f'#define WIFI_PASSWORD "{config.wifi.password}"')
        lines.append(f'#define MQTT_BROKER_ADDRESS "{config.mqtt.broker_address}"')
        lines.append(f'#define MQTT_BROKER_PORT {config.mqtt.broker_port}')
        lines.append(f'#define MQTT_USERNAME "{config.mqtt.username}"')
        lines.append(f'#define MQTT_PASSWORD "{config.mqtt.password}"')
        lines.append(f'#define MQTT_CLIENT_ID "{config.mqtt.client_id}"')
        lines.append("")
        
        # Global Settings  
        lines.append("// === Global Settings ===")
        lines.append(f'#define NTP_SERVER_ADDRESS "{config.ntp.address}"')
        lines.append(f'#define NTP_UTC_OFFSET_SECONDS {config.ntp.utc_offset_seconds}')
        lines.append(f'#define NTP_UPDATE_INTERVAL_MS {config.ntp.update_interval_ms}')
        lines.append(f'#define DEBUG_I2C_SCAN_ON_STARTUP {"true" if config.debug.i2c_scan_on_startup else "false"}  // Set to false for production builds')
        lines.append("")
        
        # Comprehensive timing constants
        lines.extend(self._generate_timing_constants(config))
        
        # FSM State Definitions
        lines.extend(self._generate_fsm_states(config))
        
        # I2C Configuration
        lines.append("// === I2C Configuration ===")
        if config.i2c:
            lines.append(f'#define I2C_SDA_PIN {config.i2c.sda_pin}')
            lines.append(f'#define I2C_SCL_PIN {config.i2c.scl_pin}')
            lines.append("")
        
        # Configuration Structs - Sensors or Actuators
        if config.i2c_sensors or config.dht_sensors or config.onewire_sensors:
            lines.append("// === Sensor Configuration Structs ===")
            lines.append('#include "sensors/SensorConfigs.h"  // Common sensor config structs (ADR-25)')
            lines.append("")
            lines.append("// === Sensor Configuration Instances ===")
            lines.append("")
            lines.extend(self._generate_sensor_structs(config, topic_generator))
        elif config.actuators:
            lines.append("// === Actuator Configuration Structs ===")
            lines.append('#include "actuators/ActuatorConfigs.h"  // Common actuator config structs (ADR-25)')
            lines.append("")
            lines.append("// === Actuator Configuration Instances ===")
            lines.append("")
            lines.extend(self._generate_actuator_structs(config))
        
        # System status points
        lines.extend(self._generate_status_points(config))
        
        # Close header guard
        lines.append(f"#endif // AUTOGEN_CONFIG_H")
        lines.append("")
        
        return "\n".join(lines)
    
    def _generate_timing_constants(self, config: MicrocontrollerConfig) -> List[str]:
        """Generate comprehensive timing constants"""
        lines = []
        lines.append("// === Timing Constants ===")
        
        timing = config.timing
        lines.append(f'#define PUBLISH_INTERVAL_MS {timing.publish_interval_ms}')
        lines.append(f'#define WIFI_CONNECT_TIMEOUT_MS {timing.wifi_connect_timeout_ms}')
        lines.append(f'#define MQTT_CONNECT_TIMEOUT_MS {timing.mqtt_connect_timeout_ms}')
        lines.append(f'#define NTP_SYNC_TIMEOUT_MS {timing.ntp_sync_timeout_ms}')
        lines.append(f'#define SENSOR_AND_STATUS_PUBLISH_INTERVAL_MS {timing.sensor_and_status_publish_interval_ms}')
        lines.append(f'#define MAX_TIME_NO_PUBLISH_MS {timing.max_time_no_publish_ms}')
        lines.append(f'#define STATUS_PUBLISH_INTERVAL_MS {timing.status_publish_interval_ms}')
        lines.append(f'#define MAINTENANCE_RESTART_INTERVAL_MS {timing.maintenance_restart_interval_ms}')
        lines.append(f'#define PERIODIC_CHECKS_INTERVAL_MS {timing.periodic_checks_interval_ms}')
        
        # Add OUTPUT_REPUBLISH_FREQUENCY_MS if present (for actuator controllers)
        if timing.output_republish_frequency_ms:
            lines.append(f'#define OUTPUT_REPUBLISH_FREQUENCY_MS {timing.output_republish_frequency_ms}')
        
        lines.append("")
        
        # FSM and Connection Configuration
        lines.append("// === FSM and Connection Configuration ===")
        lines.append(f'#define MAX_WIFI_ATTEMPTS {timing.max_wifi_attempts}')
        lines.append(f'#define WIFI_ATTEMPT_TIMEOUT_MS {timing.wifi_attempt_timeout_ms}')
        lines.append(f'#define MAX_NTP_ATTEMPTS {timing.max_ntp_attempts}')
        lines.append(f'#define NTP_ATTEMPT_TIMEOUT_MS {timing.ntp_attempt_timeout_ms}')
        lines.append(f'#define MQTT_CONNECT_RETRY_INTERVAL_MS {timing.mqtt_retry_delay_ms}')
        lines.append(f'#define NTP_LOOP_UPDATE_INTERVAL_MS {timing.ntp_loop_update_interval_ms}')
        lines.append(f'#define DEBUG_QUEUE_INTERVAL_MS {timing.debug_queue_interval_ms}')
        lines.append("")
        
        # Delay and Timing Constants
        lines.append("// === Delay and Timing Constants ===")
        lines.append(f'#define MQTT_RETRY_DELAY_MS {timing.mqtt_retry_delay_ms}')
        lines.append(f'#define RESTART_DELAY_MS {timing.restart_delay_ms}')
        lines.append(f'#define MAIN_LOOP_DELAY_MS {timing.main_loop_delay_ms}')
        lines.append("")
                    
        return lines
    
    def _generate_fsm_states(self, config: MicrocontrollerConfig) -> List[str]:
        """Generate FSM state enum"""
        lines = []
        lines.append("// === FSM State Definitions (ADR-17, ADR-22) ===")
        lines.append("// Note: This enum will be used by common FSM utilities")
        lines.append("//All states in FsmUtils.h must be defined here, even if they are not used in this controller.")
        lines.append("typedef enum {")
        
        if config.fsm and config.fsm.states:
            for i, state in enumerate(config.fsm.states):
                if i == len(config.fsm.states) - 1:
                    lines.append(f"    {state}             // {self._get_state_comment(state)}")
                else:
                    lines.append(f"    {state},           // {self._get_state_comment(state)}")
        
        lines.append("} FsmState;")
        lines.append("")
        
        return lines
    
    def _get_state_comment(self, state: str) -> str:
        """Get comment for FSM state"""
        comments = {
            "SETUP_HW": "Hardware initialization (done in setup())",
            "CONNECT_WIFI": "WiFi connection",
            "SYNC_NTP": "NTP synchronization", 
            "CONNECT_MQTT": "MQTT broker connection",
            "PUBLISH_BOOT_STATUS": "Publish boot status (restart reason) - runs once after MQTT connection",
            "PROCESS_COMMANDS": "Process actuator commands",
            "READ_SENSORS": "Read sensor values and queue for publishing",
            "PUBLISH_DATA": "Publish data from publish queue",
            "OPERATIONAL_PERIODIC_CHECKS": "Periodic maintenance tasks",
            "WAIT": "Idle state, check what needs to be done",
            "RESTART": "Restart the controller"
        }
        return comments.get(state, "")
    
    def _generate_sensor_structs(self, config: MicrocontrollerConfig, topic_generator) -> List[str]:
        """Generate C struct definitions for sensors"""
        lines = []
        
        # I2C sensors (SHT85, BME280, SCD4X)
        if config.i2c_sensors:
            for sensor in config.i2c_sensors:
                if hasattr(sensor, 'type') and sensor.type == "SHT85":
                    lines.extend(self._generate_sht85_struct(sensor))
                elif hasattr(sensor, 'type') and sensor.type == "BME280":
                    lines.extend(self._generate_bme280_struct(sensor))
                elif hasattr(sensor, 'type') and sensor.type == "SCD4X":
                    lines.extend(self._generate_scd4x_sensor_struct(sensor))
        
        # DHT22 sensors
        if config.dht_sensors:
            for sensor in config.dht_sensors:
                lines.extend(self._generate_dht22_struct(sensor))
        
        # DS18B20 sensors  
        if config.onewire_sensors:
            for sensor in config.onewire_sensors:
                lines.extend(self._generate_ds18b20_struct(sensor))
        
        return lines
    
    def _generate_sht85_struct(self, sensor) -> List[str]:
        """Generate SHT85Config struct"""
        lines = [
            f"// SHT85 Sensor Instance",
            f"const SHT85Config {sensor.instance_name}_CONFIG = {{",
            f'    .point_name = "{sensor.point_name}",',
            f'    .publish_interval_ms = SENSOR_AND_STATUS_PUBLISH_INTERVAL_MS,',
            f'    .main_loop_delay_ms = MAIN_LOOP_DELAY_MS,',
            f'    .max_time_no_publish_ms = MAX_TIME_NO_PUBLISH_MS,',
            f'    .address = {hex(sensor.address)},',
            f'    .c_to_f = {"true" if sensor.c_to_f else "false"},',
            f'    .temp_topic = "mush/c1/sensors/fruitingchamber_sht85-0/degf",',
            f'    .temp_uuid = "{sensor.temperature_uuid}",',
            f'    .humidity_topic = "mush/c1/sensors/fruitingchamber_sht85-0/percent_rh",',
            f'    .humidity_uuid = "{sensor.humidity_uuid}"',
            "};",
            ""
        ]
        return lines
    
    def _generate_bme280_struct(self, sensor) -> List[str]:
        """Generate BME280Config struct"""
        lines = [
            f"// BME280 Sensor Instance",
            f"const BME280Config {sensor.instance_name}_CONFIG = {{",
            f'    .point_name = "{sensor.point_name}",',
            f'    .publish_interval_ms = SENSOR_AND_STATUS_PUBLISH_INTERVAL_MS,',
            f'    .main_loop_delay_ms = MAIN_LOOP_DELAY_MS,',
            f'    .max_time_no_publish_ms = MAX_TIME_NO_PUBLISH_MS,',
            f'    .address = {hex(sensor.address)},',
            f'    .c_to_f = {"true" if sensor.c_to_f else "false"},',
            f'    .temp_topic = "mush/c1/sensors/fruitingchamber_bme280-1/degf",',
            f'    .temp_uuid = "{sensor.temperature_uuid}",',
            f'    .humidity_topic = "mush/c1/sensors/fruitingchamber_bme280-1/percent_rh",',
            f'    .humidity_uuid = "{sensor.humidity_uuid}",',
            f'    .pressure_topic = "mush/c1/sensors/fruitingchamber_bme280-1/pascal",',
            f'    .pressure_uuid = "{sensor.pressure_uuid}"',
            "};",
            ""
        ]
        return lines
    
    def _generate_dht22_struct(self, sensor) -> List[str]:
        """Generate DHT22Config struct"""
        lines = [
            f"// DHT22 Sensor Instance",
            f"const DHT22Config {sensor.instance_name}_CONFIG = {{",
            f'    .point_name = "{sensor.point_name}",',
            f'    .publish_interval_ms = SENSOR_AND_STATUS_PUBLISH_INTERVAL_MS,',
            f'    .main_loop_delay_ms = MAIN_LOOP_DELAY_MS,',
            f'    .max_time_no_publish_ms = MAX_TIME_NO_PUBLISH_MS,',
            f'    .pin = {sensor.pin},',
            f'    .c_to_f = {"true" if sensor.c_to_f else "false"},',
            f'    .temp_topic = "mush/c1/sensors/outside_dht-0/degf",',
            f'    .temp_uuid = "{sensor.temperature_uuid}",',
            f'    .humidity_topic = "mush/c1/sensors/outside_dht-0/percent_rh",',
            f'    .humidity_uuid = "{sensor.humidity_uuid}"',
            "};",
            ""
        ]
        return lines
    
    def _generate_ds18b20_struct(self, sensor) -> List[str]:
        """Generate DS18B20Config struct"""
        lines = [
            f"// DS18B20 Sensor Instance",
            f"const DS18B20Config {sensor.instance_name}_CONFIG = {{",
            f'    .point_name = "{sensor.point_name}",',
            f'    .publish_interval_ms = SENSOR_AND_STATUS_PUBLISH_INTERVAL_MS,',
            f'    .main_loop_delay_ms = MAIN_LOOP_DELAY_MS,',
            f'    .max_time_no_publish_ms = MAX_TIME_NO_PUBLISH_MS,',
            f'    .pin = {sensor.pin},',
            f'    .resolution_bits = {sensor.resolution_bits},              // {sensor.resolution_bits}-bit resolution = 0.25°C precision, 187.5ms conversion',
            f'    .c_to_f = {"true" if sensor.c_to_f else "false"},',
            f'    .temp_topic = "mush/c1/sensors/fruitingchamber_ds18b20-{sensor.instance_name[-1]}/degf",',
            f'    .temp_uuid = "{sensor.temperature_uuid}"',
            "};",
            ""
        ]
        return lines
    
    def _generate_status_points(self, config: MicrocontrollerConfig) -> List[str]:
        """Generate system status point macros"""
        lines = []
        
        # WiFi Uptime
        wifi_uptime = config.status_points.wifi_uptime
        lines.extend([
            f"// System Info: {wifi_uptime.point_name}",
            f'#define POINT_NAME_{wifi_uptime.point_name} "{wifi_uptime.point_name}"',
            f'#define UUID_{wifi_uptime.point_name}_DATA "{wifi_uptime.uuid}"',
            f'#define TOPIC_{wifi_uptime.point_name}_DATA "{wifi_uptime.topic}"',
            ""
        ])
        
        # Last Restart Reason
        restart_reason = config.status_points.last_restart_reason
        lines.extend([
            f"// System Info: {restart_reason.point_name}",
            f'#define POINT_NAME_{restart_reason.point_name} "{restart_reason.point_name}"',
            f'#define UUID_{restart_reason.point_name}_DATA "{restart_reason.uuid}"',
            f'#define TOPIC_{restart_reason.point_name}_DATA "{restart_reason.topic}"',
            ""
        ])
        
        return lines
    
    def _generate_scd4x_sensor_struct(self, sensor) -> List[str]:
        """Generate C struct definition for SCD4X sensor"""
        lines = []
        lines.append(f"// {sensor.point_name} CO2/Temperature/Humidity Sensor Instance")
        lines.append(f"const SCD4xConfig {sensor.instance_name}_CONFIG = {{")
        lines.append(f'    .point_name = "{sensor.point_name}",')
        lines.append(f"    .publish_interval_ms = SENSOR_AND_STATUS_PUBLISH_INTERVAL_MS,")
        lines.append(f"    .main_loop_delay_ms = MAIN_LOOP_DELAY_MS,")
        lines.append(f"    .max_time_no_publish_ms = MAX_TIME_NO_PUBLISH_MS,")
        lines.append(f"    .address = 0x{sensor.address:02X},  // SCD4x standard I2C address")
        lines.append(f"    .c_to_f = {'true' if sensor.c_to_f else 'false'},")
        lines.append(f'    .co2_topic = "{sensor.co2_topic}",')
        lines.append(f'    .co2_uuid = "{sensor.co2_uuid}",')
        lines.append(f'    .temp_topic = "{sensor.temp_topic}",')
        lines.append(f'    .temp_uuid = "{sensor.temp_uuid}",')
        lines.append(f'    .humidity_topic = "{sensor.humidity_topic}",')
        lines.append(f'    .humidity_uuid = "{sensor.humidity_uuid}"')
        lines.append("};")
        lines.append("")
        return lines
    
    def _generate_actuator_structs(self, config: MicrocontrollerConfig) -> List[str]:
        """Generate C struct instances for actuators"""
        lines = []
        
        if not config.actuators:
            return lines
            
        for actuator in config.actuators:
            lines.append(f"// {actuator.point_name} Actuator Instance")
            lines.append(f"const ActuatorConfig {actuator.instance_name}_CONFIG = {{")
            lines.append(f"    .pin = {actuator.pin},")
            lines.append(f"    .pin_mode = {actuator.pin_mode},")
            lines.append(f"    .initial_state = {actuator.initial_state},")
            lines.append(f'    .point_name = "{actuator.point_name}",')
            lines.append(f'    .write_topic = "{actuator.write_topic}",')
            lines.append(f'    .readback_topic = "{actuator.readback_topic}",')
            lines.append(f'    .readback_uuid = "{actuator.readback_uuid}",')
            lines.append(f"    .republish_frequency_ms = OUTPUT_REPUBLISH_FREQUENCY_MS,")
            lines.append(f"    .max_time_no_publish_ms = MAX_TIME_NO_PUBLISH_MS")
            lines.append("};")
            lines.append("")
            
        return lines


# ---- Main Builder Class ----

class SystemBuilder:
    """Main builder class orchestrating the build process."""
    
    def __init__(self, ssot_file_path: Path, config_base_dir: Path = Path(".")):
        self.ssot_file_path = ssot_file_path
        self.config_base_dir = config_base_dir
        self.system_config = None
        self.validated_components = {}
        self.points_by_uuid_map = {}
        self.infrastructure_config = None
        self.secrets_model: Optional[InfrastructureSecrets] = None
        
    def load_infrastructure_with_secrets(self) -> Optional[Dict[str, Any]]:
        """Load infrastructure_definition.yaml and merge with secrets"""
        try:
            # Load infrastructure definition (optional for non-secret defaults)
            infra_path = self.config_base_dir / "infrastructure_definition.yaml"
            if not infra_path.exists():
                print(f"Infrastructure definition file not found: {infra_path}")
                infrastructure = {}
            else:
                with open(infra_path) as f:
                    infrastructure = yaml.safe_load(f) or {}
            
            # Load secrets (relative to project root)
            current_dir = Path.cwd()
            if current_dir.name == "config_sources":
                project_root = current_dir.parent
            else:
                project_root = current_dir
            
            secrets_path = project_root / "secrets" / "infrastructure_secrets.yaml"
            if not secrets_path.exists():
                print(f"Infrastructure secrets file not found: {secrets_path}")
                return None
                
            with open(secrets_path) as f:
                secrets_raw = yaml.safe_load(f) or {}
            
            # Backward-compat: convert flat keys (WIFI_SSID, MQTT_*) into grouped structure expected by InfrastructureSecrets
            if isinstance(secrets_raw, dict) and (
                'WIFI_SSID' in secrets_raw or 'MQTT_BROKER_ADDRESS' in secrets_raw
            ):
                secrets_converted = {
                    'wifi': {
                        'default': {
                            'ssid': secrets_raw.get('WIFI_SSID', ''),
                            'password': secrets_raw.get('WIFI_PASSWORD', ''),
                        },
                        'per_device': {}
                    },
                    'mqtt': {
                        'default': {
                            'broker_address': secrets_raw.get('MQTT_BROKER_ADDRESS', ''),
                            'broker_port': secrets_raw.get('MQTT_BROKER_PORT', 1883),
                            'username': secrets_raw.get('MQTT_USERNAME', ''),
                            'password': secrets_raw.get('MQTT_PASSWORD', ''),
                        },
                        'per_device': {}
                    }
                }
            else:
                secrets_converted = secrets_raw
            
            # Validate secrets model
            try:
                self.secrets_model = InfrastructureSecrets.model_validate(secrets_converted)
            except Exception as e:
                print(f"Error validating infrastructure_secrets.yaml: {e}")
                return None
            
            # Do not substitute secrets into component configs here
            return infrastructure
            
        except Exception as e:
            print(f"Error loading infrastructure with secrets: {e}")
            return None
    
    def validate_system(self) -> bool:
        """Validates the entire system configuration."""
        # Step 1: Load infrastructure with secrets
        self.infrastructure_config = self.load_infrastructure_with_secrets()
        if self.infrastructure_config is None:
            print("\nAborting build due to errors loading infrastructure configuration.")
            return False
            
        # Step 2: Validate SSOT
        ssot_validator = SSOTValidator(self.ssot_file_path)
        self.system_config = ssot_validator.validate()
        if self.system_config is None:
            print("\nAborting build due to errors in SSOT file.")
            return False
            
        # Create points_by_uuid_map
        self.points_by_uuid_map = {point.uuid: point for point in self.system_config.points}
            
        # Step 2: Validate Component Configs
        component_validator = ComponentConfigValidator(self.system_config, self.config_base_dir, self.infrastructure_config, self.secrets_model)
        components_ok, self.validated_components = component_validator.validate(self.points_by_uuid_map)
        if not components_ok:
            print("\nAborting build due to errors in component configurations.")
            return False
            
        # Step 3: Cross-Validate
        cross_validator = CrossValidator(self.system_config)
        cross_validation_ok = cross_validator.validate(self.validated_components)
        if not cross_validation_ok:
            return False
            
        print("\n✅ System validation completed successfully!")
        return True
        
    def generate_points_registry(self, output_path: Path) -> bool:
        """Generates the global points registry JSON file."""
        if self.system_config is None:
            print("❌ Cannot generate points registry. System config not validated.")
            return False
            
        registry_generator = PointsRegistryGenerator(self.system_config, output_path)
        return registry_generator.generate()
        
    def generate_microcontroller_configs(self, output_dir: Path) -> bool:
        """Generates autogen_config.h files for each microcontroller."""
        if self.system_config is None or not self.validated_components:
            print("❌ Cannot generate microcontroller configs. System config not validated.")
            return False
            
        microcontroller_generator = MicrocontrollerConfigGenerator(self.system_config, output_dir, self.infrastructure_config)
        return microcontroller_generator.generate(self.validated_components)
        
    def build(self, points_registry_path: Path, microcontroller_config_dir: Path) -> bool:
        """Orchestrates the entire build process."""
        print("--- Starting Mushroom System Build ---")
        
        # Step 1: Validate
        if not self.validate_system():
            return False
            
        # Step 2: Generate Points Registry
        if not self.generate_points_registry(points_registry_path):
            print("❌ Failed to generate points registry.")
            return False
            
        # Step 3: Generate Microcontroller Configs
        if not self.generate_microcontroller_configs(microcontroller_config_dir):
            print("❌ Failed to generate microcontroller configs.")
            return False
            
        print("\n✅ Build process completed successfully!")
        return True


# --- Main Execution ---
def main():
    print(f"Running build script from CWD: {Path.cwd()}")
    
    # Configuration - paths are relative to config_sources/ directory
    ssot_file_path = Path("system_definition.yaml")
    config_base_dir = Path(".")
    # Output paths - relative to project root
    project_root = Path(__file__).parent.parent
    points_registry_path = project_root / "control" / "global_points_registry.json"
    microcontroller_config_dir = Path("./microcontrollers/generated/")
    
    # Ensure output directories exist
    microcontroller_config_dir.mkdir(parents=True, exist_ok=True)
    
    # Create and run the builder
    builder = SystemBuilder(ssot_file_path, config_base_dir)
    success = builder.build(points_registry_path, microcontroller_config_dir)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
