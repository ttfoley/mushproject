import json
import os
from typing import Dict, Any,Tuple
#The fact that I'm importing so many separate things seems like a bad smell.
from controller_old import ControlPoint,State,FSM,Outputs,Transition,SingleTransition,StateTimeConstraint,StateOutputs
from mqtt_handler import MQTTHandler
from collections import defaultdict

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

    def __init__(self,abs_config_path:str) -> None:
        #Should just be the relative path to the config file, ./config
        #note "output" and "control" are synonyms for topics, for reasons
        self._config_location = abs_config_path
        self._topics_config = self.get_topics()
        self._control_point_names,self._control_points_config = self.get_control_points()
        self._state_names, self._states_config = self.get_states()
        self._transitions = self.get_transitions()


    def get_config_file_location(self,file_name:str)->str:
        return os.path.join(self._config_location, file_name)
    
    def get_topics(self)->Dict[str,Any]:
        #Should be a dictionary of topics, with the key being the type of topic from (control,readback,sensor)
        #and the value being a list of topics (blah/blah/topic_type/topic_name)
        config_path = self.get_config_file_location("topics.json")
        print(f"Loading topics from: {config_path}")  # Debugging
        topics_dict = load_json(config_path)

        for topic_type,topics in topics_dict.items():
            assert topic_type in ["control","readback","sensor"], "Invalid topic type in topics.json"
            assert isinstance(topics,list), "values should be a list"
            for topic in topics:
                assert topic.split("/")[-2] in ["control","readback","sensor"], "Invalid topic (../topic/var_name) in topics.json"
        return topics_dict
    
    def get_control_points(self)->Tuple[list[str],Dict[str,Any]]:
        ##Dictionary of point names, with "output" and "readback" keys.
        ##I guess readbacks shouldn't strictly be necessary, but I'm keeping them for now
        config_path = self.get_config_file_location("control_points.json")
        print(f"Loading control points from: {config_path}")  # Debugging
        control_points = load_json(config_path)
        point_names = []
        for point_name,point in control_points.items():
            point_names.append(point_name)
            assert isinstance(point,dict), "Control points should be a dictionary"
            assert "output" in point.keys() and "readback" in point.keys(), "Control points should have output and readback keys"
            assert point["output"] in self._topics_config["control"], "Invalid output topic in control_points.json"
            assert point["readback"] in self._topics_config["readback"], "Invalid readback topic in control_points.json"
        return point_names,control_points
    
    #TODO: There's too much repetition happening with these get_ methods. I should make a generic one.
    def get_states(self)->Tuple[list[str],Dict[str,list[Dict[str,str]]]]:
        ##Dictionary of states, with the key being the state name, and the value being a dictionary of control points and values
        ##{"state_name":[{"point_name":"value"}]}
        config_path = self.get_config_file_location("states.json")
        print(f"Loading topics from: {config_path}") 
        states_config = load_json(self.get_config_file_location("states.json"))
        valid_outputs = ["On","Off","Unknown"]
        assert isinstance(states_config,dict), "States should be a dictionary"
        state_names = []
        for state_name,output_values in states_config.items():
            state_names.append(state_name)
            assert isinstance(output_values,list), "Output values should be a list of [{point_name:value}}]"
            for point_value in output_values:
                print(point_value)
                #print(state_name,point_value)
                assert point_value["control_point"] in self._control_point_names, "Invalid control point in states.json"
                assert point_value["value"] in valid_outputs, "Values should be in ['On','Off','Unknown']"
        return state_names, states_config
    
    @property
    def needed_control_points(self):
        #The names of those control points needed by the states
        # This should really come from searching over all control points, which would include a consistency check.
        ref_state = self._states_config["Unknown"] ## I'm assuming Unknown is a state, and all states have the same need control points.
        return [point["control_point"] for point in ref_state]

    def get_transitions(self)->Dict[str,Dict[Tuple[str,str],Any]]:
        """
        #TODO Generalize this past state_time transitions.
        For state time transitions, the key is thestate name(where transition from), and the value being a dictionary of {"to_state":value1,"time":value2} and  and times
        output should be index by pairs {(from_state,to_state):time} and the value should be the time {}.
        In the future we need to figure out format for other types of transitions
        For every type of transition, there better only be one of each pair of (oriented) states 
        """
        config_path = self.get_config_file_location("transitions.json")
        print(f"Loading transitions from: {config_path}") 
        transitions_config = load_json(config_path)

        assert isinstance(transitions_config,dict), "Transitions should be a dictionary"
        transitions = defaultdict(dict)
        #for state_time transitions
        state_time_transitions = transitions_config["state_time_transitions"]
        for from_state,transition in state_time_transitions.items():
            assert "to_state" in transition.keys() and "time" in transition.keys(), "Invalid transition in state_time_transitions"
            assert transition["to_state"] in self._state_names, "Invalid to_state in state_time_transitions"
            typed_time = float(transition["time"])
            assert typed_time >=0, "Times should be positive"
            transitions["state_time_transitions"][(from_state,transition["to_state"])] = typed_time
    
        ##other transitions will be added here
        return transitions
    
    
    def change_statetime_transition(self,from_state:str,to_state:str,time:float):
        #This should be called carefully! It may trigger a transition when applied, or invalidate an existing transition underway. Bad side effects.
        #The caller should check the aren't in from_state when calling this
        #This will be called by the main loop, and will change the time of a transition
        #It will return a boolean indicating if the change was successful. I can't remember why I'm returning the bool but thought it might be useful
        time_transitions = self._transitions["state_time_transitions"]
        existing_pairs = time_transitions.keys()
        assert (from_state,to_state) in existing_pairs, "Invalid transition, doesn't already exist"
        assert isinstance(time,int) or isinstance(time,float), "Time should be a number"
        assert time > 0, "Times should be positive"
        self._transitions["state_time_transitions"][(from_state,to_state)] = float(time)
        return True
    
    @property
    def all_topics(self)->list[str]:
        #this isn't elegant, just want to test things
        ##TODO make idiomatic
        all_topics = []
        for topic_type in self._topics_config.keys():
            topics = self._topics_config[topic_type]
            if len(topics) > 0:
                all_topics.extend(topics)
        return all_topics
    
    @property
    def readback_topics(self)->list[str]:
        #this isn't elegant, just want to test things
        ##TODO make idiomatic
        return self._topics_config["readback"]

    

class Initializer(object):
    """
    A helper to construct FSM from the Configuration object.
    Any extra sanity checks not applied in the Configuration object should be done here.
    I'm trying to prepare for when I have other types of transitions.
    """

    def __init__(self,config:Configuration,initial_desired_state:str) -> None:
        self._config = config
        self._control_points = self.make_control_points()
        self._state_outputs = self.make_state_outputs()
        self._live_outputs = self.make_live_outputs()
        self._states = self.make_states()
        self._initial_desired_state = self._states[initial_desired_state]
        self._transitions = self.make_transitions()


    

    
    def make_state_outputs(self)->Dict[str,StateOutputs]:
        state_outputs = {}
        for state_name,outputs in self._config._states_config.items():
            outputs_values = {op["control_point"]:op["value"] for op in outputs}
            state_outputs[state_name] = StateOutputs(outputs_values,self.control_points)
        return state_outputs
    
    def make_control_points(self)->Dict[str,ControlPoint]:
        #based on what's required from state defintions, get needed control points
        control_points = {}
        needed_points = self._config.needed_control_points
        for point_name,point in self._config._control_points_config.items():
            if point_name in needed_points:
                control_points[point_name] = ControlPoint(point_name,point["output"],point["readback"])
        return control_points
    
    @property
    def control_points(self):
        return [self._control_points[point_name] for point_name in sorted(self._control_points.keys())]
    def make_live_outputs(self):
        return Outputs(self.control_points)

    def make_states(self)->Dict[str,State]:
        states = {}
        for state_name in self._config._state_names:
            states[state_name] = State(state_name,self._state_outputs[state_name])
        return states
    
    def make_transitions(self)->Dict[str,Dict[Tuple[State,State],Transition]]:
        
        #For now only state_time transitions
        transitions = {"state_time_transitions":{}}
        state_time_transitions = self._config._transitions["state_time_transitions"]
        for (from_state_name,to_state_name),time in state_time_transitions.items():
            from_state,to_state = self._states[from_state_name],self._states[to_state_name]
            assert (from_state,to_state) not in transitions["state_time_transitions"].keys(), "Duplicate state time transition!!"
            transitions["state_time_transitions"][(from_state,to_state)] = SingleTransition(from_state,to_state,[StateTimeConstraint(time)])
            
        return transitions
    
    def all_final_assertions_sat(self)->bool:
        #This is a placeholder for any final assertions that should be made before returning the FSM
        #They should be in better places but I want to test this.
        #TODO put these where they belong
        print("Checking final assertions")
        print(self._initial_desired_state,self._states.keys())
        assert self._initial_desired_state.name in list(self._states.keys()), "Initial state not in known states"
        assert "Unknown" in self._states.keys(), "Unknown state must be in known states"
        return True


    def make_fsm(self,mqtt_handler:MQTTHandler)->FSM:
        assert self.all_final_assertions_sat(), "Final assertions not satisfied"##this is silly, will never be reached
        return FSM(self.control_points,self._states,self._transitions,self._initial_desired_state,mqtt_handler)
    


  