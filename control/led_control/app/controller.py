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
        self.outputs = self.sort_and_validate(outputs_values)
        self.is_unknown = self.any_unknown()

    def sort_and_validate(self,outputs_values:dict[ControlPoint,output_value]):
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
    #Outputs are {control_point_name:state(On/Off)}
    #TODO: Would it better to have an "any" option for control points that don't matter, so we don't have to filter them out?
    def __init__(self,name,outputs:list[output_value],control_points:dict[str,ControlPoint],rules):
        self.name = name
        self.outputs = {op.point_name:op for op in outputs}
        self.relevant_points = [ov.point_name for ov in outputs]
        #Restrict access to control points to only those that are relevant to the state.
        self.control_points = {name:control_points[name] for name in control_points.keys() if name in self.relevant_points}
        self.rules = rules

    


class Humidity_Control:
    #A FSM for controlling the humidity.
    #States will have rules for when to switch to the next state.
    # Unknown is not a valid state. There isn't an actuall State instance for it.
    def __init__(self, states:dict[str,State],mqtt_handler,initial_desired_state ="Off"):
        self.desired_state = initial_desired_state
        self.mqtt_handler = mqtt_handler
        self.states = states
        self.control_points = self.get_relevant_points()
        #Current states by name of states. Including "Unknown" for when we don't know the state.
        self.prev_state = "Unknown"
        self.current_state = "Unknown"
        self.time_start_state = datetime.now()
        self.time_in_state = 0
        self.update_state()

    def update_state(self):
        #Since we start in unknown, it will think we're in unknown for some nonzero amount of time regardless of whether the s
        self.prev_state = self.current_state
        self.current_state = self.get_current_state()
        now = datetime.now()
        if self.prev_state != self.current_state:
            self.time_start_state = now

        self.time_in_state = (now - self.time_start_state).total_seconds()


    def get_current_state(self):
        ##If the outputs match multiple states AND the desired state, choose the desired state as current state.
        ##Otherwise, set to "Unknown"
        output_values = [output_value(point_name,self.control_points[point_name].state) for point_name in self.control_points.keys()]
        #print(output_values)
        matching_states = []
        for state in self.states.values():
            if self.outputs_match_state(output_values,state):
                matching_states.append(state)

        if len(matching_states) == 1:
            return matching_states[0].name
        elif len(matching_states) > 1:
            if self.desired_state in [state.name for state in matching_states]:
                return self.desired_state
            else:
                return "Unknown"
        else:
            return "Unknown"

    def outputs_match_state(self,outputs:list[output_value],state:State):
        match = True
        for output in outputs:
            if output.point_name not in state.relevant_points:
                match = False
                break
            if state.outputs[output.point_name].value == output.value:
                match = True
            else:
                match = False
                break
        return match

    def in_desired_state(self):
        #If the current state is the desired state, return True
        if self.current_state == self.desired_state:
            return True
        return False

    def get_relevant_points(self):
        #The relevant points should be the same for any state.
        random_state = list(self.states.values())[0]
        return random_state.control_points

    def write_desired_state(self):
        #If the desired state is different from the current state, write the state.
        if self.desired_state != self.current_state:
            for point in self.control_points.values():
                point.set_requested_state(self.states[self.desired_state].outputs[point.name].value)
                point.publish(self.mqtt_handler)


    def current_state_time_satisfied(self):
        #this is ugly, too much indexing not enough transparency
        if self.current_state != "Unknown":
            if self.time_in_state > self.states[self.current_state].rules.required_time:
                return True
            return False
        elif self.current_state == "Unknown":
            #We're always ready to leave unknown state??
            return True
        else:
            raise ValueError("Current state is not valid")
        

    def update_desired_state(self):
        #Returns true if the desired state has been changed
        # If the current state has been satisfied, move to the next state.
        #If the current state is unknown, default to Off.
        starting_desired_state = self.desired_state
        if self.current_state_time_satisfied():
            if self.current_state == "Unknown":
                self.desired_state = "Off"
            else:
                self.desired_state = self.states[self.current_state].rules.to_state

        if self.desired_state != starting_desired_state:
            return True
        return False
            


