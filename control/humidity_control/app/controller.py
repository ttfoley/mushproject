import paho.mqtt.client as mqtt
from collections import namedtuple
from datetime import datetime
from typing import Tuple, Sequence,Dict
import time

#value better be ("On","Off","Unknown") 
#TODO: maybe this should be a class so we can do type checking and easier comparisons use __eq__ and __ne__?
output_value = namedtuple("output_value",["point_name","value"])
statetime_transition_rule = namedtuple("transition_rule",["rule_name","from_state","to_state","required_time"])


"""
Here we'll build controller class to handle writing and reading from output using MQTT and keeping trace of state and times. Maybe
that shouldn't all be in one.
"""

class ControlPoint:
    """
    Right now this does not verify its state with readback.  It's just a container for the state. I want control points to have a liveness/staleness, but
    I don't know if this is the best place to do it.  Something like a separate health monitor class?
    """
    def __init__(self, name, write_point, readback_point,republish_frequency_match = 60,republish_frequency_mismatch = 5):
        self.name = name
        self.write_point = write_point
        self.readback_point = readback_point
        self.state = "Unknown"
        self.output_value = output_value(self.name,self.state)
        self.requested_state = None
        self.time_start_state = datetime.now()
        self.time_last_published = datetime.now()
        self.republish_frequency_match = republish_frequency_match
        self.republish_frequency_mismatch = republish_frequency_mismatch
        #So we're resigning ourselves to no memory of the last state after a reboot, which seems fine for now

    def set_known_state(self, state):
        #This should only be used if you know the state from readback.
        #If state changed, restart the timer
        if self.state != state:
            self.time_start_state = datetime.now()
        self.state = state
        self.output_value = output_value(self.name,self.state)

    def time_in_state(self):
        return (datetime.now() - self.time_start_state).total_seconds()
    
    def time_since_last_published(self):
        return (datetime.now() - self.time_last_published).total_seconds()    

    def set_requested_state(self, state:output_value):
        assert state.value in ["On","Off"]
        self.requested_state = state.value

    def publish_requested_state(self, mqtt_handler):
        #Setting this at beginning so we don't spam mqtt channel.
        self.time_last_published = datetime.now()
        if self.requested_state == "On":
            mqtt_handler.publish(self.write_point, "on")
        elif self.requested_state == "Off":
            mqtt_handler.publish(self.write_point, "off")
        else:
            raise ValueError("Requested state must be On or Off")
        
    def publish(self,mqtt_handler,immediately=False):
        assert self.state in ["On","Off","Unknown"]
        if self.state != self.requested_state:
            if immediately:
                self.publish_requested_state(mqtt_handler)
            elif self.time_since_last_published() > self.republish_frequency_mismatch:
                self.publish_requested_state(mqtt_handler)
        elif self.time_since_last_published() > self.republish_frequency_match:
            self.publish_requested_state(mqtt_handler)
        

    def __eq__(self, other):
        #This is obviously not good enough, but it's a start.
        if not isinstance(other, ControlPoint):
            return False
        return self.name == other.name

    def __hash__(self):
        return hash(self.name)
    
    def __repr__(self) -> str:
        return f"ControlPoint {self.name}, state: {self.state}, requested_state: {self.requested_state}"


class Outputs:
    """
    To keep track of groups of outputs.  Used for defining states. Methods for equality and comparison.
    Include "Unknown" as a valid control point state.  Able to update, as this will track the live output values as determined by readback.
    Valid value of outputs are "On","Off","Unknown"
    #TODO: I don't like that this is a named_tuple.  I don't like that I have to use output_value to keep the name and value together. 
    ## It seems redundant
    """
    def __init__(self,outputs_values:dict[ControlPoint,output_value]):
        self.control_points = outputs_values.keys()
        self.outputs = self.sort_and_validate(outputs_values)
        self.is_unknown = self.any_unknown()

    def sort_and_validate(self,outputs_values:dict[ControlPoint,output_value])->dict[ControlPoint,output_value]:
        #Sort the outputs by control point name. Python now preserves dictionary order. It shouldn't matter but thought it would make testing easier.

        sorted_outputs_values = dict(sorted(outputs_values.items(), key=lambda item: item[0].name))
        #Check that all the outputs are valid values
        for _,output_value in outputs_values.items():

            if output_value.value not in ["On","Off","Unknown"]:
                raise ValueError(f"Invalid output value {output_value.value}")

        return sorted_outputs_values
    
    def update_single_output(self,control_point:ControlPoint,output_value:output_value):
        assert control_point in self.outputs.keys()
        assert output_value.value in ["On","Off","Unknown"]
        self.outputs[control_point] = output_value

    def any_unknown(self):
        return any([output_value.value == "Unknown" for output_value in self.outputs.values()])

    def __eq__(self, other):
        """To compare two Outputs, they must have the same control points and the same values for each control point.
        I think I could get by with just comparing the dictionaries, but this is more explicit and gives better error messages.
        Note this does not include the "Unknown" state, as that is not a valid state for a state."""
        if not isinstance(other, Outputs):
            return False
        
        if len(self.outputs) != len(other.outputs):
            print("Different number of outputs")
            return False
        
        elif self.outputs.keys() != other.outputs.keys():
            print("Different control points")
            return False

        elif self.any_unknown():
            #This is comparing two unknown states, which is always true.
            if other.any_unknown():
                return True
            else:
                return False

        else:
            for key in self.outputs.keys():
                if self.outputs[key] != other.outputs[key]:
                    return False
            return True
        
    def __repr__(self):
        return f"Outputs: {self.outputs}"
        
    def __hash__(self):
        #This is ugly, one example of why I want to get rid of type named_tuple
        point_names = sorted([point.name for point in self.outputs.keys()])
        output_values = []
        for point in point_names:
            for key in self.outputs.keys():
                if key.name == point:
                    output_values.append(self.outputs[key])
        hashed = ""
        for point_name,output_value in zip(point_names,output_values):
            hashed += f"{point_name}:{output_value},"
        hashed = hashed[:-1]

        return hash(hashed)



class State:
    #Every state better have the same control points
    #TODO: Would it better to have an "any" option for control points that don't matter, so we don't have to filter them out?
    def __init__(self,name,outputs:Outputs):
        self.name = name
        self.outputs = outputs

    def same_outputs(self,other):
        assert isinstance(other,State)
        return self.outputs == other.outputs
    





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
        pass


class Constraint:
    """
    Satisfied or not. Base class for time constaint and eventually other constraints.
    Note the definition of the constraint doesn't include the current state, so it can't be evaluated without it.
    This is intentional, I want this be the schema for constraints, and defer the actual evaluation.
    I wanted satisfied to be a property, but it needs the current state to be passed in.
    """
    def __init__(self):
        pass
    
    def satisfied(self,current_state:StateStatus)->bool:
        raise NotImplementedError
    

class StateTimeConstraint(Constraint):
    """
    A constraint that is satisfied if the state has been active for a certain amount of time (Seconds).
    Operators are just > and < for now.
    sat
    [gt,lt](greater than,less than) are  the only valid operators for now.
    I don't know if I should require the state it's expecting to be in. Seems better to leave that up to the Transition.
    required_time in seconds.
    """
    def __init__(self,required_time:float,operator:str = "gt"):
        assert operator in ["gt","lt"]
        self.operator = operator
        self.required_time = required_time

    def satisfied(self,current_state:StateStatus)->bool:
        time_in_state = current_state.time_in_state
        if self.operator == "gt":
            if time_in_state > self.required_time:
                return True
            return False
        elif self.operator == "lt":    
            if time_in_state < self.required_time:
                return True
            return False
        else:
            #shouldn't be able to get here.
            raise ValueError("Invalid operator")
        
    def __repr__(self) -> str:
        return "StateTimeConstraint, operator:{self.operator}, required_time:{self.required_time} sec"


class Transition:
    """
    Return a bool and the state to transition to. 
    Hopefully only one transition is active among all possible transitions.
    At the very least, a given state better have only one active transition.
    I wanted active to be a property, but I couldn't make it work while keeping Transition abstract.
    TODO A transition may eventually have more than one constraint.
    TODO A transition's constraints will be evaluated based on some joing with logical operators.
    I think that that current state should be passed in to active
    """
    def __init__(self,from_state:State,to_state:State,constraints:Sequence[Constraint]):
        self.from_state = from_state
        self.to_state = to_state
        self.constraints = constraints
    
    def active(self,current_state:StateStatus)->Tuple[bool,State]:
        ## If not active, return current state(to_state)
        raise NotImplementedError

class SingleTransition(Transition):
    """
    A transition that only has one constraint.
    """
    def __init__(self,from_state:State,to_state:State,constraints:Sequence[Constraint]):
        assert len(constraints) == 1
        super().__init__(from_state,to_state,constraints)

    def active(self,current_state:StateStatus)->Tuple[bool,State]:
        if self.from_state != current_state.state:
            print("The expected current state is {self.from_state.name}, but the current state is {current_state.state.name}")
            return False,self.from_state
        if self.constraints[0].satisfied(current_state):
            return True,self.to_state
        else:
            return False,self.from_state
        
    def __repr__(self) -> str:
        ##Incomplete for now until I get the constraints __repr__ working.
        return f"Transition {self.from_state.name} to {self.to_state.name} with constraint {self.constraints}"


class FSM:
    #A FSM for controlling the humidity.
    #You need an unknown state, and you need to know the initial desired state.
    #States will have rules for when to switch to the next state..
    #READ THIS Current state is StateStatus, desired and previous states are State. This is kind of confusing.  I need better names.
    def __init__(self, states:dict[str,State],transitions:Dict[str,Dict[Tuple[State,State],Transition]],initial_desired_state:State,mqtt_handler):
        self.desired_state = initial_desired_state
        self.mqtt_handler = mqtt_handler
        assert "Unknown" in states.keys()
        self.states = states
        self.transitions = transitions
        ###maybe current state should be passed in the general case?
        self.current_state = StateStatus(states["Unknown"])
        ##TODO I don't like this. We shouldn't have to do this and we're oversubscribing to topics for the time being.
        self.control_points = self.get_relevant_points()
        #This is the state of the outputs as determined by readback. I guess I could try to fetch known states from the start...
        self.outputs_state = self.initialize_outputs_unknown()
        self.previous_state = self.states["Unknown"]
        self.desired_state =  initial_desired_state
          
    def update_state(self)->bool:
        #This compares against readbacks.
        #Since we start in unknown, it will think we're in unknown for some nonzero amount of time regardless
        self.update_outputs_state()
        self.previous_state = self.current_state.state
        new_state = self.get_validated_state()
        if new_state != self.current_state.state:
            self.current_state = StateStatus(new_state)
            return True
        else:
            return False

    def update_outputs_state(self):
        #Look up the current state of the outputs and update the outputs_state
        for control_point in self.outputs_state.control_points:
            #I don't like using output_value here, or anywhere really. But I guess it never lets us separate the name from the value.
            current_output = output_value(control_point.name,control_point.state)
            self.outputs_state.update_single_output(control_point,current_output)


    def get_compatible_states(self)->Tuple[bool,list[State]]:
        #bool indicates if any were found
        # Returns a list of states that have the same outputs as the current outputs.
        compatible_states = []
        found = False
        for state in self.states.values():
            if state.outputs == self.outputs_state:
                found = True
                compatible_states.append(state)
        return found, compatible_states

    def get_validated_state(self)->State:
        """ Returns the state that match the outputs. This is too complicated right now.
        If the outputs match a single state, set that as the current state.  This could be "Unknown".
        elif the outputs match multiple states AND the desired state, choose the desired state as current state.
        elif the outputs match multine and the previous verified state, set that as the current state.
        else  set to "Unknown"

        CAREFUL: The current state may be stale in reality. We're not yet checking the freshness of output readbacks.
        """

        were_found,compatible_states = self.get_compatible_states()
        #print("compatible states:",[s.name for s in compatible_states])
        if were_found:
            if len(compatible_states) == 1:
                return compatible_states[0]
            else:
                #Note that order matters here.  If the desired state is in the compatible states, it will be chosen first.
                #This should always be what we want, I think.  Or does this throw us into Unknown too often?
                if self.desired_state in compatible_states:
                    return self.desired_state
                elif self.current_state.state in compatible_states:
                    return self.current_state.state
                else:
                    #print("Compatible states found, but no valid state found.")
                    #print("Compatible states:",[s.name for s in compatible_states])
                    return self.states["Unknown"]
        elif not were_found:
            #Don't know what causes this to happen....
            raise ValueError("No compatible states found")
        
        else:
            #This shouldn't be possible.
            print("Something really weird happened, here are the outputs.")
            print([f"{cp.name}:{cp.state}" for cp in self.outputs_state.control_points])
            print("The compatible states were: ",[s.name for s in compatible_states])
            raise ValueError("Something went wrong in get_validated_state")
        
    def in_desired_state(self):
        #If the current state is the desired state, return True
        #TODO Make this more robust.  Maybe we should check the outputs too.
        print(self.current_state.state.name,self.desired_state.name)
        if self.current_state.state.name == self.desired_state.name:
            return True
        return False

    def write_desired_state(self,immediately=False):
        #If the desired state is different from the current state, write the state.
        if not self.in_desired_state():
            for point,output in self.desired_state.outputs.outputs.items():
                point.set_requested_state(output)
                point.publish(self.mqtt_handler,immediately)

    def get_possible_transitions(self,type = "single_state_transitions")->list[Tuple[State,Transition]]:
        #Return the possible states to transition to.
        possible_transitions = []
        for transition_type in self.transitions.keys():
            for (from_state,to_state),transition in self.transitions[transition_type].items():
                if from_state == self.current_state.state:
                    possible_transitions.append((to_state,transition))
        return possible_transitions

    def get_transition_to(self)->State:
        #Return the state to transition to.  If no transition is active, return the current state.
        active_transitions = []
        possible_transitions = self.get_possible_transitions()
        for to_state,transition in possible_transitions:
            ##I guess returning new_state is redundant.
            ##TODO think about whether we should return the transition or the new state.
            ##TODOShould we make a transition named_tuple? Seems like it would enforce the structure.
            active,new_state = transition.active(self.current_state)
            if active:
                active_transitions.append(new_state)
        if len(active_transitions) == 1:
            return active_transitions[0]
        elif len(active_transitions) > 1:
            #I think we can do this since we hashed the states
            if len(set(active_transitions)) == 1:
                #More than one active transition, but they all go to the same state, hopefully you never see this.
                return active_transitions[0]
                
            else:
                #Should definitely never see this.
                raise ValueError("More than one active transition to different states")
        else:
            return self.current_state.state
    
    def update_desired_state(self)->bool:
        #If the current state is the desired state, check if it's time to transition.
        #Return true if the desired state is updated.
        if self.in_desired_state():
            next_state = self.get_transition_to()
            if next_state != self.current_state.state:
                self.desired_state = next_state
                return True
            else:
                return False
        else:
            #I'm not sure exactly where the logic should be for being in limbo for too long should be.
            return False

    def initialize_outputs_unknown(self):
        #We don't know in the very beginning what the outputs are.
        return Outputs({cp:output_value(cp.name,"Unknown") for cp in self.control_points})

    def get_relevant_points(self):
        #The relevant points should be the same for any state.  
        return [control_point for control_point in self.current_state.state.outputs.control_points]

    def print_update(self):
        print(self.current_state.state.name,self.desired_state.name,self.current_state.time_in_state)