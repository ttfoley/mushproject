from datetime import datetime
from mqtt_handler import MQTTHandler
from construction import FSMConstructor

class FSMRunner:
    def __init__(self, 
                 config_path: str,
                 update_frequency: int = 10):
        """Base FSM class that handles common initialization and update logic"""
        self.builder = FSMConstructor(config_path) #Save full config early to help ID issues
        self.builder.save_full_config() 
        self.fsm, self.pm, self.tm, self.mqtt = (self.builder
            .build_points()
            .build_states_manager()
            .build_transitions_manager()
            .add_mqtt()
            .build_active_fsm()
            .build())

        self.update_frequency = update_frequency
        self.last_update_time = datetime.now()
        self.gap_between_set_readback = 0
        self.desired_set = datetime.now()

    def _initial_setup(self):
        """Initial FSM setup"""
        assert isinstance(self.mqtt, MQTTHandler), "MQTT handler not properly initialized"
        if not self.mqtt.client.is_connected():
            self.mqtt.connect()  # Ensure MQTT is connected
        self.mqtt.loop_start()
        self.fsm.print_update()
        self.fsm.write_desired_state(immediately=True)
        self.fsm.update_state()
        self.fsm.print_update()

    def update(self):
        """Single iteration of FSM update loop"""
        self.fsm.update_state()
        changed = self.fsm.update_desired_state()
        
        if changed:
            print(f"Changed desired state to {self.fsm.desired_state.name} at {datetime.now()}. "
                  f"Current state is: {self.fsm.current_state.name}")
            self.desired_set = datetime.now()
            
        if self.fsm.current_state.name != self.fsm.previous_state.name:
            print(f"Verified state change to {self.fsm.current_state.name} at {datetime.now()} "
                  f"from state: {self.fsm.previous_state.name}")
            self.gap_between_set_readback = (datetime.now() - self.desired_set).total_seconds()
            print(f"Gap between set and readback: {self.gap_between_set_readback}")

        if not self.fsm.in_desired_state:
            if changed:
                self.fsm.write_desired_state(immediately=True)
            else:
                self.fsm.write_desired_state()

        # Update monitor after all state changes are complete
        if self.fsm.monitor:
            self.fsm.monitor.update()
        else:
            print("Warning,No monitor active, state_time will not be usable")

        if (datetime.now()-self.last_update_time).total_seconds() > self.update_frequency:
            self.fsm.print_update()
            self.last_update_time = datetime.now()

    def run(self):
        """Main run loop"""
        self._initial_setup()
        try:
            while True:
                self.update()
        except KeyboardInterrupt:
            print("\nShutting down...")
        finally:
            self.mqtt.loop_stop()