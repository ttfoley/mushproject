from pathlib import Path
from typing import Optional

from pydantic import ValidationError

from shared_libs.config_models.core_ssot_models import SystemDefinition


class SSOTValidator:
    """Validates the SSOT YAML file and returns a SystemDefinition model."""

    def __init__(self, file_path: Path):
        self.file_path = file_path

    def validate(self) -> Optional[SystemDefinition]:
        print(f"\n--- Validating SSOT File: {self.file_path} ---")
        if not self.file_path.is_file():
            print(f"❌ Error: SSOT file not found at '{self.file_path}'")
            return None

        try:
            import yaml
            with open(self.file_path, "r") as f:
                loaded_data = yaml.safe_load(f)
        except Exception as e:
            print(f"❌ Error loading SSOT YAML: {e}")
            return None

        if loaded_data is None:
            print("❌ Error: SSOT YAML is empty or invalid.")
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
            print(f"❌ An unexpected error occurred during SSOT validation: {e}")
            return None

from pathlib import Path
from typing import Optional

from pydantic import ValidationError

from shared_libs.config_models.core_ssot_models import SystemDefinition


class SSOTValidator:
    """Validates the SSOT YAML file and returns a SystemDefinition model."""

    def __init__(self, file_path: Path):
        self.file_path = file_path

    def validate(self) -> Optional[SystemDefinition]:
        print(f"\n--- Validating SSOT File: {self.file_path} ---")
        if not self.file_path.is_file():
            print(f"❌ Error: SSOT file not found at '{self.file_path}'")
            return None

        try:
            import yaml
            with open(self.file_path, "r") as f:
                loaded_data = yaml.safe_load(f)
        except Exception as e:
            print(f"❌ Error loading SSOT YAML: {e}")
            return None

        if loaded_data is None:
            print("❌ Error: SSOT YAML is empty or invalid.")
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
            print(f"❌ An unexpected error occurred during SSOT validation: {e}")
            return None


