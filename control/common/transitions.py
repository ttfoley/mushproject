from typing import Dict,Sequence
from points_core import PointsRegistry
from states import State,States_Manager
import time

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
    Satisfied or not. Base class for time constraint and eventually other constraints.
    Note the definition of the constraint doesn't include the current state, so it can't be evaluated without it.
    This is intentional, I want this be the schema for constraints, and defer the actual evaluation.
    """
    def __init__(self, registry: PointsRegistry, definition: dict):
        self.registry = registry
        self._definition = definition
        self._converted_comparand = self._convert_value(definition['comparand'])
        self.last_eval = None
    
    @property
    def comparator(self):
        return self._definition['comparator']
        
    @property
    def comparand(self):
        return self._converted_comparand
        
    @property
    def value_uuid(self):
        return self._definition['value_uuid']
        
    @property
    def units(self):
        return self._definition['units']
    
    def _convert_value(self, value):
        """Convert value based on units"""
        if self.units == 'float':
            return float(value)
        elif self.units == 'int':
            return int(value)
        ##Do nothing for strings
        return value
    
    def update_comparand(self, new_comparand):
        """Update comparand with validation"""
        self._converted_comparand = self._convert_value(new_comparand)
        self._definition['comparand'] = new_comparand
    
    @property
    def value_exists(self)->bool:
        return self.registry.value_exists(self.value_uuid)
    
    def eval_string(self) -> str:
        if not self.value_exists:
            raise ValueError(f"Value {self.value_uuid} does not exist in registry.")
        
        point = self.registry.get_point(self.value_uuid)
        val = self._convert_value(point.value)
        
        if val is None:
            return "False"  # If value is None, constraint can't be satisfied
        
        return f"{str(val)} {self.comparator} {self.comparand}"
    
    def satisfied(self) -> bool:
        if not self.value_exists:
            raise ValueError(f"Value {self.value_uuid} does not exist in the surveyor.")
        
        point = self.registry.get_point(self.value_uuid)
        val = self._convert_value(point.value)
        
        if val is None:
            return False
            
        assert type(val) == type(self.comparand)
        result = False
        
        if self.comparator == ">=":
            result = val >= self.comparand
        elif self.comparator == "<=":
            result = val <= self.comparand
        elif self.comparator == "==":
            result = val == self.comparand
        elif self.comparator == "!=":
            result = val != self.comparand
        elif self.comparator == ">":
            result = val > self.comparand
        elif self.comparator == "<":
            result = val < self.comparand
        else:
            raise ValueError(f"Unknown comparator: {self.comparator}")
            
        # Log evaluation details
        self.last_eval = {
            "value": val,
            "comparator": self.comparator,
            "comparand": self.comparand,
            "result": result,
            "description": self._definition.get('description', '')
        }
        return result

class Constraint_Group:
    """
    Combined multiple constraints together, ANDs them (all must be true.)
    """
    def __init__(self, constraints: list[Constraint], priority: int, description: str):
        self.id = id(self)  # Generate unique id if needed
        self.constraints = constraints
        self.priority = priority
        self.description = description
        self.last_eval = None

    @property
    def satisfied(self)->bool:
        results = [constraint.satisfied() for constraint in self.constraints]
        self.last_eval = {
            "description": self.description,
            "priority": self.priority,
            "constraints": [c.last_eval for c in self.constraints],
            "result": all(results)
        }
        return all(results)

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
    def __init__(self, from_state: State, to_state: State, constraint_groups: list[Constraint_Group]):
        self.from_state = from_state.name  # Store name instead of State object
        self.to_state = to_state.name
        self.constraint_groups = constraint_groups
        self.last_eval = None

    def add_constraint_group(self,CG:Constraint_Group):
        #This isn't a very robust check, but it's better than nothing. Should have __equal__ defined for Constraint_Group.
        assert CG.id not in self.constraint_groups
        self.constraint_groups.append(CG)

    @property
    def prioritized_cgs(self) -> Sequence[Constraint_Group]:
        return sorted(self.constraint_groups, key=lambda x: x.priority)
    
    @property
    def active(self)->bool:
        active = False
        eval_details = []
        
        for cg in self.prioritized_cgs:
            if cg.satisfied:
                active = True
                eval_details.append(cg.last_eval)
                break
            else:
                eval_details.append(cg.last_eval)
                
        self.last_eval = {
            "from_state": self.from_state,
            "to_state": self.to_state,
            "constraint_groups": eval_details,
            "result": active,
            "timestamp": time.time()
        }
        return active

def build_transition(from_state: State, to_state: State, transition_config: dict, registry: PointsRegistry) -> Transition:
    transition = Transition(from_state, to_state, [])
    for cg_config in transition_config['constraint_groups']:
        constraints = []
        for constraint_config in cg_config['constraints']:
            constraints.append(build_constraint(
                constraint_config['definition']['id'],
                constraint_config,
                registry
            ))
        constraint_group = Constraint_Group(
            constraints=constraints,
            priority=cg_config['priority'],
            description=cg_config['description']
        )
        transition.add_constraint_group(constraint_group)
    return transition

def build_constraint(constraint_id: int, constraint_config: dict, registry: PointsRegistry) -> Constraint:
    return Constraint(registry, constraint_config['definition'])

class Transitions_Manager:
    def __init__(self, transitions_config: dict, SM: States_Manager, registry: PointsRegistry):
        self.transitions_config = transitions_config
        self.SM = SM
        self.registry = registry
        self.build_from_config(transitions_config)

    def next_state(self, cur_state: State) -> State:
        relevant_transitions = self.transitions[cur_state.name]
        end_states = []
        transition_logs = []
        
        for end_state, transition in relevant_transitions.items():
            if transition.active:
                print(f"\nTransition activated: {cur_state.name} -> {end_state}")
                print(f"Evaluation details:")
                self._print_transition_eval(transition.last_eval)
                end_states.append(self.SM.get_state(end_state))
                transition_logs.append(transition.last_eval)
                
        if len(end_states) > 1:
            print(f"Multiple possible transitions from {cur_state.name} to: {[state.name for state in end_states]}")
            raise ValueError("Panic! Multiple transitions active. This should not happen.")
        elif len(end_states) == 0:
            return cur_state
        else:
            return end_states[0]
            
    def _print_transition_eval(self, eval_data: dict):
        print(f"  From {eval_data['from_state']} to {eval_data['to_state']}")
        for cg in eval_data['constraint_groups']:
            print(f"  Constraint Group: {cg['description']}")
            print(f"  Priority: {cg['priority']}")
            for c in cg['constraints']:
                print(f"    {c['description']}:")
                print(f"      {c['value']} {c['comparator']} {c['comparand']} = {c['result']}")

    def build_from_config(self, config: dict):
        existing_transitions = {}
        if hasattr(self, 'transitions'):
            existing_transitions = self.transitions

        if "Transitions" not in config:
            raise ValueError("Config must have 'Transitions' as the top-level key")
            
        config = config["Transitions"]
        self.transitions = {}
        
        for from_state, to_state_dict in config.items():
            if from_state not in self.transitions:
                self.transitions[from_state] = {}
            for to_state, transition_config in to_state_dict.items():
                transition = build_transition(
                    self.SM.get_state(from_state), 
                    self.SM.get_state(to_state), 
                    transition_config, 
                    self.registry
                )
                self.transitions[from_state][to_state] = transition
                
        if existing_transitions:
            for from_state, to_states in existing_transitions.items():
                if from_state not in self.transitions:
                    self.transitions[from_state] = {}
                self.transitions[from_state].update(to_states)

    

    


        


