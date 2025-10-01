from datetime import datetime
from typing import Tuple, Sequence, Dict, Optional


class State:
    #Every state better have the same control points
    #Dict[str,str] is [CP_name:desired_value of CP]
    #TODO: Would it better to have an "any" option for control points that don't matter, so we don't have to filter them out?
    #Todo, define __repr__, __eq__, __hash__ for this class
    def __init__(self,name,outputs:list):
        self.name = name
        self.outputs = outputs

    
    @property
    def listed_output_pairs(self) -> Sequence[Tuple[str, str]]:
        """Returns list of (cp_id, value) pairs in format ('controller/name', value)"""
        return [
            (f"{output['control_point']['controller']}/{output['control_point']['name']}", 
             output['value'])
            for output in self.outputs
        ]
    
    def matched_outputs(self, other_outputs: list) -> bool:
        return self.outputs == other_outputs
    
    def __repr__(self) -> str:
        return f"State {self.name} with outputs {self.outputs}"

    def __hash__(self) -> int:
        return hash(self.__repr__())

    @property
    def control_point_ids(self) -> set[str]:
        """Returns set of control point identifiers in format 'controller/name'"""
        return {
            f"{output['control_point']['controller']}/{output['control_point']['name']}"
            for output in self.outputs
        }

class UnknownState(State):
    def __init__(self, control_points: list[str]):
        outputs = [
            {"control_point": {"controller": cp.split('/')[0], "name": cp.split('/')[1]}, 
             "value": "unknown"} 
            for cp in control_points
        ]
        super().__init__("unknown", outputs)

class StateStatus:
    """To keep track of the FSMs current state and time in state"""
    def __init__(self, state: State):
        self.state = state
        self.time_started = datetime.now()

    @property
    def time_in_state(self):
        return (datetime.now() - self.time_started).total_seconds()
    
    def report(self):
        print(f"Current state: {self.state.name}, time started: {self.time_started}, elapsed time: {self.time_in_state}")

    def in_same_state(self, other: State) -> bool:
        assert isinstance(other, State)
        return self.state == other


class States_Manager:
    def __init__(self, states_config: Dict[str, list], initial_state: str):
        self._unknown_reasons = []  # [(datetime, reason)]
        self.states = self.build_states(states_config) 
        self.used_control_points = self.cps_used()
        self.states["unknown"] = UnknownState(self.used_control_points)
        self.initial_state = self.states[initial_state]

    def record_unknown_reason(self, reason: str):
        self._unknown_reasons.append((datetime.now(), reason))

    def get_state(self, state_name: str, reason: Optional[str] = None) -> State:
        if state_name == "unknown" and reason:
            self.record_unknown_reason(reason)
        return self.states[state_name]

    def build_states(self, states_config: Dict[str, list]) -> Dict[str, State]:
        states = {}
        for state_name, outputs in states_config.items():
            states[state_name] = State(state_name, outputs)
        return states
    
    def cps_used(self):
        """Returns the control points used by all states."""
        first_state = next(iter(self.states.values()))
        reference_points = first_state.control_point_ids
        
        for state in self.states.values():
            if state.control_point_ids != reference_points:
                raise ValueError(f"State {state.name} uses different control points: {state.control_point_ids} vs {reference_points}")
        
        return list(reference_points)
    
    def _get_CP_id(self,cp_info:dict)->str:
        return cp_info["controller"]+cp_info["name"]

    @property
    def state_names(self)->list[str]:
        return list(self.states.keys())