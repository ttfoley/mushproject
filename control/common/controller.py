from states import State
from transitions import Transitions_Manager
from points_messenger import PointsMessenger
from points_core import PointsRegistry
from states import States_Manager
from fsm_monitor import FSMMonitor

class ActiveFSM:
    """FSM that requires points messenger and monitor.
    Current state is type StateStatus, desired and previous states are type State."""
    def __init__(self, driver_name: str, SM: States_Manager, 
                 registry: PointsRegistry,
                 messenger: PointsMessenger,
                 TM: Transitions_Manager, initial_desired_state: State):
        self.driver_name = driver_name
        self.desired_state = initial_desired_state
        self.SM = SM
        self.states = SM.states  
        self.registry = registry
        self.messenger = messenger
        self.TM = TM
        self.current_state = self.SM.get_state("unknown", "Initial state")
        self.previous_state = self.states["unknown"]
        self.monitor = self._create_monitor()

    def _create_monitor(self) -> FSMMonitor:
        """Internal helper to create monitor"""
        return FSMMonitor(fsm=self, registry=self.registry)

    def _get_compatible_states(self) -> list[State]:
        """Internal helper to find states matching current control point values"""
        compatible_states = []
        for state in self.states.values():
            matches = True
            for cp_id, desired_value in state.listed_output_pairs:
                rb_point, _ = self.registry.get_control_point_pair(cp_id)
                if rb_point.value != desired_value:
                    matches = False
                    break
            if matches:
                compatible_states.append(state)
        return compatible_states

    def _get_validated_state(self) -> State:
        """Internal helper to validate state based on compatible states"""
        compatible_states = self._get_compatible_states()
        
        if not compatible_states:
            return self.SM.get_state("unknown", "No states match current control point values")
        
        if len(compatible_states) == 1:
            return compatible_states[0]
            
        # Multiple compatible states - try to resolve
        if self.desired_state in compatible_states:
            return self.desired_state
        elif self.current_state in compatible_states:
            return self.current_state
        else:
            return self.SM.get_state("unknown", "Multiple matching states without resolution")

    def update_state(self) -> bool:
        """Public interface to update current state"""
        new_state = self._get_validated_state()
        self.previous_state = self.current_state
        
        if new_state != self.current_state:
            self.current_state = new_state
            self.monitor.on_state_change() #callback to notify monitor of state change
            return True
        else:
            self.monitor.update()
            return False

    @property
    def in_desired_state(self):
        """Public property to check if current state matches desired state"""
        #This isn't very robust, but it's good enough for now.
        return self.current_state.name == self.desired_state.name

    def write_desired_state(self, immediately=False):
        """Public interface to write outputs for desired state"""
        if not self.in_desired_state:
            for cp_id, output_value in self.desired_state.listed_output_pairs:
                _, write_point = self.registry.get_control_point_pair(cp_id)
                write_point.requested_value = output_value
                self.messenger.publish_point(write_point, force=immediately)

    def update_desired_state(self) -> bool:
        """Public interface to update desired state based on transitions"""
        if self.in_desired_state:
            next_state = self.TM.next_state(self.current_state)
            if next_state != self.current_state:
                self.desired_state = next_state
                return True
        return False

    def print_update(self):
        """Public interface to print current status"""
        print(self.current_state.name, self.desired_state.name, 
              self.monitor.get_time_in_state())
