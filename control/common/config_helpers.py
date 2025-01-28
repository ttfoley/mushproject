import json
from typing import Dict, Any,Tuple
from collections import defaultdict

def load_json(file_path:str):
    with open(file_path) as f:
        return json.load(f)



class Constraint:
    def __init__(self,name:str,value:str,threshold:str,comparator:str,units,description = ""):
        self.name = name
        self.value = value
        self.threshold = threshold
        self.comparator = comparator
        self.description = description
        self.units = units


    @property
    def constraint_dict(self):
        D = defaultdict(dict)
        D[self.name] = defaultdict(dict)
        D[self.name]["definition"] = {"value":self.value, "threshold":self.threshold,"comparator":self.comparator,"units":self.units,"description" : self.description}
        D[self.name]["description"] = self.description
        return D



class ConstraintGroup:
    #This should be the function most called.
    def __init__(self,name,constraints:list[Constraint],description =""):
        self.name = name
        self.constraints = constraints
        self.description = description

    @property
    def group_dict(self):
        D = defaultdict(dict)
        D[self.name]["constraints"] = defaultdict(dict)
        for con in self.constraints:
            D[self.name]["constraints"].update(con.constraint_dict)
        D[self.name]["description"] = self.description

        return D




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

    def add_constraint_group(self,from_state,to_state,constraint_group:ConstraintGroup):
        try:
            D = self.configuration["Transitions"][from_state][to_state]
        except:
            #I thought the point of default dicts was that I don't need to do ths
            self.add_state_pair(from_state,to_state)

        self.configuration["Transitions"][from_state][to_state]['constraint_groups'].update(constraint_group.group_dict)

    def save(self,file_name):
        #jsonified = json.dumps(self.configuration)
        with open(file_name,'w') as f:
            json.dump(self.configuration,f)
        

    


class Node:
    def __init__(self, value):
        self.value = value
        self.children = []
        self.parent = None

    def add_child(self, child):
        self.children.append(child)
        child.parent = self

class Tree(object):
    def __init__(self):
        self.nodes = []
    
    def add_node(self,node:Node):
        self.nodes.append(node)

    @property
    def root(self):
        #Sloppy
        for node in self.nodes:
            if node.parent == "None":
                return node
