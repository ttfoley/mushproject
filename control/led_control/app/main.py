import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
from datetime import datetime
import time
from mqtt_handler import MQTTHandler
from controller import ControlPoint,State,FSM,Outputs,StateStatus,SingleTransition,StateTimeConstraint,StateStatus,output_value,transition_rule
mqtt_uname = "ttfoley"
mqtt_pwd = "password"
mqtt_broker = "192.168.1.17"
mqtt_port = 1883
mqtt_client_id = "control_test"


to_subscribe = ["mush/controller2/control/led1","mush/controller2/control/pin25","mush/controller2/control/pin26","mush/controller2/control/pin32",
                "mush/controller2/control/pin33","mush/controller2/readback/led1","mush/controller2/readback/pin25",
                "mush/controller2/readback/pin26","mush/controller2/readback/pin32","mush/controller2/readback/pin33"]

state_output_defs = {"Off":[output_value("pin25","Off"),output_value("pin33","Off")],"HumidOn":[output_value("pin25","On"),output_value("pin33","Off")],
                     "Humidify":[output_value("pin25","On"),output_value("pin33","On")],"FanOff":[output_value("pin25","On"),output_value("pin33","Off")],
                     "Unknown":[output_value("pin25","Unknown"),output_value("pin33","Unknown")]}

#for now only one rule per state
transition_rules = {"Off":transition_rule("0","Off","HumidOn",25*60),"HumidOn":transition_rule("1","HumidOn","Humidify",45),
               "Humidify":transition_rule("2","Humidify","FanOff",10*60),"FanOff":transition_rule("3","FanOff","Off",15),
               "Unknown":transition_rule("4","Unknown","Off",0)}

###We're going to move this block to files.
control_points_lookup = {"led1":{"output":"mush/controller2/control/led1","readback":"mush/controller2/readback/led1"},
                       "pin25":{"output":"mush/controller2/control/pin25","readback":"mush/controller2/readback/pin25"}, 
                       "pin26":{"output":"mush/controller2/control/pin26","readback":"mush/controller2/readback/pin26"},
                       "pin32":{"output":"mush/controller2/control/pin32","readback":"mush/controller2/readback/pin32"},
                       "pin33":{"output":"mush/controller2/control/pin33","readback":"mush/controller2/readback/pin33"}}

##{Name:{output:value}}
state_defs_lookup = {"Off":{"pin25":"Off","pin33":"Off"},"HumidOn":{"pin25":"On","pin33":"Off"},
                     "Humidify":{"pin25":"On","pin33":"On"},"FanOff":{"pin25":"On","pin33":"Off"},
                     "Unknown":{"pin25":"Unknown","pin33":"Unknown"}}

#{FromState:{ToState:time}}## For now only one rule per state, with only ">" operators
timer_transition_rules_lookup = {"Off":{"HumidOn":.5*60},"HumidOn":{"Humidify":45},"Humidify":{"FanOff":.5*60},"FanOff":{"Off":15},"Unknown":{"Off":0}}

initial_desired_state = "Off"
###End of block to move to files


def make_control_points(cp_lookup:dict[str,dict[str,str]])->dict[str,ControlPoint]:
    control_points = {point_name:ControlPoint(point_name,cp_lookup[point_name]["output"],cp_lookup[point_name]["readback"] ) for point_name in cp_lookup.keys()}
    return control_points

def make_states(state_defs_lookup:dict[str,dict[str,str]],control_points:dict[str,ControlPoint],transition_rules:dict[str,transition_rule]):
    outputs_instances = {}
    state_names = state_defs_lookup.keys()
    for state_name,outputs in state_defs_lookup.items():
        outputs_instances[state_name] = Outputs({control_points[output_point]:output_value(output_point,value) for output_point,value in outputs.items()})

    states = {}
    for state_name in state_names:
        states[state_name] = State(state_name,outputs_instances[state_name],transition_rules[state_name])
    return states

def make_timed_transitions(rules:dict[str,dict[str,int]],states:dict[str,State])-> dict[State,dict[State,SingleTransition]]:
    transitions = {}
    for from_state_name in rules.keys():
        from_state = states[from_state_name]
        transitions[from_state] = {}
        for to_state_name,time in rules[from_state_name].items():
            to_state = states[to_state_name]
            constraints = [StateTimeConstraint(time)]
            transitions[from_state][to_state] = SingleTransition(from_state,to_state,constraints)
    return transitions



def main():
    #TODO: verify the connection, add reconnect logic
    mqtt_handler.loop_start()
    humid_control.print_update()
    humid_control.write_desired_state(immediately=True)
    time.sleep(5)
    #Give it some time to fetch values
    humid_control.update_state()
    humid_control.print_update()
    last_update_time = datetime.now()
    update_frequency = 10
    gap_between_set_readback =0
    desired_set = datetime.now()
    while True:
        #print(humid_control.current_state.name,humid_control.desired_state.name,humid_control.time_in_state)
        humid_control.update_state()
        changed = humid_control.update_desired_state()
        if changed:
            print(f"Changed desired state to {humid_control.desired_state.name} at {datetime.now()}.  Current state is: {humid_control.current_state.state.name}") 
            desired_set = datetime.now()
        if humid_control.current_state.state.name != humid_control.previous_state.name:
            print(f"Verified state change to {humid_control.current_state.state.name} at {datetime.now()} from state: {humid_control.previous_state.name}")
            gap_between_set_readback = (datetime.now()-desired_set).total_seconds()
            print(f"Gap between set and readback: {gap_between_set_readback}")

        ##Changing to only write the desired state if it's not there.
        ## I don't know if this is sufficient, who knows exactly how MQTT message que stuff works, but 
        ## as long it's not in desired state, it will keep trying.
        if not humid_control.in_desired_state():
            if changed:
                humid_control.write_desired_state(immediately=True)
            else:
                humid_control.write_desired_state()
            #Don't want to spam
            time.sleep(1)

        if (datetime.now()-last_update_time).total_seconds() > update_frequency:
            humid_control.print_update()
            last_update_time = datetime.now()

    mqtt_handler.loop_stop()


if __name__ == "__main__":

    control_points = make_control_points(control_points_lookup)

    outputs_instances = {}
    #"Off":[output_value("pin25","Off"),output_value("pin33","Off")]
    state_names = state_output_defs.keys()
    for state_name,outputs in state_output_defs.items():
        #print(state_name,outputs)

        outputs_instances[state_name] = Outputs({control_points[output.point_name]:output for output in outputs})

    states = {}
    for state_name in state_names:
        states[state_name] = State(state_name,outputs_instances[state_name],transition_rules[state_name])
    transitions = make_timed_transitions(timer_transition_rules_lookup,states)
    mqtt_handler = MQTTHandler(mqtt_client_id, mqtt_broker, mqtt_port, mqtt_uname, mqtt_pwd,userdata=control_points)
    mqtt_handler.connect()
    humid_control = FSM(states,transitions,states[initial_desired_state],mqtt_handler)

    #I don't like how this is separate, but you can't add args to the callbacks...
    for topic in to_subscribe:
        mqtt_handler.client.subscribe(topic)

    main()