import json
from typing import Dict, Any, Tuple, List, Optional, Type
from collections import defaultdict
from configuration import BaseConfiguration
import os

def load_json(file_path:str):
    with open(file_path) as f:
        return json.load(f)



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

class TransitionsConfigHelper(BaseConfiguration):
    """Helper class for building transitions configuration"""
    def __init__(self, config_path: str):
        super().__init__(config_path)  # This loads all configs including governor points
        self.driver_name = self._driver_name
        
    @property 
    def writable_states(self) -> list[str]:
        """Get list of writable states from states config"""
        return list(self._states_config.keys())

    def get_point_uuid(self, addr: str) -> int:
        return super().get_point_uuid(addr)

    def get_driver_points(self) -> dict:
        """Get driver state, time and command point UUIDs"""
        base_topic = f"mush/drivers/{self.driver_name}"
        state_addr = f"{base_topic}/status/state"
        time_addr = f"{base_topic}/status/state_time"
        command_addr = f"{base_topic}/command/state"
        return {
            'state': self.get_point_uuid(state_addr),
            'time': self.get_point_uuid(time_addr),
            'command': self.get_point_uuid(command_addr)
        }

    def get_sensor_point(self, controller: str, sensor_name: str, sensor_type: str) -> int:
        """Get UUID for sensor point"""
        addr = f"mush/drivers/{controller}/sensors/status/{sensor_name}"
        return self.get_point_uuid(addr)

    def get_control_point(self, controller: str, cp_name: str, rb_w: str = "readback") -> int:
        """Get UUID for control point readback or write"""
        addr = f"mush/controllers/{controller}/control_points/{cp_name}/{rb_w}"
        return self.get_point_uuid(addr)

    def get_command_point(self, commander_name: str, command_name: str) -> int:
        """Get UUID for command point"""
        return self.get_driver_points()['command']

    def get_point_description(self, uuid: int) -> str:
        """Get description for point with given UUID"""
        result = self._search_description(self._points_config, uuid)
        if result is not None:
            return result
        raise ValueError(f"No point found with UUID {uuid}")

    def _search_description(self, config: dict, uuid: int) -> Optional[str]:
        def search_dict(d: dict) -> Optional[str]:
            if isinstance(d, dict):
                if d.get("UUID") == uuid:
                    return d.get("description", "No description")
                if "readback" in d and d["readback"].get("UUID") == uuid:
                    return d.get("description", "No description")
                if "write" in d and d["write"].get("UUID") == uuid:
                    return d.get("description", "No description")
                for v in d.values():
                    result = search_dict(v)
                    if result is not None:
                        return result
            return None
        return search_dict(config)

class TransitionsBuilder:
    """Helper class for building state transitions"""
    def __init__(self, helper: TransitionsConfigHelper):
        self.helper = helper
        self.driver_name = helper.driver_name
        self.driver_states = helper.writable_states + ["unknown"]
        self.driver_points = helper.get_driver_points()
        self.constraint_groups = defaultdict(lambda: defaultdict(list))  # from -> to -> [groups]
        self.transitions_maker = Transitions_Maker()

    def add_state_time_constraint(self, cg: ConstraintGroup, time_seconds: float, comparator: str = ">=") -> None:
        """Add state time constraint to existing constraint group"""
        value = self.driver_points['time']
        desc = self.helper.get_point_description(value)
        cg.add_constraint(StateTimeConstraint(cg.num_constraints, value, time_seconds, comparator, description=desc))

    def add_command_constraint(self, cg: ConstraintGroup, command_value: str) -> None:
        """Add command constraint to existing constraint group"""
        # Validate command value is a valid state
        assert command_value in self.driver_states, \
            f"Command value '{command_value}' must be one of {self.driver_states}"
        
        cmd_uuid = self.helper.get_command_point(self.driver_name, "state")
        cg.add_constraint(DiscreteValueConstraint(
            cg.num_constraints, cmd_uuid, command_value, "==",
            description=f"Command to enter {command_value} state"
        ))

    def new_constraint_group(self, from_state: str, to_state: str, description: str = "", priority: int = 0) -> ConstraintGroup:
        """Create new constraint group and track it"""
        assert (from_state in self.driver_states) and (to_state in self.driver_states), \
            f"Invalid states: {from_state} -> {to_state}"
            
        # ID is just the length of existing groups for this transition
        cg_id = len(self.constraint_groups[from_state][to_state])
        
        cg = ConstraintGroup(from_state, to_state, cg_id, description=description, priority=priority)
        self.constraint_groups[from_state][to_state].append(cg)
        return cg

    def add_state_time_constraint_group(self, from_state: str, to_state: str, 
                                      time_seconds: float, description: str = "",
                                      priority: int = 0, comparator: str = ">=") -> None:
        """Add a constraint group with a state time constraint"""
        cg = self.new_constraint_group(from_state, to_state, description, priority)
        self.add_state_time_constraint(cg, time_seconds, comparator)

    def add_command_constraint_group(self, from_state: str, to_state: str,
                                   command: str, description: str = "", 
                                   priority: int = 0) -> None:
        """Add a constraint group with a command value constraint"""
        cg = self.new_constraint_group(from_state, to_state, description, priority)
        self.add_command_constraint(cg, command)

    def build(self) -> dict:
        """Build and return complete transitions configuration"""
        for from_state in self.constraint_groups:
            for to_state in self.constraint_groups[from_state]:
                for cg in self.constraint_groups[from_state][to_state]:
                    self.transitions_maker.add_constraint_group(from_state, to_state, cg)
        return self.transitions_maker.configuration

    def save(self, config_path: str) -> None:
        """Save transitions configuration to file"""
        self.transitions_maker.save(os.path.join(config_path, "transitions.json"))

    def add_command_constraints(self):
        """Add governor command constraints"""
        # Add command points
        self.command_points = {}
        for state in self.driver_states:
            if state != "unknown":
                cmd_uuid = self.helper.get_command_point(self.driver_name, f"set_{state}")
                self.command_points[state] = cmd_uuid

class LayeredTransitionsBuilder(TransitionsBuilder):
    """Builds transitions with multiple layers of constraints"""
    
    def add_safety_constraints(self, min_state_time: float = 60):
        """Add basic safety constraints"""
        # Unknown to off transition
        cg = self.new_constraint_group("unknown", "off", 
            "Turn the driver off immediately if state is unknown")
        self.add_state_time_constraint(cg, 0)

        # Add minimum state time constraints between other states
        for from_state in self.driver_states:
            if from_state == "unknown":
                continue
            for to_state in self.driver_states:
                if to_state == "unknown" or from_state == to_state:
                    continue
                cg = self.new_constraint_group(from_state, to_state,
                    f"Safety constraints for {from_state} to {to_state}")
                self.add_state_time_constraint(cg, min_state_time)

    def add_command_constraints(self):
        """Add governor command constraints"""
        # Add command points
        self.command_points = {}
        for state in self.driver_states:
            if state != "unknown":
                cmd_uuid = self.helper.get_command_point(self.driver_name, f"set_{state}")
                self.command_points[state] = cmd_uuid

        # Add command constraints to existing transitions
        for from_state in self.driver_states:
            if from_state == "unknown":
                continue
            for to_state in self.driver_states:
                if to_state == "unknown" or from_state == to_state:
                    continue
                cg = self.new_constraint_group(from_state, to_state,
                    f"Command constraints for {from_state} to {to_state}")
                cmd_uuid = self.command_points[to_state]
                self.add_command_constraint(cg, f"set_{to_state}")