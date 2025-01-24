from controller2 import *
from typing import Dict,Sequence
from surveyor import Surveyor
## Where great new transitions are born! Full rewrite of the transitions modules to allow for more complex constraints and transitions.
## And to clean up areas of code that had to do extra work to make the old transitions work. And I also just didn't really like them.

"""A transition is defined between two states. Transitions occur when you're in the "from" state and all of the constraints
on the edge to the "to" state are satisfied. The constraints can now be pretty arbitrary and multi-level. At the base level, there are binary 
constraints like constr_1 = "time_in_state > 30." -> bool. But you can also make a complex constraint by combining multiple base constraints together.
These combinations of constraints as a whole still evaluate to a bool. We call this collection a ConstraintGroup. Now the most simple case
of state_time > 30 is just a ConstraintGroup with one constraint, which may seem like unnecessary overhead.. but I've written a script!
Finally, you can have multiple ConstraintGroups on a single transition (all OR'd together for now). The most obvious case where this would be helpful is if you were to wire all of your states 
to a "safe" off state. No matter what other ConstraintGroups are on that edge, you can always add a "safe" ConstraintGroup to bypass. Say, for example, the esp32 is
being weird so you don't actually know the state of the equipment and how long it's been running. You can have universal transitions to "Off" if you think it's been too long.
"""

class Constraint:
    """
    Satisfied or not. Base class for time constaint and eventually other constraints.
    Note the definition of the constraint doesn't include the current state, so it can't be evaluated without it.
    This is intentional, I want this be the schema for constraints, and defer the actual evaluation.
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


    def eval_string(self)->str:
        print(f"{self.surveyor.parse_dot_path(self.value_loc).value} {self.comparator} {self.threshold}")
        return f"{self.surveyor.parse_dot_path(self.value_loc).value} {self.comparator} {self.threshold}"
    
    @property
    def satisfied(self)->bool:
        eval_string = self.eval_string()
        print(f"Evaling: {eval_string}")
        return eval(eval_string)

    
class ConstraintGroup:
    """
    Combined multiple constraints together, ANDs them (all must be true.)
    """
    def __init__(self,name,constraints:Sequence[Constraint]):
        self.name = name
        self.constraints = constraints
    
    def satisfied(self)->bool:
        return all([con.satisfied for con in self.constraints])

class Transition:
    """
    Return a bool and the state to transition to. 
    Hopefully only one transition is active among all possible transitions.
    At the very least, a given state better have only one active transition.
    I wanted active to be a property, but I couldn't make it work while keeping Transition abstract.
    """
    def __init__(self,from_state:State,to_state:State,constraint_groups:Dict[str,ConstraintGroup]):
        self.from_state = from_state
        self.to_state = to_state
        self.constraint_groups = constraint_groups
    
    @property
    def active(self)->Tuple[bool,State]:
        return any([cg.satisfied() for cg in self.constraint_groups.values()]),self.to_state



class TransitionsManager:
    ##Transitions will should be a big  dict of dicts. The outer dict is keyed by the "from" state. The inner dict is keyed by the "to" state, and the value is a list of ConstraintGroups.
    def __init__(self, transitions_config: dict, states: Dict[str, State], surveyor):
        self.states = states
        self.surveryor = surveyor


    def next_state(self, cur_state: StateStatus) -> State:
        return self.states["Off"]


