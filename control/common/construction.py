import os
from typing import Tuple
#The fact that I'm importing so many separate things seems like a bad smell, but this is the constructor only...
from states import States_Manager
from points_messenger import PointsMessenger
from transitions import Transitions_Manager
from controller import ActiveFSM
from mqtt_handler import MQTTHandler
from configuration import FSMConfiguration
from points_core import PointsBuilder, PointsRegistry




class FSMConstructor:
    """Builds FSM system using full configuration"""
    def __init__(self, config_path: str):
        self.config = FSMConfiguration(config_path)

    def build_points(self):
        """Build points system with registry"""
        # Create builder and registry
        builder = PointsBuilder(self.config.points_config, self.config.settings)
        self.registry = PointsRegistry(settings=self.config.settings)
        
        # Build all points, get points to register and control points
        points_to_register, control_points = builder.build_points_from_config()
        
        # Register everything in the registry
        for point in points_to_register:
            self.registry.register_point(point)
        for cp_info in control_points:
            self.registry.register_control_point(cp_info)
            
        return self
        
    def build_states_manager(self):
        """Build states manager"""
        self.SM = States_Manager(self.config.states_config, self.config.settings["driver"]["initial_state"])
        self._validate_state_control_points()
        return self
        
    def build_transitions_manager(self):
        """Build transitions manager"""
        if not hasattr(self, 'PM'):
            raise RuntimeError("Call add_mqtt() before building transitions")
            
        self.TM = Transitions_Manager(
            transitions_config=self.config.transitions_config,
            SM=self.SM,
            registry=self.registry
        )
        return self

    def add_mqtt(self):
        """Create and connect MQTT handler"""
        mqtt_settings = self.config.settings.get("mqtt", {})
        if not all(key in mqtt_settings for key in ["broker", "port", "username", "password", "client_id"]):
            raise ValueError("Missing required MQTT settings")
        
        # Override broker with environment variable if present
        mqtt_settings["broker"] = os.getenv('MQTT_BROKER', mqtt_settings["broker"])

        # Create and connect handler
        self.mqtt_handler = MQTTHandler(
            broker=mqtt_settings["broker"],
            port=mqtt_settings["port"],
            username=mqtt_settings["username"],
            password=mqtt_settings["password"],
            client_id=mqtt_settings["client_id"]
        )
        return self

    def build_points_messenger(self):
        """Create points messenger with registry and MQTT handler"""
        if not hasattr(self, 'mqtt_handler'):
            raise RuntimeError("Call add_mqtt() before building points messenger")
            
        self.PM = PointsMessenger(
            registry=self.registry,
            mqtt_handler=self.mqtt_handler,
            settings=self.config.settings
        )
        
        return self

    def build_active_fsm(self):
        """Build FSM with points messenger"""
        if not hasattr(self, 'mqtt_handler'):
            raise RuntimeError("Call add_mqtt() before building FSM")
            
        self.FSM = ActiveFSM(
            driver_name=self.config.driver_name,
            SM=self.SM,
            registry=self.registry,
            messenger=self.PM,
            TM=self.TM,
            initial_desired_state=self.SM.initial_state
        )
        return self

    def build(self) -> Tuple[ActiveFSM, PointsMessenger, Transitions_Manager, MQTTHandler]:
        """Build complete system"""
        if not hasattr(self, 'FSM'):
            raise RuntimeError("Call build_active_fsm() before build()")
        return self.FSM, self.PM, self.TM, self.mqtt_handler

    def _validate_state_control_points(self):
        """Validate that all control points in states exist in registry"""
        for state_name, outputs in self.config.states_config.items():
            for output in outputs:
                cp_info = output["control_point"]
                controller = cp_info["controller"]
                cp_name = cp_info["name"]
                
                if (controller not in self.registry.control_points or 
                    cp_name not in self.registry.control_points[controller]):
                    raise ValueError(f"Control point '{cp_name}' on controller '{controller}' "
                                  f"used in state '{state_name}' does not exist in registry")

    def save_full_config(self, filename: str = "full_config.json"):
        """Save full configuration to file"""
        self.config.save_full_config(filename)









  