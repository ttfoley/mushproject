import json
import sys
import os
from typing import Dict, Any,Tuple
#The fact that I'm importing so many separate things seems like a bad smell, but this is the constructor only...
from states import State, States_Manager
from points_manager import Points_Manager, Active_Points_Manager, ControlPoint
from collections import defaultdict
from transitions import Transitions_Manager  # You'll need to create/import this
from controller import FSM
from fsm_monitor import create_monitor_points
from mqtt_handler import MQTTHandler





class PreTransitionsConstructor:
    """
    Builds everything up to the transitions. Transitions are hard to build right now, having this info available 
    will make it easier to build them.
    """
    def __init__(self, config_path):
        # Load configs
        self._microC_points_config = json.load(open(os.path.join(config_path, "microC_points.json")))
        self._states_config = json.load(open(os.path.join(config_path, "states.json")))
        self._settings = json.load(open(os.path.join(config_path, "settings.json")))
        self._driver_name = self._settings["driver"]["name"]
        
        # Build base Points_Manager
        self.PM = Points_Manager(self._microC_points_config, self._settings)
        
        # Build States_Manager
        self.SM = States_Manager(self._states_config, self._settings["driver"]["initial_state"])
        
        self._validate_state_control_points(self._states_config)

    def _validate_state_control_points(self, states_config):
        """Validate that all control points in states exist in points manager"""
        for state_name, outputs in states_config.items():
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




class Constructor(PreTransitionsConstructor):
    """Constructor that requires MQTT handler to be activated to function properly."""
    def __init__(self, config_path):
        super().__init__(config_path)
        
        # Load transitions config
        self._transitions_config = json.load(open(os.path.join(config_path, "transitions.json")))
        
        # Create transitions manager
        self.TM = Transitions_Manager(
            transitions_config=self._transitions_config,
            SM=self.SM,
            PM=self.PM
        )
        
        # Create monitor points first
        points, self._state_point, self._time_point = create_monitor_points(
            driver_name=self._driver_name,
            state_names=self.SM.state_names,
            points_manager=self.PM
        )
        self.PM.points.update(points)
        
        # Create FSM without monitor
        self.FSM = FSM(
            driver_name=self._driver_name,
            SM=self.SM,
            PM=self.PM,
            TM=self.TM,
            initial_desired_state=self.SM.initial_state,
            create_monitor=False
        )
        
        # Initialize MQTT handler from settings
        mqtt_settings = self._settings.get("mqtt", {})
        if not all(key in mqtt_settings for key in ["broker", "port", "username", "password", "client_id"]):
            raise ValueError("Missing required MQTT settings. Need broker, port, username, password, and client_id")
            
        self.mqtt_handler = MQTTHandler(
            broker=mqtt_settings["broker"],
            port=mqtt_settings["port"],
            points_manager=self.PM,
            username=mqtt_settings["username"],
            password=mqtt_settings["password"],
            client_id=mqtt_settings["client_id"]
        )

    def connect_mqtt(self):
        """Connect MQTT and activate functionality"""
        self.mqtt_handler.connect()
        self.activate_mqtt(self.mqtt_handler)

    def activate_mqtt(self, mqtt_handler):
        """Activate MQTT functionality"""
        # Convert PM to Active_Points_Manager
        self.PM = Active_Points_Manager(
            base_manager=self.PM,
            message_publisher=mqtt_handler
        )
        
        # Update FSM's reference to the new Active_Points_Manager
        self.FSM.PM = self.PM
        
        # Update mqtt_handler's reference to the Active_Points_Manager
        mqtt_handler._points_manager = self.PM
        
        # Create monitor with existing points
        self.FSM.create_monitor(
            points_manager=self.PM,
            state_point=self._state_point,
            time_point=self._time_point
        )

        # Subscribe to all control point readback and write topics
        read_points = set()
        write_points = set()
        for controller in self.PM.control_points:
            for cp in self.PM.control_points[controller].values():
                read_points.add(cp.readback_point.addr)
                write_points.add(cp.write_point.addr)
        
        # Only subscribe to readback points
        self.PM.add_monitored_points(read_points=read_points, write_points=set())









  
class FSMBuilder:
    """Builds FSM system step by step with clear dependencies"""
    def __init__(self, config_path):
        self._config_path = config_path
        self._load_configs()
        
    def _load_configs(self):
        """Load all configuration files"""
        self._microC_points_config = json.load(open(os.path.join(self._config_path, "microC_points.json")))
        self._states_config = json.load(open(os.path.join(self._config_path, "states.json")))
        self._settings = json.load(open(os.path.join(self._config_path, "settings.json")))
        self._transitions_config = json.load(open(os.path.join(self._config_path, "transitions.json")))
        self._driver_name = self._settings["driver"]["name"]

    def build_points_manager(self):
        """Build base points manager"""
        self.PM = Points_Manager(self._microC_points_config, self._settings)
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

    def build_monitor_points(self):
        """Create monitor points"""
        points, self._state_point, self._time_point = create_monitor_points(
            driver_name=self._driver_name,
            state_names=self.SM.state_names,
            points_manager=self.PM
        )
        self.PM.points.update(points)
        return self

    def build_fsm(self):
        """Build FSM without monitor"""
        self.FSM = FSM(
            driver_name=self._driver_name,
            SM=self.SM,
            PM=self.PM,
            TM=self.TM,
            initial_desired_state=self.SM.initial_state,
            create_monitor=False
        )
        return self

    def add_mqtt(self):
        """Add MQTT functionality if needed"""
        mqtt_settings = self._settings.get("mqtt", {})
        if not all(key in mqtt_settings for key in ["broker", "port", "username", "password", "client_id"]):
            raise ValueError("Missing required MQTT settings")

        # Create handler
        self.mqtt_handler = MQTTHandler(
            broker=mqtt_settings["broker"],
            port=mqtt_settings["port"],
            points_manager=self.PM,
            username=mqtt_settings["username"],
            password=mqtt_settings["password"],
            client_id=mqtt_settings["client_id"]
        )

        # Connect and activate
        self.mqtt_handler.connect()
        
        # Convert to Active_Points_Manager
        self.PM = Active_Points_Manager(
            base_manager=self.PM,
            message_publisher=self.mqtt_handler
        )
        
        # Update references
        self.FSM.PM = self.PM
        self.mqtt_handler._points_manager = self.PM
        
        # Create monitor
        self.FSM.create_monitor(
            points_manager=self.PM,
            state_point=self._state_point,
            time_point=self._time_point
        )

        # Subscribe to all control point readback and write topics
        read_points = set()
        write_points = set()
        for controller in self.PM.control_points:
            for cp in self.PM.control_points[controller].values():
                read_points.add(cp.readback_point.addr)
                write_points.add(cp.write_point.addr)
        
        # Only subscribe to readback points
        self.PM.add_monitored_points(read_points=read_points, write_points=set())
        
        return self

    def build(self) -> Tuple[FSM, Points_Manager, Transitions_Manager, MQTTHandler]:
        """Build complete system"""
        if not hasattr(self, 'mqtt_handler'):
            raise RuntimeError("MQTT handler not created. Call add_mqtt() before build()")
            
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









  