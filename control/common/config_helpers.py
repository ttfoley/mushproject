import json
from typing import Dict, Any, Tuple, List, Optional, Type
from collections import defaultdict
from construction import PreTransitionsConstructor

def load_json(file_path:str):
    with open(file_path) as f:
        return json.load(f)


class PTC_Helper:
    def __init__(self,ptc:PreTransitionsConstructor):
        self.PTC = ptc
        self.PM = ptc.PM
        self.SM = ptc.SM

    @property
    def driver_name(self):
        return self.PTC._driver_name
    
    @property
    def writable_states(self)->List[str]:
        return self.SM.state_names

    def get_sensor_point(self,controller,sensor_name,sensor_type):
        sensor_topic = f"mush/controllers/{controller}/sensors/{sensor_name}/{sensor_type}"
        return self.PM._uuid_lookup[sensor_topic]

    def get_control_point(self,controller,cp_name,rb_w = "rb"):
        #should only be looking at readbacks.
        control_topic = f"mush/controllers/{controller}/control_points/{cp_name}/{rb_w}"
        return self.PM._uuid_lookup[control_topic]

    def get_command_point(self,commander_name,command_name):
        #No commanders implemented yet
        command_topic = f"mush/commanders/{commander_name}/commands/{command_name}"
        return self.PM._uuid_lookup[command_topic]

class Constraint:
    """
    Units of the constraint (comparand) are assumed to be the same as the units of the value.
    """
    def __init__(self, id: int, value_uuid: int, comparand, comparator: str, units:str, description: str = ""):
        self.id = id
        self.value_uuid = value_uuid
        self.comparand = comparand
        self.comparator = comparator
        self._description = description
        self.units = units
        self._type = ""  # Add default type

    @property
    def constraint_dict(self):
        D = {
            "definition": {
                "id": self.id,
                "value_uuid": self.value_uuid,
                "comparand": self.comparand,
                "comparator": self.comparator,
                "units": self.units
            },
            "description": self._description,
            "type": self._type
        }
        return D

class StateTimeConstraint(Constraint):
    def __init__(self, id: int, value_uuid: int, comparand: float, comparator: str, units = "float", description: str = ""):
        super().__init__(id, value_uuid, comparand, comparator, units, description)
        self._type = "state_time"
        self._description = f"{self._type} constraint for {self._description}"


class ContinuousValueConstraint(Constraint):
    def __init__(self, id: int, value_uuid: int, comparand: float, comparator: str, units = "float", description: str = ""):
        super().__init__(id, value_uuid, comparand, comparator, units, description)
        self._type = "continuous_value"
        self._description = f"{self._type} constraint for {self._description}"


class DiscreteValueConstraint(Constraint):
    def __init__(self, id: int, value_uuid: int, comparand: str, comparator: str, units = "str", description: str = ""):
        super().__init__(id, value_uuid, comparand, comparator, units, description)
        self._type = "discrete_value"
        self._description = f"{self._type} constraint for {self._description}"


class ConstraintGroup:
    # This should be the function most called.
    def __init__(self, from_state: str, to_state: str, id: int, constraints: Optional[List[Constraint]] = None, description: str = "",priority:int = 0):
        self._from_state = from_state
        self._to_state = to_state
        self._id = id
        self._priority = priority
        self._constraints = constraints if constraints is not None else []
        self.description = description


    @property 
    def num_constraints(self):
        return len(self._constraints)
    @property
    def constraints(self):
        return self._constraints

    def add_constraint(self, constraint: Constraint):
        self.constraints.append(constraint)

    @property
    def group_dict(self):
        return {
            "id": self._id,
            "constraints": [constraint.constraint_dict for constraint in self._constraints],
            "description": self.description,
            "priority": self._priority
        }


class Transitions_Maker:
    def __init__(self):
        self.configuration = self.initialize_configurations()
    
    def initialize_configurations(self):
        config = defaultdict(dict)
        config["Transitions"] = defaultdict(dict)
        return config

    def add_states(self,state_names:list[str]):
        for state in state_names:
            self.configuration["Transitions"][state] = defaultdict(dict)
    
    def add_state_pair(self,state1:str,state2:str):
        self.configuration["Transitions"][state1][state2] = defaultdict(dict)

    def add_constraint_group(self, from_state, to_state, constraint_group: ConstraintGroup):
        try:
            D = self.configuration["Transitions"][from_state][to_state]
        except:
            self.add_state_pair(from_state, to_state)
            D = self.configuration["Transitions"][from_state][to_state]
        
        if 'constraint_groups' not in D:
            D['constraint_groups'] = []
        D['constraint_groups'].append(constraint_group.group_dict)

    def save(self,file_name):
        #jsonified = json.dumps(self.configuration)
        with open(file_name,'w') as f:
            json.dump(self.configuration,f,indent = 4)
        

    



def make_state_time_constraint(id:int,value_uuid:int,comparand:float,comparator:str,description:str = ""):
    return StateTimeConstraint(id,value_uuid,comparand,comparator)

def make_discete_value_equal_constraint(id:int,value_uuid:int,comparand:str,description:str = "",valid_values:List[str] = []):
    #Assuming all discrete values mapped to strings.
    if valid_values == []:
        print("Warning!: No valid values provided for discrete value constraint.")
    else:
        assert comparand in valid_values
    return DiscreteValueConstraint(id,value_uuid,comparand,"==")

def make_continuous_value_constraint(id:int,value_uuid:int,comparand:float,comparator:str,description:str = ""):
    return ContinuousValueConstraint(id,value_uuid,comparand,comparator)