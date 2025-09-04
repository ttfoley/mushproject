from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import yaml
from pydantic import ValidationError

from shared_libs.config_models.core_ssot_models import (
    SystemDefinition,
    ComponentType,
    PointDefinition,
    PointUUID,
)
from shared_libs.config_models.component_configs import (
    DriverConfig,
    GovernorConfig,
    MicrocontrollerConfig,
)
from shared_libs.config_models.secrets import InfrastructureSecrets


class ComponentConfigValidator:
    """Validates component YAMLs with Pydantic models and context."""

    def __init__(
        self,
        system_config: SystemDefinition,
        config_base_dir: Path,
        infrastructure_config: Optional[Dict[str, Any]] = None,
        secrets_model: Optional[InfrastructureSecrets] = None,
    ):
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
        print("\n--- Validating Component Configuration Files ---")
        all_components_valid = True
        validated_configs: Dict[str, Any] = {}

        for component in self.system_config.components:
            print(f"\nValidating component: id='{component.id}', type='{component.type.value}'")
            if component.config_file is None:
                print(f"   Note: Component '{component.id}' has no config file. Skipping file validation.")
                continue

            component_config_path = self.config_base_dir / component.config_file
            if not component_config_path.is_file():
                print(f"❌ Error: Config file not found at '{component_config_path}'")
                all_components_valid = False
                continue

            config_model = self.component_model_map.get(component.type)
            if not config_model:
                print(f"⚠️ Warning: No model defined for type '{component.type.value}'. Skipping validation for '{component.config_file}'.")
                continue

            try:
                with open(component_config_path, "r") as f:
                    component_data = yaml.safe_load(f)
                if component_data is None:
                    print(f"❌ Error: Component YAML '{component_config_path}' is empty or invalid.")
                    all_components_valid = False
                    continue
            except yaml.YAMLError as e:
                print(f"❌ Error parsing YAML for '{component_config_path}':\n{e}")
                all_components_valid = False
                continue
            except Exception as e:
                print(f"❌ Unexpected error loading '{component_config_path}': {e}")
                all_components_valid = False
                continue

            try:
                validation_context = {
                    "points_by_uuid_map": points_by_uuid_map,
                    "component_id": component.id,
                    "infrastructure_secrets": self.secrets_model,
                }
                validated_component_config = config_model.model_validate(component_data, context=validation_context)
                print(f"✅ Validation Successful for '{component.config_file}' using {config_model.__name__}.")
                validated_configs[component.id] = validated_component_config
            except ValidationError as e:
                print(f"❌ Pydantic Validation Failed for '{component.config_file}'!")
                print("   Error details:")
                print(e)
                all_components_valid = False
            except Exception as e:
                print(f"❌ Unexpected error during validation for '{component.config_file}': {e}")
                all_components_valid = False

        return all_components_valid, validated_configs


