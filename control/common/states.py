from datetime import datetime
from typing import Tuple, Sequence,Dict

VALID_OUTPUT_STATES = ["On","Off","Unknown"]

class State:
    #Every state better have the same control points
    #Dict[str,str] is [CP_name:desired_value of CP]
    #TODO: Would it better to have an "any" option for control points that don't matter, so we don't have to filter them out?
    #Todo, define __repr__, __eq__, __hash__ for this class
    def __init__(self,name,outputs:Dict[str,str]):
        self.name = name
        self.outputs = outputs

    
    @property
    def listed_output_pairs(self)->Sequence[Tuple[str,str]]:
        #Returns list of (cp,value) pairs. Like I used to have that name_tuple.
        # his eased some confusion from dicts at some points
        return [(cp,value) for (cp,value) in self.outputs.items()]
    
    def matched_outputs(self,other_putputs: Dict[str,str])->bool:
        return self.outputs == other_putputs
    
    def __repr__(self) -> str:
        return f"State {self.name} with outputs {self.outputs}"

    def __hash__(self) -> int:
        return hash(self.__repr__())

class StateStatus(object):
    """
    To keep track of the FSMs current state and time in state. 
    IMPORTANT: To make sure this whole thing remains a state machine, this better not contain anything that isn't an "attribute" of the CURRENT STATE.
    TODORepresents the current state of the FSM, so we should replace calls to the current_state with calls to this 
    Potentially other attributes to be added later
    Typical use case should be to initialize this to Unknown state and then update it as the FSM runs. Note that in that case, 
    the time in state will be nonzero by the time the FSM starts. That's kind of unfortunate, but I don't think it breaks anything.
    TODO Mark exit time.
    """

    def __init__(self,state:State):
        self.state = state
        self.time_started = datetime.now()


    @property
    def time_in_state(self):
        return (datetime.now() - self.time_started).total_seconds()
    
    def report(self):
        print(f"Current state: {self.state.name}, time started: {self.time_started}, elapsed time: {self.time_in_state}")

    def in_same_state(self, other:State)->bool:
        assert isinstance(other,State)
        return self.state == other
    
    def __repr__(self) -> str:
        #1/23 don't even know why we need this?
        #this probably isn't the best repr since the time object might have a lot of digits.
        return f"In state {self.state.name} from {self.time_started}"
