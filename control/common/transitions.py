from controller import *
from typing import Dict,Sequence,Tuple
from collections import defaultdict
from surveyor import Surveyor
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
    def __init__(self,id:str,value:str,threshold:str,comparator:str,units:str,surveyor:Surveyor):
        self.id = id
        self.value_loc = value
        self.threshold = threshold
        self.comparator = comparator
        self.units = units
        self.surveyor = surveyor

    #I wish this was all assured beforehand by construction, but with the way the fsm virtual points are created after surveyor is constructed, I want to be sure.
    @property
    def val_exists(self)->bool:
        return self.surveyor.value_exists(self.value_loc)
    
    def eval_string(self)->str:
        if self.val_exists:
            val = self.surveyor.parse_dot_path(self.value_loc)[1].value
            #print(f"{self.surveyor.parse_dot_path(self.value_loc).value} {self.comparator} {self.threshold}")
            return f"{val} {self.comparator} {self.threshold}"
        else:
            raise ValueError(f"Value {self.value_loc} does not exist in the surveyor.")
    
    @property
    def satisfied(self)->bool:
        #print(f"Evaling: {self.eval_string()}")
        eval_string = self.eval_string()
        #print(eval(eval_string))
        #print(f"Evaling: {eval_string}")
        return eval(eval_string)

    
class Constraint_Group:
    """
    Combined multiple constraints together, ANDs them (all must be true.)
    """
    def __init__(self,name,constraints:Sequence[Constraint]):
        self.name = name
        self.constraints = constraints

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
    
    """
    def __init__(self,from_state:State,to_state:State,constraint_groups:Dict[str,Constraint_Group]):
        self.from_state = from_state
        self.to_state = to_state
        #These constraint groups are all OR'd together.
        self.constraint_groups = constraint_groups
    
    @property
    def active(self)->bool:
        return any([cg.satisfied for cg in self.constraint_groups.values()])



class Transitions_Manager:
    ##Transitions will should be a big  dict of dicts. The outer dict is keyed by the "from" state. The inner dict is keyed by the "to" state, and the value is a list of Constraint_Groups.
    #!!!! As is, this assumes there are no self-transitions.
    def __init__(self, transitions_config: dict, states: Dict[str, State], surveyor:Surveyor):
        self.transitions_config = transitions_config
        self.states = states
        self.surveyor = surveyor
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
            print(f"Multiple possible transitions from from {cur_state.state.name}: {[state.name for state in end_states]}")
            raise ValueError("Panic! Multiple transitions active. This should not happen.")
        elif len(end_states) == 0:
            #We must stay put
            return cur_state.state
        else:
            #valid transition, let's go there.
            return end_states[0]
    

    def build(self)->Dict[str,Dict[str,Transition]]:
        all_transitions = defaultdict(dict)
        trans_config = self.transitions_config["Transitions"]
        for start_state in self.states.values():
            for end_state in self.states.values():
                if start_state != end_state:
                    try:
                        #print(start_state.name,end_state.name)
                        CG_defs= trans_config[start_state.name][end_state.name]["constraint_groups"]
                        D_CGs = {}
                        for CG_name,values in CG_defs.items():
                            D_CGs[CG_name] = {}
                            constraints_d = []
                            for ix,values in values["constraints"].items():
                                def_vals = values["definition"]
                                constraints_d.append(Constraint(ix,def_vals["value"],def_vals["threshold"],def_vals["comparator"],def_vals["units"],self.surveyor))
                            D_CGs[CG_name] = Constraint_Group(CG_name,constraints_d)
                        #print(D_CGs)
                        all_transitions[start_state.name][end_state.name] = Transition(start_state,end_state,D_CGs)

                    except:
                        pass
        return all_transitions

            
    


        


