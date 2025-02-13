from datetime import datetime
from mqtt_handler import MQTTHandler
from construction import FSMConstructor
import time

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
            .add_mqtt()
            .build_points_messenger()
            .build_transitions_manager()
            .build_active_fsm()
            .build())

        self.update_frequency = update_frequency
        self.last_update_time = datetime.now()
        self.gap_between_set_readback = 0
        self.desired_set = datetime.now()

    def _initial_setup(self):
        """Initial FSM setup"""
        assert isinstance(self.mqtt, MQTTHandler), "MQTT handler not properly initialized"
        
        # Ensure MQTT is connected and ready
        self._ensure_mqtt_connection()
        
        self.fsm.print_update()
        self.fsm.write_desired_state(immediately=True)
        self.fsm.update_state()
        self.fsm.print_update()

    def _ensure_mqtt_connection(self, timeout: int = 10):
        """Ensure MQTT is connected and ready for communication
        
        Args:
            timeout: Maximum time in seconds to wait for connection
            
        Raises:
            RuntimeError: If connection cannot be established within timeout
        """
        # Start MQTT network loop thread first - this handles all async operations
        # including connection process, callbacks, and message processing
        self.mqtt.loop_start()
        
        # Now initiate connection if needed
        if not self.mqtt.client.is_connected():
            self.mqtt.connect()  # Initiate connection attempt
            time.sleep(0.1)  # Give connection a moment to start
            
            # Wait for connection to be established (with timeout)
            start_time = datetime.now()
            while not self.mqtt.client.is_connected():
                if (datetime.now() - start_time).total_seconds() > timeout:
                    self.mqtt.loop_stop()
                    raise RuntimeError(f"MQTT connection timeout after {timeout} seconds")
                time.sleep(0.1)

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
        try:
            self._initial_setup()
            while True:
                self.update()
        except KeyboardInterrupt:
            print("\nShutting down...")
        except RuntimeError as e:
            print(f"\nError during setup or run: {e}")
        finally:
            self.mqtt.loop_stop()