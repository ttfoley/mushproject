from states import State, StateStatus
from transitions import Transitions_Manager
from points_manager import Active_Points_Manager
from states import States_Manager
from fsm_monitor import FSMMonitor

class ActiveFSM:
    """FSM that requires active points manager and monitor.
    Current state is type StateStatus, desired and previous states are type State."""
    def __init__(self, driver_name: str, SM: States_Manager, 
                 PM: Active_Points_Manager,
                 TM: Transitions_Manager, initial_desired_state: State):
        self._driver_name = driver_name
        self.desired_state = initial_desired_state
        self._SM = SM
        self._states = SM.states
        self._PM = PM
        self.TM = TM
        self._state_status = StateStatus(self._SM.get_state("unknown"))
        self.previous_state = self._states["unknown"]
        self.monitor = self._create_monitor()

    def _create_monitor(self) -> FSMMonitor:
        """Create monitor after FSM is fully initialized"""
        return FSMMonitor(fsm=self, points_manager=self._PM)

    @property
    def PM(self):
        return self._PM

    @PM.setter
    def PM(self, new_pm: Active_Points_Manager):
        self._PM = new_pm
        self.monitor.pm = new_pm  # Always have monitor
        self.TM.update_points_manager(new_pm)

    @property
    def current_state(self) -> StateStatus:
        return self._state_status

    @current_state.setter
    def current_state(self, new_state: State):
        """Set the current state and update related attributes"""
        self._state_status = StateStatus(new_state)
        self.monitor.on_state_change()  # Always have monitor

    def update_state(self) -> bool:
        new_state = self.get_validated_state()
        self.previous_state = self.current_state.state
        
        if new_state != self.current_state.state:
            self.current_state = new_state
            return True
        else:
            self.monitor.update()  # Always have monitor
            return False

    def get_compatible_states(self) -> list[State]:
        """Returns list of states whose output values match current control point values"""
        compatible_states = []
        for state in self._states.values():
            matches = True
            for cp_id, desired_value in state.listed_output_pairs:
                rb_point, _ = self.PM.get_control_point_pair(cp_id)
                if rb_point.value != desired_value:
                    matches = False
                    break
            if matches:
                compatible_states.append(state)
        return compatible_states

    def get_validated_state(self) -> State:
        """Get compatible state based on current control point values"""
        compatible_states = self.get_compatible_states()
        
        if not compatible_states:
            return self._SM.get_state("unknown")
        
        if len(compatible_states) == 1:
            return compatible_states[0]
            
        # Multiple compatible states - try to resolve
        if self.desired_state in compatible_states:
            return self.desired_state
        elif self.current_state.state in compatible_states:
            return self.current_state.state
        else:
            return self._SM.get_state("unknown")

    @property
    def in_desired_state(self):
        return self.current_state.state.name == self.desired_state.name

    def write_desired_state(self, immediately=False):
        """Write all outputs to match desired state"""
        if not self.in_desired_state:
            for cp_id, output_value in self.desired_state.listed_output_pairs:
                _, write_point = self.PM.get_control_point_pair(cp_id)
                write_point.requested_value = output_value
                self.PM.publish_point(write_point, force=immediately)

    def update_desired_state(self) -> bool:
        """Update desired state based on transitions"""
        if self.in_desired_state:
            next_state = self.TM.next_state(self.current_state)
            if next_state != self.current_state.state:
                self.desired_state = next_state
                return True
        return False

    def print_update(self):
        print(self.current_state.state.name, self.desired_state.name, 
              self.monitor.get_time_in_state())

    def get_time_in_state(self) -> float:
        """Implement TimeProvider protocol"""
        return self.current_state.time_in_state