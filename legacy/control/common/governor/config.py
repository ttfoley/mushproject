# control/common/governor/config.py

import json
import os
from typing import Dict, Any, Optional, List, Tuple

# Assuming uuid_database is correctly importable
# If not, adjust the path based on your project structure
# Option 1: If common/ is directly in PYTHONPATH
# from common.config.uuid_database import UUIDDatabase
# Option 2: Relative path (might be fragile depending on execution context)
try:
    from ..config.uuid_database import UUIDDatabase
except ImportError:
    # Fallback if the above fails, might need adjustment
    import sys
    # This assumes the script is run from somewhere like 'control/' directory
    # Or that 'control' is in PYTHONPATH
    sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
    from common.config.uuid_database import UUIDDatabase


class GovernorConfigurationError(Exception):
    """Custom exception for governor configuration errors."""
    pass

class GovernorConfiguration:
    """
    Loads, validates, and provides access to all configuration
    required for the Governor layer.
    """

    def __init__(self, governor_config_path: str):
        """
        Initializes the configuration loader.

        Args:
            governor_config_path: Path to the main governor_config.json file.

        Raises:
            FileNotFoundError: If the main governor config file doesn't exist.
            GovernorConfigurationError: For issues during loading or validation.
        """
        print(f"Initializing GovernorConfiguration with: {governor_config_path}")
        if not os.path.isfile(governor_config_path): # Use isfile for files
            raise FileNotFoundError(f"Governor configuration file not found: {governor_config_path}")

        self.governor_config_path = os.path.abspath(governor_config_path)
        self.config_dir = os.path.dirname(self.governor_config_path) # Absolute dir path

        # Internal storage for loaded configs
        self._raw_governor_config: Optional[Dict[str, Any]] = None
        self._mqtt_config: Optional[Dict[str, Any]] = None
        self._runner_config: Optional[Dict[str, Any]] = None
        self._point_manager_config: Optional[Dict[str, Any]] = None # Specific settings for GPM
        self._governor_points_config: Optional[Dict[str, Any]] = None # Processed governor points
        self._controllers_config: Optional[List[Dict[str, Any]]] = None # For potentially multiple controllers
        self._referenced_microc_config: Optional[Dict[str, Any]] = None # Store loaded microC config
        self._referenced_uuid_db_config: Optional[Dict[str, int]] = None # Store loaded UUID db mapping
        self._referenced_driver_configs: Dict[str, Dict[str, Any]] = {} # Store loaded driver configs by path

        # Helpers
        self._uuid_db: Optional[UUIDDatabase] = None
        self._all_point_addrs: set[str] = set() # Collect all known point addresses for validation

        # Load and validate immediately on creation
        try:
            self.load_config()
            print("Governor configuration loaded and validated successfully.")
        except Exception as e:
            # Chain the exception for better debugging
            raise GovernorConfigurationError(f"Failed to initialize GovernorConfiguration: {e}") from e


    def _resolve_path(self, path: str) -> str:
        """Resolves a path relative to the governor config directory."""
        if os.path.isabs(path):
            return path
        return os.path.abspath(os.path.join(self.config_dir, path))

    def _load_json_file(self, path: str, description: str) -> Dict[str, Any]:
        """Loads a JSON file with error handling."""
        resolved_path = self._resolve_path(path)
        print(f"Attempting to load {description} from: {resolved_path}")
        if not os.path.isfile(resolved_path):
            raise FileNotFoundError(f"{description} file not found at resolved path: {resolved_path} (original path: {path})")
        try:
            with open(resolved_path, 'r') as f:
                data = json.load(f)
            if not isinstance(data, dict):
                 raise GovernorConfigurationError(f"{description} file ({resolved_path}) must contain a JSON object.")
            print(f"Successfully loaded {description}.")
            return data
        except json.JSONDecodeError as e:
            raise GovernorConfigurationError(f"Error decoding JSON from {description} file {resolved_path}: {e}")
        except Exception as e:
            raise GovernorConfigurationError(f"Error loading {description} file {resolved_path}: {e}")

    def _validate_required_keys(self, config: Dict, keys: List[str], context: str):
        """Checks if all required keys are present in a config dict."""
        missing_keys = [key for key in keys if key not in config]
        if missing_keys:
            raise GovernorConfigurationError(f"Missing required keys in {context}: {', '.join(missing_keys)}")

    def _extract_point_addrs(self, data_structure: Any):
        """
        Recursively extracts all 'addr' string values found anywhere within
        a nested dictionary or list structure.
        """
        if isinstance(data_structure, dict):
            # Check if this dictionary itself contains the 'addr' key
            if "addr" in data_structure and isinstance(data_structure["addr"], str):
                addr = data_structure["addr"]
                # Optional: print when adding
                # print(f"DEBUG Extract: Adding address {addr}")
                self._all_point_addrs.add(addr)

            # Recurse into all values within this dictionary
            for value in data_structure.values():
                self._extract_point_addrs(value) # Recursive call

        elif isinstance(data_structure, list):
            # Recurse into all items within this list
            for item in data_structure:
                self._extract_point_addrs(item) # Recursive call
        # Ignore other types (like strings, numbers, booleans, etc.)


    def load_config(self):
        """
        Loads the main governor config and all referenced configs.
        Performs validation checks.
        """
        print(f"Loading Governor configuration from: {self.governor_config_path}")
        self._raw_governor_config = self._load_json_file(self.governor_config_path, "main governor config")


        # --- 1. Extract and Validate Top-Level Sections ---
        print("Validating top-level sections...")
        # Updated required key list
        required_top_level = ["mqtt", "runner", "control_strategies", "config_references"]
        self._validate_required_keys(self._raw_governor_config, required_top_level, "governor_config.json")

        self._mqtt_config = self._raw_governor_config["mqtt"]
        self._runner_config = self._raw_governor_config["runner"]
        # Updated assignment
        self._control_strategies_config = self._raw_governor_config["control_strategies"]
        self._point_manager_config = self._raw_governor_config.get("point_manager", {})

        assert isinstance(self._mqtt_config, dict), "'mqtt' section must be a dictionary."
        assert isinstance(self._runner_config, dict), "'runner' section must be a dictionary."
        # Updated check
        assert isinstance(self._control_strategies_config, list), "'control_strategies' must be a list."
        if not self._control_strategies_config:
             raise GovernorConfigurationError("'control_strategies' list cannot be empty.")

        self._validate_required_keys(self._mqtt_config, ["broker", "port", "username", "password", "client_id"], "mqtt config")
        self._validate_required_keys(self._runner_config, ["update_interval_seconds"], "runner config")

        print("Top-level sections validated.")
        # --- 2. Load Referenced Configs ---
        print("Loading referenced configurations...")
        references = self._raw_governor_config["config_references"]
        self._validate_required_keys(references, ["microcontroller_points", "uuid_database"], "config_references")

        # Load UUID DB FIRST - needed for UUID assignment/lookup
        uuid_db_path = references["uuid_database"]
        self._referenced_uuid_db_config = self._load_json_file(uuid_db_path, "UUID database")
        # Instantiate the UUIDDatabase helper class
        self._uuid_db = UUIDDatabase(db_path=self._resolve_path(uuid_db_path))
        print(f"UUIDDatabase instantiated using {self._resolve_path(uuid_db_path)}")

        # Load Microcontroller Points
        microc_path = references["microcontroller_points"]
        self._referenced_microc_config = self._load_json_file(microc_path, "microcontroller points")
        # Extract addresses from microC points
        self._extract_point_addrs(self._referenced_microc_config.get("microcontrollers", {}))
        print(f"Collected {len(self._all_point_addrs)} point addresses from microC config.")


        # Load Driver Configs (Optional, used for validation)
        driver_config_paths = references.get("driver_configs", [])
        if not isinstance(driver_config_paths, list):
             raise GovernorConfigurationError("'config_references.driver_configs' must be a list of paths.")

        for driver_path in driver_config_paths:
            try:
                resolved_driver_path = self._resolve_path(driver_path)
                print(f"DEBUG: Attempting to load driver config from resolved path: {resolved_driver_path}") # Keep this
                driver_conf = self._load_json_file(driver_path, f"driver config ({driver_path})")
                print(f"DEBUG: Successfully loaded driver config: {resolved_driver_path}") # Keep this
                self._referenced_driver_configs[resolved_driver_path] = driver_conf

                # *** Modify this part ***
                driver_points_data = driver_conf.get("points", {})
                driver_drivers_data = driver_points_data.get("drivers", {})
                print(f"DEBUG: Data passed to _extract_point_addrs for driver '{driver_path}': {driver_drivers_data}") # Print what's being passed
                self._extract_point_addrs(driver_drivers_data) # Call with the extracted data

            except FileNotFoundError:
                print(f"Warning: Optional driver config not found: {driver_path}. Skipping.")
            except GovernorConfigurationError as e:
                 print(f"Warning: Error loading optional driver config {driver_path}: {e}. Skipping.")
        print(f"Total point addresses collected after drivers: {len(self._all_point_addrs)}")

        print("Referenced configurations loaded.")

        # --- 3. Process Governor-Defined Points ---
        print("Processing governor-defined points...")
        self._governor_points_config = self._raw_governor_config.get("governor_points", {})
        if not isinstance(self._governor_points_config, dict):
             raise GovernorConfigurationError("'governor_points' section must be a dictionary.")

        for point_name, point_def in self._governor_points_config.items():
             self._validate_required_keys(point_def, ["addr", "value_type", "description"], f"governor_points.{point_name}")
             addr = point_def["addr"]
             if not isinstance(addr, str) or not addr:
                 raise GovernorConfigurationError(f"Address for governor point '{point_name}' must be a non-empty string.")
             if addr in self._all_point_addrs:
                 print(f"Warning: Governor-defined point address '{addr}' collides with an existing point address.")
                 # Decide on behavior: error out or allow override? Let's allow for now.

             # Get/Assign UUID using the helper class and save it back to the definition
             # This ensures the UUID DB file is updated if the point is new
             try:
                 point_def["UUID"] = self._uuid_db.get_uuid(addr)
                 print(f"Assigned/Retrieved UUID {point_def['UUID']} for governor point '{addr}' ({point_name})")
             except Exception as e:
                 raise GovernorConfigurationError(f"Failed to get UUID for governor point '{addr}': {e}")

             self._all_point_addrs.add(addr) # Add governor point address to the set

             # TODO: Add more validation for value_type, valid_range/valid_values, initial_value, publish settings etc.

        print("Governor-defined points processed.")
        print(f"Total point addresses collected after governor points: {len(self._all_point_addrs)}")


        # --- 4. Perform Cross-Config Validation ---
        print("Performing cross-config validation...")
        # Validate control strategy point references
        for i, strategy_conf in enumerate(self._control_strategies_config):
             context = f"control_strategies[{i}]" # Updated context string
             self._validate_required_keys(strategy_conf, ["name", "type", "settings"], context)
             settings = strategy_conf["settings"]
             context = f"control_strategies[{i}].settings" # Updated context string

             # Check specific points needed by BangBang controller type
             if strategy_conf["type"] == "BangBang":
                 required_points = ["sensor_point_addr", "setpoint_point_addr",
                                    "deadband_point_addr", "actuator_command_addr"]
                 optional_points = ["actuator_status_addr"]
                 self._validate_required_keys(settings, required_points, context)

                 all_strategy_points = required_points + optional_points
                 for point_key in all_strategy_points:
                     if point_key in settings:
                         addr_to_check = settings[point_key]
                         if not isinstance(addr_to_check, str) or not addr_to_check:
                             raise GovernorConfigurationError(f"'{point_key}' in {context} must be a non-empty string.")
                         if addr_to_check not in self._all_point_addrs:
                             raise GovernorConfigurationError(
                                 f"Point address '{addr_to_check}' referenced by '{point_key}' in {context} "
                                 f"not found in any loaded configuration (microC, driver, or governor points)."
                             )
                         # print(f"Validated point reference: {point_key} -> {addr_to_check}") # Keep commented for less noise

             # TODO: Add validation for other strategy types if needed


        print("Cross-config validation complete.")


    # --- Getter methods to provide validated config sections ---

    def get_mqtt_config(self) -> Dict[str, Any]:
        """Returns the validated MQTT connection details."""
        if self._mqtt_config is None:
            raise GovernorConfigurationError("MQTT config accessed before successful loading.")
        return self._mqtt_config

    def get_runner_config(self) -> Dict[str, Any]:
        """Returns the validated Runner configuration (e.g., loop intervals)."""
        if self._runner_config is None:
            raise GovernorConfigurationError("Runner config accessed before successful loading.")
        return self._runner_config

    def get_control_strategies_config(self) -> List[Dict[str, Any]]:
         """Returns the validated configuration for the control strategy/strategies."""
         if self._control_strategies_config is None:
            raise GovernorConfigurationError("Control strategies config accessed before successful loading.")
         return self._control_strategies_config

    def get_point_manager_config(self) -> Dict[str, Any]:
         """Returns the validated configuration specifically for the Point Manager."""

         assert self._point_manager_config is not None, \
                "Point Manager config accessed before being initialized (should not happen)."
         return self._point_manager_config

    def get_all_point_definitions(self) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Returns all loaded point definitions needed for point instantiation.

        Returns:
            Tuple[Dict[str, Any], Dict[str, Any]]:
              - First dict: Governor-defined points config (already processed with UUIDs).
              - Second dict: Combined external points (microC, drivers).
        """
        if self._governor_points_config is None or self._referenced_microc_config is None:
             raise GovernorConfigurationError("Point definitions accessed before successful loading.")

        # Combine external points (microC and drivers)
        external_points = {
            "microcontrollers": self._referenced_microc_config.get("microcontrollers", {}),
            "drivers": {}
        }
        for _, driver_conf in self._referenced_driver_configs.items():
             driver_name = driver_conf.get("settings", {}).get("driver", {}).get("name")
             driver_points_section = driver_conf.get("points", {}).get("drivers", {})
             if driver_name and driver_name in driver_points_section:
                  if driver_name not in external_points["drivers"]:
                       external_points["drivers"][driver_name] = {}
                  external_points["drivers"][driver_name].update(driver_points_section[driver_name])

        return self._governor_points_config, external_points


    def get_uuid_database_mapping(self) -> Dict[str, int]:
        """Returns the loaded UUID database address-to-UUID mapping."""
        if self._referenced_uuid_db_config is None:
             raise GovernorConfigurationError("UUID DB mapping accessed before successful loading.")
        return self._referenced_uuid_db_config