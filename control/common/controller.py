from states import State, StateStatus
from transitions import Transitions_Manager
from points_manager import Points_Manager,Active_Points_Manager
from states import States_Manager
from fsm_monitor import FSMMonitor
from typing import Union

class FSM:
    #A FSM for controlling the humidity.
    #You need an unknown state, and you need to know the initial desired state.
    #States will have rules for when to switch to the next state..
    #Note that control point state and thus outputs is updated by the mqtt_handler. 
    #READ THIS Current state is type StateStatus, desired and previous states are type State. This is kind of confusing.  I need better names.
    def __init__(self, driver_name: str, SM: States_Manager, 
                 PM: Union[Points_Manager, Active_Points_Manager],  # Accept either type
                 TM: Transitions_Manager, initial_desired_state: State,
                 create_monitor: bool = True):
        self._driver_name = driver_name
        self.desired_state = initial_desired_state
        self._SM = SM
        self._states = SM.states
        self._PM = PM
        self.TM = TM
        self._state_status = StateStatus(self._SM.get_state("unknown"))
        self.previous_state = self._states["unknown"]
        
        self.monitor = None
        if create_monitor:
            self.create_monitor(PM)

    @property
    def PM(self):
        return self._PM

    @PM.setter
    def PM(self, new_pm: Active_Points_Manager):
        self._PM = new_pm
        if self.monitor:
            self.monitor.pm = new_pm  # Update monitor's points manager
        # Update all constraints' points manager
        self.TM.update_points_manager(new_pm)

    @property
    def current_state(self) -> StateStatus:
        return self._state_status

    @current_state.setter
    def current_state(self, new_state: State):
        """Set the current state and update related attributes"""
        self._state_status = StateStatus(new_state)
        if self.monitor:
            self.monitor.on_state_change()  # Notify monitor

    def update_state(self) -> bool:
        new_state = self.get_validated_state()
        # Store the current state before potentially changing it
        self.previous_state = self.current_state.state
    # Debug prints
        # print("\nControl Point Values:")
        # for controller in self.PM.control_points:
        #     for cp_name, cp in self.PM.control_points[controller].items():
        #         print(f"{cp_name}: readback={cp.readback_point.value}, write={cp.write_point.value}")
    
        if new_state != self.current_state.state:
            #triggers a state change, which also triggers the monitor
            self.current_state = new_state
            return True
        else:
            if self.monitor:
                self.monitor.update()  # Update time
            return False

    def get_compatible_states(self) -> list[State]:
        """Returns list of states whose output values match current control point values"""
        compatible_states = []
        for state in self._states.values():
            matches = True
            #state.listed_output_pairs is a list of (cp_id, desired_value) tuples, 
            #where cp_id is the id of the control point (With controller and name) and desired_value is the value to write to the control point.
            for cp_id, desired_value in state.listed_output_pairs:
                rb_point, _ = self.PM.get_control_point_pair(cp_id)
                if rb_point.value != desired_value:
                    matches = False
                    break
            if matches:
                compatible_states.append(state)
        return compatible_states

    def get_validated_state(self) -> State:
        """Get state compatible with current control point values"""
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
            print("Warning: No compatible states found. Returning unknown.")
            return self._SM.get_state("unknown")
                
        

    @property
    def in_desired_state(self):
        #If the current state is the desired state, return True
        #TODO Make this more robust.  Maybe we should check the outputs too.
        if self.current_state.state.name == self.desired_state.name:
            return True
        return False

    def write_desired_state(self, immediately=False):
        """Write all outputs to match desired state"""
        if isinstance(self.PM, Active_Points_Manager):
            if not self.in_desired_state:
                for cp_id, output_value in self.desired_state.listed_output_pairs:
                    _, write_point = self.PM.get_control_point_pair(cp_id)
                    write_point.requested_value = output_value
                    self.PM.publish_point(write_point, force=immediately)
        else:
            print("Warning: PM is not an Active_Points_Manager, writing state does nothing.")

    
    
    def update_desired_state(self)->bool:
        #If the current state is the desired state, check if it's time to transition.
        #Return true if the desired state is updated.
        if self.in_desired_state:
            next_state = self.TM.next_state(self.current_state)
            if next_state != self.current_state.state:
                self.desired_state = next_state
                return True
            else:
                return False
        else:
            #I'm not sure exactly where the logic should be for being in limbo for too long should be.
            return False

    def print_update(self):
        if self.monitor:
            print(self.current_state.state.name, self.desired_state.name, 
                  self.monitor.get_time_in_state())
        else:
            print(self.current_state.state.name, self.desired_state.name,"no monitor active")

    def get_time_in_state(self) -> float:
        """Implement TimeProvider protocol"""
        return self.current_state.time_in_state

    def create_monitor(self, points_manager, state_point=None, time_point=None):
        """Create FSM monitor with given points manager and optional existing points"""
        monitor = FSMMonitor(
            fsm=self,
            points_manager=points_manager,
            state_point=state_point,
            time_point=time_point
        )
        if isinstance(points_manager, Active_Points_Manager):
            monitor.pm = points_manager  # Update monitor if we already have an active PM
        self.monitor = monitor  # Actually set the monitor reference