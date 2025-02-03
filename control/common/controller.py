from states import State,StateStatus
from transitions import Transitions_Manager
from surveyor import Surveyor




class FSM:
    #A FSM for controlling the humidity.
    #You need an unknown state, and you need to know the initial desired state.
    #States will have rules for when to switch to the next state..
    #Note that control point state and thus outputs is updated by the mqtt_handler. 
    #READ THIS Current state is type StateStatus, desired and previous states are type State. This is kind of confusing.  I need better names.
    def __init__(self, states:dict[str,State],transitions:Transitions_Manager,surveyor:Surveyor,initial_desired_state:State):
        self.desired_state = initial_desired_state
        self.states = states
        self.surveyor = surveyor
        self.transitions = transitions
        ###maybe current state should be passed in the general case?
        self.current_state = StateStatus(self.states["Unknown"])
        self.previous_state = self.states["Unknown"]
        #the use of the word "state" is getting confusing. Sorry future me.
        # self.state = Virtual_Sensor(self.current_state.state,"Current State of the FSM.")
        # self.time_in_state = Virtual_Sensor(self.current_state.time_in_state,"Time in the current active state.")
          

        
    
    def update_state(self)->bool:
        #Outputs are updated by the mqtt_handler.  This just updates the current state.
        #Since we start in unknown, it will think we're in unknown for some nonzero amount of time regardless
        #This creates a new object if the state has changed.
        ##I don't like how these virtual sensors are adding a mess to this whole thing. Should be some sort of wrapper for it.
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


    def get_validated_state(self)->State:
        """ Compatible states now handled by surveyor. Still need logic to try to handle if compatible states.
        """

        compatible_states = self.surveyor.get_compatible_states(self.states)

        if len(compatible_states) == 0:
            return self.states["Unknown"]
        
        if len(compatible_states) == 1:
            return compatible_states[0]
        
        if len(compatible_states) > 1:
            #check if the desired state is in the compatible states
            if self.desired_state in compatible_states:
                return self.desired_state
            #else check if it's the current state
            elif self.current_state.state in compatible_states:
                return self.current_state.state
            ###something goofy going on. Should we just set it to unkown? or raise an exception?
            else:
                return self.states["Unknown"]
        
        # Default return in case all conditions fail, linter told me I was missing a path but i couldn't see it.
        return self.states["Unknown"]
                
        

        
    def in_desired_state(self):
        #If the current state is the desired state, return True
        #TODO Make this more robust.  Maybe we should check the outputs too.
        if self.current_state.state.name == self.desired_state.name:
            return True
        return False

    def write_desired_state(self,immediately=False):
        #If the desired state is different from the current state, write all of the outputs to make the current state the desired state.
        #Has extra flag to tell point to publish the point immediately, don't know if I ever used it.
        if not self.in_desired_state():
            cp_val_pairs  = self.desired_state.listed_output_pairs
            for (cp,output_value) in cp_val_pairs:
                live_point = self.surveyor.cp_lookup(cp)
                live_point.set_requested_value(output_value)
                live_point.publish(immediately)

    
    
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