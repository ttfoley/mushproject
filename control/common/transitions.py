from controller import *
from typing import Dict,Sequence,Tuple
from collections import defaultdict
from points_manager import Points_Manager
## Where great new transitions are born! Full rewrite of the transitions modules to allow for more complex constraints and transitions.
## And to clean up areas of code that had to do extra work to make the old transitions work. And I also just didn't really like them.

"""A transition is defined between two states. Transitions occur when you're in the "from" state and all of the constraints
on the edge to the "to" state are satisfied. The constraints can now be pretty arbitrary and multi-level. At the base level, there are binary 
constraints like constr_1 = "time_in_state > 30." -> bool. But you can also make a complex constraint by combining multiple base constraints together.
These combinations of constraints as a whole still evaluate to a bool. We call this collection a Constraint_Group. Now the most simple case
of state_time > 30 is just a Constraint_Group with one constraint, which may seem like unnecessary overhead.. but I've written a script!
Finally, you can have multiple Constraint_Groups on a single transition (all OR'd together for now). The most obvious case where this would be helpful is if you were to wire all of your states 
to a "safe" off state. No matter what other Constraint_Groups are on that edge, you can always add a "safe" Constraint_Group to bypass. Say, for example, the esp32 is
being weird so you don't actually know the state of the equipment and how long it's been running. You can have universal transitions to "Off" if you think it's been too long.
"""

class Constraint:
    """
    Satisfied or not. Base class for time constaint and eventually other constraints.
    Note the definition of the constraint doesn't include the current state, so it can't be evaluated without it.
    This is intentional, I want this be the schema for constraints, and defer the actual evaluation.
    IMPORTANT: At time of constraint declaration, the value may not be in the surveyor, as in the case of "Virtual Pints" attached to the FSM.
    I wanted satisfied to be a property, but it needs the current state to be passed in.
    What about values that are supposed to remain strings?
    """
    def __init__(self,id:int,value:int,comparand:str,comparator:str,units:str,PM:Points_Manager):
        self.id = id
        self.value_uuid = value
        self.comparand = comparand
        self.comparator = comparator
        self.units = units
        self.PM = PM


    @property
    def value_exists(self)->bool:
        return self.PM.value_exists(self.value_uuid)
    
    def eval_string(self)->str:
        if self.value_exists:
            val = self.PM.get_value(self.value_uuid).value
            assert type(val) == type(self.comparand)
            return f"{val} {self.comparator} {self.comparand}"
        else:
            raise ValueError(f"Value {self.value_uuid} does not exist in the surveyor.")
    
    @property
    def satisfied(self)->bool:
        eval_string = self.eval_string()
        return eval(eval_string)

    
class Constraint_Group:
    """
    Combined multiple constraints together, ANDs them (all must be true.)
    """
    def __init__(self,id:int,constraints:Sequence[Constraint],priority:int = 0):
        self.id = id
        self.constraints = constraints
        self._priority = priority

    @property
    def satisfied(self)->bool:
        #print(self.constraints)
        return all([constraint.satisfied for constraint in self.constraints])

class Transition:
    """
    Return a bool and the state to transition to. 
    Constraint groups are created from config file and are tied to specific state pairs there.
    Hopefully only one transition is active among all possible transitions.
    At the very least, a given state better have only one active transition.
    2/2 - Now CGs have attribute _priority, which is used to sort them. 
    This is useful for the case where you have multiple CGs on a single transition, and you want to prioritize them.
    This doesn't immediately help anything, but in the future it could be used to make the transitions more robust, 
    I'm thinking like forced manual over-rides have their own priority level. Maybe it's just unneccesary complexity right now.
    
    """
    def __init__(self,from_state:State,to_state:State,constraint_groups:list[Constraint_Group]):
        self.from_state = from_state
        self.to_state = to_state
        #These constraint groups are all OR'd together.
        self.constraint_groups = constraint_groups
    
    def add_constraint_group(self,CG:Constraint_Group):
        assert CG.id not in self.constraint_groups
        self.constraint_groups[CG.id] = CG

    @property
    def prioritized_cgs(self)->Sequence[Constraint_Group]:
        #if same priority, order is not guaranteed.
        return sorted(self.constraint_groups,key = lambda x: x._priority)
    
    @property
    def active(self)->bool:
        active = False
        for cg in self.prioritized_cgs:
            if cg.satisfied:
                active = True
                break

        return active

def build_transition(from_state:str,to_state:str,config:dict,PM:Points_Manager)->Transition:
    # should probably check this before even calling.
    assert from_state in config
    assert to_state in config[from_state]
    transition_config = config[from_state][to_state]
    for CG_id, CG in transition_config['constraint_groups'].items():
        CG_id = int(CG_id)
        constraints = []
        for constraint_id, constraint in CG['constraints'].items():
            constraint_id = int(constraint_id)
            constraints.append(Constraint(constraint_id,constraint['value_uuid'],constraint['comparand'],constraint['comparator'],constraint['units'],PM))
        constraint_group = Constraint_Group(CG_id,constraints,CG['priority'])
        transition.add_constraint_group(constraint_group)

def build_constraint(config:dict,PM:Points_Manager)->Constraint:
    return Constraint(config['id'],config['value_uuid'],config['comparand'],config['comparator'],config['units'],PM)

class Transitions_Manager:
    ##Transitions will should be a big  dict of dicts. The outer dict is keyed by the "from" state. The inner dict is keyed by the "to" state, and the value is a list of Constraint_Groups.
    #!!!! As is, this assumes there are no self-transitions.
    def __init__(self, transitions_config: dict, states: Dict[str, State], PM:Points_Manager):
        self.transitions_config = transitions_config
        self.states = states
        self.PM = PM
        #I'm being inconsistent with how things are constructed. For Surveyor I made a separate class for some reaason.
        self.transitions = self.build()

    def next_state(self, cur_state: StateStatus) -> State:
        #Note that the transitions array is indexed by state name, while we're supposed to return a state.
        relevant_transitions = self.transitions[cur_state.state.name]
        end_states = []
        for end_state, transition in relevant_transitions.items():
            if transition.active:
                print("transitiion_activated",end_state)
                end_states.append(self.states[end_state])
        
        if len(end_states) >1:
            """
            This is tricky, I can see this actually happening. For example, if the sensors time out for a while, 
            then we could have multiple transitions activate as sensors come online. I should be able to design
            transitions for now to avoid this, so I'm just going to make it panic for now. Another option is to return the first
            transition.
            """
            #Maybe CGs should have a priority level. But for now, this is a panic.
            #I could imagine 
            print(f"Multiple possible transitions from from {cur_state.state.name} to: {[state.name for state in end_states]}")
            raise ValueError("Panic! Multiple transitions active. This should not happen.")
        elif len(end_states) == 0:
            #We must stay put
            return cur_state.state
        else:
            #valid transition, let's go there.
            return end_states[0]
    



            
    


        


