import paho.mqtt.client as mqtt
from collections import namedtuple
from datetime import datetime
import time

#value better be ("On","Off","Unknown") 
#TODO: maybe this should be a class so we can do type checking and easier comparisons use __eq__ and __ne__?
output_value = namedtuple("output_value",["point_name","value"])
transition_rule = namedtuple("transition_rule",["rule_name","from_state","to_state","required_time"])


"""
Here we'll build controller class to handle writing and reading from output using MQTT and keeping trace of state and times. Maybe
that shouldn't all be in one.
"""

class ControlPoint:
    def __init__(self, name, write_point, readback_point,republish_frequency = 5):
        self.name = name
        self.write_point = write_point
        self.readback_point = readback_point
        self.state = "Unknown"
        self.output_value = output_value(self.name,self.state)
        self.requested_state = None
        self.time_start_state = datetime.now()
        self.time_last_published = datetime.now()
        self.republish_frequency = republish_frequency
        #So we're resigning ourselves to no memory of the last state after a reboot, which seems fine for now

    def set_known_state(self, state):
        #This should only be used if you know the state from readback.
        #If state changed, restart the timer
        if self.state != state:
            self.time_start_state = datetime.now()
        self.state = state

    def time_in_state(self):
        return (datetime.now() - self.time_start_state).total_seconds()
    
    def time_since_last_published(self):
        return (datetime.now() - self.time_last_published).total_seconds()    

    def set_requested_state(self, state):
        assert state in ["On","Off"]
        self.requested_state = state

    def publish_requested_state(self, mqtt_handler):
        #Setting this at beginning so we don't spam mqtt channel.
        self.time_last_published = datetime.now()
        if self.requested_state == "On":
            mqtt_handler.publish(self.write_point, "on")
        elif self.requested_state == "Off":
            mqtt_handler.publish(self.write_point, "off")
        else:
            raise ValueError("Requested state must be On or Off")
        
    def publish(self,mqtt_handler):
        if self.time_since_last_published() > self.republish_frequency:
            if self.requested_state is not None:
                self.publish_requested_state(mqtt_handler)
            else:
                print(f"Requested state not set for {self.name}")

    def __eq__(self, other):
        #This is obviously not good enough, but it's a start.
        if not isinstance(other, ControlPoint):
            return False
        return self.name == other.name

    def __hash__(self):
        return hash(self.name)


class Outputs:
    """
    To keep track of groups of outputs.  Used for defining states. Methods for equality and comparison.
    Include "Unknown" as a valid state.  Able to update, as this will track the live output values as determined by readback.
    Valid value of outputs are "On","Off","Unknown"
    """
    def __init__(self,outputs_values:dict[ControlPoint,output_value]):
        self.control_points = outputs_values.keys()
        self.outputs = self.sort_and_validate(outputs_values)
        self.is_unknown = self.any_unknown()

    def sort_and_validate(self,outputs_values:dict[ControlPoint,output_value])->dict[ControlPoint,output_value]:
        #Sort the outputs by control point name.
        #Check that all the outputs are valid values
        sorted_outputs = dict(sorted(outputs_values.items(), key=lambda item: item[0].name))
        for value in outputs_values.values():
            if value not in ["On","Off","Unknown"]:
                raise ValueError("Invalid output value")

        return sorted_outputs
    
    def update_single_output(self,control_point:ControlPoint,value:output_value):
        assert control_point in self.outputs.keys()
        assert value in ["On","Off","Unknown"]
        self.outputs[control_point] = value

    def any_unknown(self):
        return any([value == "Unknown" for value in self.outputs.values()])

    def __eq__(self, other):
        """To compare two outputs, they must have the same control points and the same values for each control point.
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
        
    def __hash__(self):
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
    def __init__(self,name,outputs:Outputs,rules:transition_rule):
        self.name = name
        self.outputs = outputs
        self.rules = rules

    def same_outputs(self,other):
        assert isinstance(other,State)
        return self.outputs == other.outputs

class Humidity_Control:
    #A FSM for controlling the humidity.
    #States will have rules for when to switch to the next state..
    def __init__(self, states:dict[str,State],initial_desired_state:State,mqtt_handler):
        self.desired_state = initial_desired_state
        self.mqtt_handler = mqtt_handler
        self.states = states
        self.unknown_state = states["Unknown"]
        self.control_points = self.get_relevant_points()
        #This is the state of the outputs as determined by readback. I guess I could try to fetch known states from the start...
        self.outputs_state = self.initialize_outputs_unknown()
        self.prev_state = self.unknown_state
        self.current_state = self.unknown_state
        self.desired_state =  initial_desired_state
        self.time_start_state = datetime.now()
        self.time_in_state = 0

    def initialize_outputs_unknown(self):
        #We don't know in the very beginning what the outputs are.
        return Outputs({cp:output_value(cp.name,"Unknown") for cp in self.control_points})

    def get_relevant_points(self):
        #The relevant points should be the same for any state.  
        return [control_point for control_point in self.unknown_state.outputs.control_points]
                              
    def update_state(self):
        #Since we start in unknown, it will think we're in unknown for some nonzero amount of time regardless
        self.prev_state = self.current_state
        self.current_state = self.get_current_state()
        now = datetime.now()
        if self.prev_state != self.current_state:
            self.time_start_state = now

        self.time_in_state = (now - self.time_start_state).total_seconds()


    def get_outputs_state(self):
        #Look up the current state of the outputs and update the outputs_state
        for control_point in self.outputs_state.control_points:
            #I don't like using output_value here, or anywhere really. But I guess it never lets us separate the name from the value.
            current_output = output_value(control_point.name,control_point.state)
            self.outputs_state.update_single_output(control_point,current_output)


    def get_compatible_states(self)->list[State]:
        #Returns a list of states that have the same outputs as the current outputs.
        compatible_states = []
        for state in self.states.values():
            if state.outputs == self.outputs_state:
                compatible_states.append(state)
        return compatible_states

    def get_current_state(self)->State:
        """If the outputs match a single state, set that as the current state.  This could be "Unknown".
        elif the outputs match multiple states AND the desired state, choose the desired state as current state.
        elif the outputs match multine and the previous verified state, set that as the current state.
        else  set to "Unknown"

        CAREFUL: this is using current state as a proxy for the last verified state (elif self.current_state in compatible_states:).
        The current state may be stale in reality.
        """

        compatible_states = self.get_compatible_states()
        if len(compatible_states) == 1:
            return compatible_states[0]
        elif len(compatible_states) > 1:
            #Note that order matters here.  If the desired state is in the compatible states, it will be chosen first.
            #This should always be what we want, I think.  Or does this throw us into Unknown too often?
            if self.desired_state in compatible_states:
                return self.desired_state
            elif self.current_state in compatible_states:
                return self.current_state
            else:
                return self.unknown_state
        else:
            #This should never happen, so maybe raise an error?
            raise ValueError("No compatible states found")
        
    def in_desired_state(self):
        #If the current state is the desired state, return True
        if self.current_state == self.desired_state:
            return True
        return False


    def write_desired_state(self):
        #If the desired state is different from the current state, write the state.
        if self.desired_state != self.current_state:
            for point,output in self.desired_state.outputs.outputs.items():
                point.set_requested_state(output)
                point.publish(self.mqtt_handler)


    def current_state_time_satisfied(self):
        #This should be a method of the state class, maybe?
        #In any case, it's too specific right now to the way our rules are defined.
        if self.time_in_state > self.current_state.rules.required_time:
            return True
        return False

        

    def update_desired_state(self):
        #Returns true if the desired state has been changed
        # If the current state has been satisfied, move to the next state.
        starting_desired_state = self.desired_state
        if self.current_state_time_satisfied():
            #The fallback state is "Off" if the current state is unknown. This should be in the rules.
            self.desired_state = self.states[self.current_state.rules.to_state]

        if self.desired_state != starting_desired_state:
            return True
        return False
            


