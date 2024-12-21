import json
import os
from typing import Dict, Any,Tuple

def load_json(file_path:str):
    with open(file_path) as f:
        return json.load(f)

class Configuration(object):
    """"
    Will be run from the main.py, will read the configuration files and set up the control loop.
    Will have files for States, Outputs, Transitions, and points
    Design around being able to change transition parameters (state_time, cutoffs..), nothing else should be modified
    after the control loop start. When transitions params are changed, there should be some sanity check and a return code
    if it's rejected.  
    """

    def __init__(self,relative_config_path:str) -> None:
        #Should just be the relative path to the config file, ./config
        #note "output" and "control" are synonyms for topics, for reasons
        self._config_location = relative_config_path
        self._topics_config = self.get_topics()
        self._control_points_config,self._control_point_names = self.get_control_points()
        self._state_names, self._states_config = self.get_states()
        self._transition_pairs,self._transitions = self.get_transitions()



    def get_topics(self)->Dict[str,Any]:
        #Should be a dictionary of topics, with the key being the type of topic from (control,readback,sensor)
        #and the value being a list of topics (blah/blah/topic_type/topic_name)
        topics_dict = load_json(self._config_location + "/topics.json")

        for topic_type,topics in topics_dict.items():
            assert topic_type in ["control","readback","sensor"], "Invalid topic type in topics.json"
            assert isinstance(topics,list), "values should be a list"
            for topic in topics:
                assert topic.split("/")[-2] in ["control","readback","sensor"], "Invalid topic (../topic/var_name) in topics.json"
        return topics_dict
    
    def get_control_points(self)->Tuple[list[str],Dict[str,Any]]:
        ##Dictionary of point names, with "output" and "readback" keys.
        ##I guess readbacks shouldn't strictly be necessary, but I'm keeping them for now
        control_points = load_json(self._config_location + "/control_points.json")
        point_names = []
        for point_name,point in control_points.items():
            point_names.append(point_name)
            assert isinstance(point,dict), "Control points should be a dictionary"
            assert "output" in point.keys() and "readback" in point.keys(), "Control points should have output and readback keys"
            assert point["output"] in self._topics_config["control"], "Invalid output topic in control_points.json"
            assert point["readback"] in self._topics_config["readback"], "Invalid readback topic in control_points.json"
        return point_names,control_points
    
    def get_states(self)->Tuple[list[str],Dict[str,Any]]:
        ##Dictionary of states, with the key being the state name, and the value being a dictionary of control points and values
        ##{"state_name":[{"point_name":"value"}]}
        states = load_json(self._config_location + "/states.json")
        valid_outputs = ["On","Off"]
        assert isinstance(states,dict), "States should be a dictionary"
        state_names = []
        for state_name,output_values in states.items():
            state_names.append(state_name)
            assert isinstance(output_values,list), "Output values should be a list of [{point_name:value}}]"
            for point_value in output_values:
                assert point_value["control_point"] in self._control_point_names, "Invalid control point in states.json"
                assert point_value["value"] in valid_outputs, "Values should be strings"
        return state_names, states
    
    def get_transitions(self)->Tuple[list[Tuple[str,str]],Dict[str,Any]]:
        """
        Dictionary of states.
        For state time transtions, the key is thestate name(where transition from), and the value being a dictionary of {"to_state":value1,"time":value2} and  and times
        output should be index by pairs {(from_state,to_state):time} and the value should be the time {}.
        In the future we need to figure out format for other types of transitions
        """
        transitions = load_json(self._config_location + "/transitions.json")
        assert isinstance(transitions,dict), "Transitions should be a dictionary"
        
        #
        state_time_transition = {}
        pairs = []
        for from_state,transition in transitions.items():
            assert from_state in self._state_names, "Invalid state in transitions.json"
            for to_state,time in transition.items():
                pairs.append((from_state,to_state))
                assert to_state in self._state_names, "Invalid state in transitions.json"
                typed_time = float(time)
                assert typed_time > 0, "Times should be positive"
                state_time_transition[(from_state,to_state)] = typed_time
        return "state_time_transitions":state_time_transition_pairs
    
    def change_statetime_transition(self,from_state,to_state,time):
        #This will be called by the main loop, and will change the time of a transition
        #It will return a boolean indicating if the change was successful
        assert (from_state,to_state) in self._transition_pairs, "Invalid transition, doesn't already exist"
        assert time > 0, "Times should be positive"
        self._transitions["state_time_transitions"][(from_state,to_state)] = time
        return True


        

