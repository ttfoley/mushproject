from collections import namedtuple
from datetime import datetime
from typing import Tuple, Sequence,Dict
from points import ControlPoint

VALID_OUTPUT_STATES = ["On","Off","Unknown"]

class StateOutputs(object):
    """Just a basic immutable type to DEFINE the outputs of a state.  This is just a dictionary of control points and their states."""
    def __init__(self,outputs:dict[str,str],control_points:Sequence[ControlPoint]):
        self.outputs = self.validated_outputs(outputs,control_points)

    ## 1/23 This should no longer be necessary, points should be validated before being written.
    def validated_outputs(self,outputs:dict[str,str],control_points:Sequence[ControlPoint])->dict[str,str]:
        #Make sure the outputs are valid
        available_cps = [cp.name for cp in control_points]
        for key,value in outputs.items():
            assert key in available_cps, f"Invalid control point {key}, doesn't exist in control points"
            assert value in VALID_OUTPUT_STATES, f"Invalid state for control point {key}:{value}"
        return outputs
    
    @property
    def control_point_names(self):
        return self.outputs.keys()
    

    def __eq__(self, other):
        if not isinstance(other, StateOutputs):
            return False
        return self.outputs == other.outputs

class State:
    #Every state better have the same control points
    #TODO: Would it better to have an "any" option for control points that don't matter, so we don't have to filter them out?
    def __init__(self,name,outputs:StateOutputs):
        self.name = name
        self.outputs = outputs

class Outputs:
    """
    To keep track of groups of outputs.  Methods for equality and comparison.
    Include "Unknown" as a valid control point state. 
    Valid value of outputs are "On","Off","Unknown". Values here refer to readback value
    #Note that the control points are sorted by name.  This is to make sure that the hash is consistent.
    #There should be no way to change the values of control points from here, but they should be kept live by the mqtt_handler.
    ## It seems redundant
    """
    def __init__(self,control_points:list[ControlPoint]):
        self._control_points = self.sort_and_validate(control_points)
        self.lookup = {cp._name:cp for cp in control_points}


    @property
    def point_names(self):
        return [cp._name for cp in self._control_points]
    
    @property
    def outputs(self):
        return {cp:cp._value for cp in self._control_points}  
      
    @property
    def outputs_str(self):
        return {cp._name:cp._value for cp in self._control_points}

    @property
    def is_unknown(self):
        return any([cp.state == "Unknown" for cp in self._control_points])

    def sort_and_validate(self,control_points:list[ControlPoint])->list[ControlPoint]:
        #Make sure the outputs are valid
        for cp in control_points:
            assert cp.state in ["On","Off","Unknown"], f"Invalid state for control point {cp.name}:{cp.state}"
        #Sort the outputs by name
        return sorted(control_points,key = lambda x: x._name)
    
    def match_state_output(self,state:State)->bool:
        #Check if the state outputs match the outputs of the actual.
        #note 
        return state.outputs.outputs == self.outputs_str

    def __eq__(self, other):
        """To compare two Outputs, they must have the same control points and the same values for each control point.
        I think I could get by with just comparing the dictionaries, but this is more explicit and gives better error messages.
        Note this does not include the "Unknown" state, as that is not a valid state for a state."""
        if not isinstance(other, Outputs):
            return False
        
        if len(self._control_points) != len(other._control_points):
            print("Different number of outputs")
            return False
        
        elif self.point_names != other.point_names:
            print("Different control points")
            return False

        elif self.is_unknown:
            #This is comparing two unknown states, which is always true.
            if other.is_unknown:
                return True
            #If I'm unknown, and the other isn't, then they're not equal.
            else:
                return False

        else:
            for point_name in self.point_names:
                if self.outputs[point_name] != other.outputs[point_name]:
                    return False
            return True
        
    def __repr__(self):
        return f"Outputs: {self.outputs}"
        
    def __hash__(self):
        #This is ugly, one example of why I want to get rid of type named_tuple
        point_names = sorted([point._name for point in self.outputs.keys()])
        output_values = []
        for point in point_names:
            for key in self.outputs.keys():
                if key._name == point:
                    output_values.append(self.outputs[key])
        hashed = ""
        for point_name,output_value in zip(point_names,output_values):
            hashed += f"{point_name}:{output_value},"
        hashed = hashed[:-1]

        return hash(hashed)



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
        #this probably isn't the best repr since the time object might have a lot of digits.
        return f"In state {self.state.name} from {self.time_started}"
