import paho.mqtt.client as mqtt
import json
from datetime import datetime
from points import Remote_Write,Remote_Read,Virtual_Sensor,ControlPoint
from states import State,StateStatus,Outputs
from typing import Tuple,Dict
from transitions import TransitionsManager



class FSM:
    #A FSM for controlling the humidity.
    #You need an unknown state, and you need to know the initial desired state.
    #States will have rules for when to switch to the next state..
    #Note that control point state and thus outputs is updated by the mqtt_handler. 
    #READ THIS Current state is type StateStatus, desired and previous states are type State. This is kind of confusing.  I need better names.
    def __init__(self,control_points:list[ControlPoint], states:dict[str,State],transitions:TransitionsManager,initial_desired_state:State,mqtt_handler):
        self.desired_state = initial_desired_state
        self.mqtt_handler = mqtt_handler
        assert "Unknown" in states.keys()
        self.states = states
        self.transitions = transitions
        self.control_points = control_points
        self.outputs = self.initialize_outputs()
        ###maybe current state should be passed in the general case?
        self.current_state = StateStatus(states["Unknown"])
        self.previous_state = self.states["Unknown"]
        self.desired_state =  initial_desired_state
        self.state = Virtual_Sensor(self.current_state.state,"Current State of the FSM.")
        self.time_in_state = Virtual_Sensor(self.current_state.time_in_state,"Time in the current active state.")
          

        

    def initialize_outputs(self)->Outputs:
        #We don't know in the very beginning what the outputs are.
        return Outputs(self.control_points)
    
    def update_state(self)->bool:
        #Outputs are updated by the mqtt_handler.  This just updates the current state.
        #Since we start in unknown, it will think we're in unknown for some nonzero amount of time regardless
        #This creates a new object if the state has changed.
        ##I don't like how these virtual sensors are adding a mess to this whole ting.
        self.previous_state = self.current_state.state
        new_state = self.get_validated_state()
        if new_state != self.current_state.state:
            self.current_state = StateStatus(new_state)## Triggers time upon initialization.
            self.state.value = new_state
            self.time_in_state.value = 0
            return True
        else:
            self.time_in_state.value = self.current_state.time_in_state
            return False
    @property
    def control_point_lookup(self):
        return {cp._name:cp for cp in self.control_points}

    def get_compatible_states(self)->Tuple[bool,list[State]]:
        #bool indicates if any were found
        # Returns a list of states that have the same outputs as the current outputs.
        found = False
        compatible_states = []
        for _,state in self.states.items():
            if self.outputs.match_state_output(state):
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
            print([f"{cp._name}:{cp._value}" for cp in self.control_points])
            print("The compatible states were: ",[s.name for s in compatible_states])
            raise ValueError("Something went wrong in get_validated_state")
        
    def in_desired_state(self):
        #If the current state is the desired state, return True
        #TODO Make this more robust.  Maybe we should check the outputs too.
        if self.current_state.state.name == self.desired_state.name:
            return True
        return False

    def write_desired_state(self,immediately=False):
        #If the desired state is different from the current state, write the state.
        if not self.in_desired_state():
            for point,output_value in self.desired_state.outputs.outputs.items():
                live_point = self.control_point_lookup[point]
                live_point.set_requested_value(output_value)
                live_point.publish(self.mqtt_handler,immediately)

    
    
    def update_desired_state(self)->bool:
        #If the current state is the desired state, check if it's time to transition.
        #Return true if the desired state is updated.
        if self.in_desired_state():
            next_state = self.transitions.next_state(self.current_state)
            if next_state != self.current_state.state:
                self.desired_state = next_state
                return True
            else:
                return False
        else:
            #I'm not sure exactly where the logic should be for being in limbo for too long should be.
            return False

    def print_update(self):
        print(self.current_state.state.name,self.desired_state.name,self.current_state.time_in_state)