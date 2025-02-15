import json
import os
from typing import Dict, Any, Optional
from config.uuid_database import UUIDDatabase
from config.point_address import PointAddress

class BaseConfiguration:
    """Base configuration needed for transitions"""
    def __init__(self, config_path: str):
        self._config_path = config_path
        self._needed_points = set()  # Track points needed by FSM
        self._uuid_db = UUIDDatabase()  # Use shared UUID database
        self._load_base_configs()
        self._build_points_config()
        self._validate_base_configs()
        
    def _load_base_configs(self):
        """Load configs needed for transitions"""
        self._microC_points_config = json.load(open(os.path.join(self._config_path, "microC_points.json")))
        self._states_config = json.load(open(os.path.join(self._config_path, "states.json")))
        self._settings = json.load(open(os.path.join(self._config_path, "settings.json")))
        self._driver_name = self._settings["driver"]["name"]

    def _add_needed_point(self, addr: str):
        """Add point to set of points needed by FSM"""
        self._needed_points.add(addr)
        
    def _build_points_config(self):
        """Build complete points configuration including driver and governor points"""
        # Start with microcontroller points
        self._points_config = self._microC_points_config
        
        # Add driver points
        if "drivers" not in self._points_config:
            self._points_config["drivers"] = {}
            
        # Track current address for UUID assignment
        base_topic = f"mush/drivers/{self._driver_name}"
        
        # Always create status points
        self._current_addr = f"{base_topic}/status/state"
        state_uuid = self._get_next_uuid()
        
        self._current_addr = f"{base_topic}/status/state_time"
        time_uuid = self._get_next_uuid()
        
        driver_config = {
            "status": {
                "state": {
                    "addr": f"{base_topic}/status/state",
                    "UUID": state_uuid,
                    "value_type": "discrete",
                    "valid_values": list(self._states_config.keys()) + ["unknown"],
                    "description": "driver state"
                },
                "state_time": {
                    "addr": f"{base_topic}/status/state_time", 
                    "UUID": time_uuid,
                    "value_type": "continuous",
                    "valid_range": {"lower": 0, "upper": 1000000},
                    "description": "state time"
                }
            }
        }
        
        # Only create command point if governor needed
        if self._settings["driver"].get("needs_governor", False):
            self._current_addr = f"{base_topic}/command/state"
            command_uuid = self._get_next_uuid()
            driver_config["command"] = {
                "state": {
                    "addr": f"{base_topic}/command/state",
                    "UUID": command_uuid,
                    "value_type": "discrete",
                    "valid_values": list(self._states_config.keys()),
                    "description": "commanded state"
                }
            }
        
        self._points_config["drivers"][self._driver_name] = driver_config

    def _get_next_uuid(self) -> int:
        """Get UUID for current point address"""
        return self._uuid_db.get_uuid(self._current_addr)

    def _validate_base_configs(self):
        """Validate configs and track needed points from states"""
        # Add control points from states to needed points
        for state_name, outputs in self._states_config.items():
            for output in outputs:
                cp_info = output["control_point"]
                controller = cp_info["controller"]
                cp_name = cp_info["name"]
                
                # Validate control point exists in microcontroller config
                assert controller in self._microC_points_config["microcontrollers"], \
                    f"Controller '{controller}' referenced in state '{state_name}' not found in microcontroller config"
                
                controller_config = self._microC_points_config["microcontrollers"][controller]
                assert "control_points" in controller_config, \
                    f"Controller '{controller}' has no control points defined but is referenced in state '{state_name}'"
                
                assert cp_name in controller_config["control_points"], \
                    f"Control point '{cp_name}' referenced in state '{state_name}' not found in controller '{controller}'"
                
                # Add readback point to needed points
                addr = f"mush/controllers/{controller}/control_points/{cp_name}/readback"
                self._add_needed_point(addr)

    def get_point_uuid(self, addr: str) -> int:
        """Get UUID for point at given address"""
        def search_dict(d: dict) -> Optional[int]:
            if isinstance(d, dict):
                if d.get("addr") == addr:
                    return d["UUID"]
                if "readback" in d and d["readback"].get("addr") == addr:
                    return d["readback"]["UUID"]
                if "write" in d and d["write"].get("addr") == addr:
                    return d["write"]["UUID"]
                for v in d.values():
                    result = search_dict(v)
                    if result is not None:
                        return result
            return None

        result = search_dict(self._points_config)
        if result is None:
            raise ValueError(f"No point found with address {addr}")
        return result

    def save_points_config(self, filename: str):
        """Save complete points configuration to file"""
        with open(filename, 'w') as f:
            json.dump(self._points_config, f, indent=4)

class FSMConfiguration(BaseConfiguration):
    """Full configuration including transitions"""
    def __init__(self, config_path: str):
        super().__init__(config_path)
        # Track points needed by address
        self._needed_points = set()
        self._load_transitions_config()
        self._collect_needed_points()
        # Replace full config with filtered version
        self._points_config = self._create_filtered_config()

    def _load_transitions_config(self):
        self._transitions_config = json.load(open(os.path.join(self._config_path, "transitions.json")))

    def save_full_config(self, filename: str = "full_config.json"):
        """Save full configuration to file"""
        config = {
            "settings": self._settings,
            "states": self._states_config, 
            "transitions": self._transitions_config, 
            "points": self._points_config
        }
        with open(os.path.join(self._config_path, filename), 'w') as f:
            json.dump(config, f, indent=2)

    @property
    def points_config(self) -> Dict[str, Any]:
        return self._points_config

    @property
    def settings(self) -> Dict[str, Any]:
        return self._settings

    @property
    def states_config(self) -> Dict[str, Any]:
        return self._states_config

    @property
    def transitions_config(self) -> Dict[str, Any]:
        return self._transitions_config

    @property
    def driver_name(self) -> str:
        return self._driver_name 

    def _collect_needed_points(self):
        """Collect addresses of all points needed by the FSM"""
        # From states.json - get control points
        self._collect_state_points()
        # From transitions.json - get points referenced by UUID
        self._collect_transition_points()
        # Add required driver points
        self._needed_points.add(PointAddress.make_driver_address(self._driver_name, "status", "state"))
        self._needed_points.add(PointAddress.make_driver_address(self._driver_name, "status", "state_time"))
        if self._settings["driver"].get("needs_governor", False):
            self._needed_points.add(PointAddress.make_driver_address(self._driver_name, "command", "state"))

    def _collect_state_points(self):
        """Collect control points used in states"""
        for state_name, outputs in self._states_config.items():
            for output in outputs:
                cp_info = output["control_point"]
                controller = cp_info["controller"]
                cp_name = cp_info["name"]
                # Add both readback and write addresses
                rb_addr = PointAddress.make_control_point_address(controller, cp_name, "readback")
                wr_addr = PointAddress.make_control_point_address(controller, cp_name, "write")
                self._needed_points.add(rb_addr)
                self._needed_points.add(wr_addr)

    def _collect_transition_points(self):
        """Collect points from transitions"""
        def extract_uuids(obj):
            """Recursively find all value_uuid fields in transitions config
            and add their corresponding points to needed points.
            This will work regardless of where value_uuid appears in the structure."""
            if isinstance(obj, dict):
                if "value_uuid" in obj:
                    uuid = obj["value_uuid"]
                    self._add_point_by_uuid(uuid)
                for value in obj.values():
                    extract_uuids(value)
            elif isinstance(obj, list):
                for item in obj:
                    extract_uuids(item)
        
        extract_uuids(self._transitions_config)

    def _create_filtered_config(self):
        """Create filtered points config with only needed points.
        
        Always includes driver status points (state and state_time) which are
        required for FSM operation. Also includes command/state point if 
        governor control is enabled in settings.
        """
        filtered_config = {"microcontrollers": {}, "drivers": {}}
        
        # Add needed microcontroller points
        for addr in self._needed_points:
            address = PointAddress(addr)
            if address.type == "microcontroller":
                controller = address.controller
                point_type = address.point_type
                name = address.name
                
                # Initialize controller structure if needed
                if controller not in filtered_config["microcontrollers"]:
                    filtered_config["microcontrollers"][controller] = {
                        "control_points": {}  # Don't create empty sensors dict
                    }
                
                # Copy the point config from the original
                if point_type == "control_points":
                    if name not in filtered_config["microcontrollers"][controller]["control_points"]:
                        filtered_config["microcontrollers"][controller]["control_points"][name] = \
                            self._microC_points_config["microcontrollers"][controller]["control_points"][name]
                elif point_type == "sensors":
                    if "sensors" not in filtered_config["microcontrollers"][controller]:
                        filtered_config["microcontrollers"][controller]["sensors"] = {}
                    sensor_name = name
                    reading = address.access_type
                    if sensor_name not in filtered_config["microcontrollers"][controller]["sensors"]:
                        filtered_config["microcontrollers"][controller]["sensors"][sensor_name] = {}
                    filtered_config["microcontrollers"][controller]["sensors"][sensor_name][reading] = \
                        self._microC_points_config["microcontrollers"][controller]["sensors"][sensor_name][reading]

        # Add driver points with correct UUIDs
        driver_config = {
            "status": {
                "state": {
                    "addr": PointAddress.make_driver_address(self._driver_name, "status", "state"),
                    "UUID": self._uuid_db.get_uuid(PointAddress.make_driver_address(self._driver_name, "status", "state")),
                    "value_type": "discrete",
                    "valid_values": list(self._states_config.keys()) + ["unknown"],
                    "description": "driver state"
                },
                "state_time": {
                    "addr": PointAddress.make_driver_address(self._driver_name, "status", "state_time"),
                    "UUID": self._uuid_db.get_uuid(PointAddress.make_driver_address(self._driver_name, "status", "state_time")),
                    "value_type": "continuous",
                    "valid_range": {"lower": 0, "upper": 1000000},
                    "description": "state time"
                }
            }
        }
        
        if self._settings["driver"].get("needs_governor", False):
            driver_config["command"] = {
                "state": {
                    "addr": PointAddress.make_driver_address(self._driver_name, "command", "state"),
                    "UUID": self._uuid_db.get_uuid(PointAddress.make_driver_address(self._driver_name, "command", "state")),
                    "value_type": "discrete",
                    "valid_values": list(self._states_config.keys()),
                    "description": "commanded state"
                }
            }
        
        filtered_config["drivers"][self._driver_name] = driver_config
        
        return filtered_config 

    def _add_point_by_uuid(self, uuid: int):
        """Find point with given UUID and add its address to needed points"""
        def find_addr_by_uuid(d: dict) -> Optional[str]:
            """Recursively search for point with given UUID and return its address
            Assumes UUID is on same level as addr..."""
            if isinstance(d, dict):
                if "UUID" in d and d["UUID"] == uuid:
                    return d.get("addr")
                for v in d.values():
                    result = find_addr_by_uuid(v)
                    if result:
                        return result
            return None

        addr = find_addr_by_uuid(self._points_config)
        if addr:
            self._needed_points.add(addr) 