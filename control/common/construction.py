import json
import sys
import os
from typing import Dict, Any,Tuple, Optional
#The fact that I'm importing so many separate things seems like a bad smell, but this is the constructor only...
from states import States_Manager
from points_manager import Points_Manager, Active_Points_Manager
from transitions import Transitions_Manager  # You'll need to create/import this
from controller import  ActiveFSM
from mqtt_handler import MQTTHandler
from config.uuid_database import UUIDDatabase





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
        self._current_addr = f"mush/drivers/{self._driver_name}/sensors/status/state"
        state_uuid = self._get_next_uuid()
        
        self._current_addr = f"mush/drivers/{self._driver_name}/sensors/status/state_time"
        time_uuid = self._get_next_uuid()
            
        self._points_config["drivers"][self._driver_name] = {
            "sensors": {
                "status": {
                    "state": {
                        "addr": f"mush/drivers/{self._driver_name}/sensors/status/state",
                        "UUID": state_uuid,
                        "value_type": "discrete",
                        "valid_values": list(self._states_config.keys()) + ["unknown"],
                        "description": "driver state"
                    },
                    "time_in_state": {
                        "addr": f"mush/drivers/{self._driver_name}/sensors/status/state_time", 
                        "UUID": time_uuid,
                        "value_type": "continuous",
                        "valid_range": {"lower": 0, "upper": 1000000},
                        "description": "state time"
                    }
                }
            }
        }

        # Add governor points if configured
        if "governor" in self._settings:
            if "governors" not in self._points_config:
                self._points_config["governors"] = {}

            governor_config = self._settings["governor"]
            governor_name = governor_config["name"]
            governor_addr = governor_config["addr"]

            self._current_addr = f"{governor_addr}/commands/state"
            cmd_uuid = self._get_next_uuid()

            self._points_config["governors"][governor_name] = {
                "commands": {
                    "state": {
                        "addr": f"{governor_addr}/commands/state",
                        "UUID": cmd_uuid,
                        "value_type": "str",
                        "valid_values": list(self._states_config.keys()),
                        "description": "commanded state"
                    }
                }
            }

    def _build_governor_points(self) -> dict:
        """Build governor points configuration"""
        governor_config = self._settings["governor"]
        governor_points = {
            "governors": {
                governor_config["name"]: {
                    "commands": {}
                }
            }
        }
        
        # Add command points
        for command in governor_config.get("commands", []):
            addr = f"mush/governors/{governor_config['name']}/commands/{command}"
            governor_points["governors"][governor_config["name"]]["commands"][command] = {
                "addr": addr,
                "UUID": self._get_next_uuid(),
                "value_type": "discrete",
                "valid_values": ["on", "off"],
                "description": f"Governor {command} command"
            }
            self._add_needed_point(addr)
            
        return governor_points

    def _get_next_uuid(self) -> int:
        """Get UUID for current point address"""
        return self._uuid_db.get_uuid(self._current_addr)  # Need to track current address

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
        self._load_transitions_config()
        
    def _load_transitions_config(self):
        self._transitions_config = json.load(open(os.path.join(self._config_path, "transitions.json")))

    def save_full_config(self, filename: str = "full_config.json"):
        """Save full configuration to file"""
        config = {"settings": self._settings,"states": self._states_config, "transitions": self._transitions_config, "points": self._points_config}
        with open(self._config_path + "/" + filename, 'w') as f:
            json.dump(config, f, indent=2)
            
class FSMConstructor(FSMConfiguration):
    """Builds FSM system using full configuration"""
    def __init__(self, config_path: str):
        super().__init__(config_path)

    def build_points_manager(self):
        """Build points manager with all needed points"""
        self.PM = Points_Manager(self._points_config, self._settings)
        self.PM.build_governor_points()
        self.PM.build_driver_points(self._driver_name, self._states_config)
        return self
        
    def build_states_manager(self):
        """Build states manager"""
        self.SM = States_Manager(self._states_config, self._settings["driver"]["initial_state"])
        self._validate_state_control_points()
        return self
        
    def build_transitions_manager(self):
        """Build transitions manager"""
        self.TM = Transitions_Manager(
            transitions_config=self._transitions_config,
            SM=self.SM,
            PM=self.PM
        )
        return self

    def add_mqtt(self):
        """Create MQTT handler and activate points manager"""
        mqtt_settings = self._settings.get("mqtt", {})
        if not all(key in mqtt_settings for key in ["broker", "port", "username", "password", "client_id"]):
            raise ValueError("Missing required MQTT settings")
        # Override broker with environment variable if present
        mqtt_settings["broker"] = os.getenv('MQTT_BROKER', mqtt_settings["broker"])

        # Create and connect handler
        self.mqtt_handler = MQTTHandler(
            broker=mqtt_settings["broker"],
            port=mqtt_settings["port"],
            points_manager=self.PM,
            username=mqtt_settings["username"],
            password=mqtt_settings["password"],
            client_id=mqtt_settings["client_id"]
        )
        self.mqtt_handler.connect()
        
        # Activate points manager
        self.PM = Active_Points_Manager(
            base_manager=self.PM,
            message_publisher=self.mqtt_handler
        )
        self.mqtt_handler._points_manager = self.PM
        
        # Subscribe to control points
        read_points = set()
        write_points = set()
        for controller in self.PM.control_points:
            for cp in self.PM.control_points[controller].values():
                read_points.add(cp.readback_point.addr)
                write_points.add(cp.write_point.addr)
        
        # Only subscribe to readback points
        self.PM.add_monitored_points(read_points=read_points, write_points=set())
        return self

    def build_active_fsm(self):
        """Build FSM with active points manager"""
        if not hasattr(self, 'mqtt_handler'):
            raise RuntimeError("Call add_mqtt() before building FSM")
        if not isinstance(self.PM, Active_Points_Manager):
            raise RuntimeError("Points Manager must be activated before building FSM. Call add_mqtt() first")
        self.FSM = ActiveFSM(
            driver_name=self._driver_name,
            SM=self.SM,
            PM=self.PM,
            TM=self.TM,
            initial_desired_state=self.SM.initial_state
        )
        return self

    def build(self) -> Tuple[ActiveFSM, Active_Points_Manager, Transitions_Manager, MQTTHandler]:
        """Build complete system"""
        if not hasattr(self, 'FSM'):
            raise RuntimeError("Call build_active_fsm() before build()")
        assert isinstance(self.PM, Active_Points_Manager)
        return self.FSM, self.PM, self.TM, self.mqtt_handler

    def _validate_state_control_points(self):
        """Validate that all control points in states exist in points manager"""
        for state_name, outputs in self._states_config.items():
            for output in outputs:
                cp_info = output["control_point"]
                controller = cp_info["controller"]
                cp_name = cp_info["name"]
                
                control_point_found = False
                if controller in self.PM.control_points:
                    if cp_name in self.PM.control_points[controller]:
                        control_point_found = True
                
                if not control_point_found:
                    raise ValueError(f"Control point '{cp_name}' on controller '{controller}' used in state '{state_name}' "
                                  f"does not exist in points manager")









  