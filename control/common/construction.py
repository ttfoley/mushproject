import os
from typing import Tuple
#The fact that I'm importing so many separate things seems like a bad smell, but this is the constructor only...
from states import States_Manager
from points_manager import Points_Manager, Active_Points_Manager
from transitions import Transitions_Manager  # You'll need to create/import this
from controller import  ActiveFSM
from mqtt_handler import MQTTHandler
from configuration import FSMConfiguration




class FSMConstructor:
    """Builds FSM system using full configuration"""
    def __init__(self, config_path: str):
        self.config = FSMConfiguration(config_path)

    def build_points_manager(self):
        """Build points manager with all needed points"""
        self.PM = Points_Manager(self.config.points_config, self.config.settings)
        self.PM.build_driver_points(self.config.states_config)
        return self
        
    def build_states_manager(self):
        """Build states manager"""
        self.SM = States_Manager(self.config.states_config, self.config.settings["driver"]["initial_state"])
        self._validate_state_control_points()
        return self
        
    def build_transitions_manager(self):
        """Build transitions manager. When constructed, the PM is not yet activated. Gets activated 
        when we upgrade to the Active_Points_Manager in add_mqtt()."""
        self.TM = Transitions_Manager(
            transitions_config=self.config.transitions_config,
            SM=self.SM,
            PM=self.PM
        )
        return self

    def add_mqtt(self):
        """Create MQTT handler and activate points manager
        Note that since Transitions_Manager is referencing the Points_Manager,
        its points will also be activated once we upgrade to the Active_Points_Manager.
        """
        mqtt_settings = self.config.settings.get("mqtt", {})
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
         # Update self.PM to Active_Points_Manager
        # This affects all references to self.PM, including the one in TM
        self.PM = Active_Points_Manager(
            base_manager=self.PM,
            message_publisher=self.mqtt_handler
        )
        self.mqtt_handler._points_manager = self.PM
        
        return self

    def build_active_fsm(self):
        """Build FSM with active points manager"""
        if not hasattr(self, 'mqtt_handler'):
            raise RuntimeError("Call add_mqtt() before building FSM")
        if not isinstance(self.PM, Active_Points_Manager):
            raise RuntimeError("Points Manager must be activated before building FSM. Call add_mqtt() first")
        self.FSM = ActiveFSM(
            driver_name=self.config.driver_name,
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
        for state_name, outputs in self.config.states_config.items():
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

    def save_full_config(self, filename: str = "full_config.json"):
        """Save full configuration to file"""
        self.config.save_full_config(filename)









  