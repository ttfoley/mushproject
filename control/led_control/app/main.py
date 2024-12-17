import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
from datetime import datetime
import time
from mqtt_handler import MQTTHandler
from controller import ControlPoint,State,Humidity_Control,Outputs,output_value,transition_rule
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
state_rules = {"Off":transition_rule("0","Off","HumidOn",20*60),"HumidOn":transition_rule("1","HumidOn","Humidify",45),
               "Humidify":transition_rule("2","Humidify","FanOff",2*60),"FanOff":transition_rule("3","FanOff","Off",15),
               "Unknown":transition_rule("4","Unknown","Off",0)}

def main():
    #TODO: verify the connection, add reconnect logic
    mqtt_handler.loop_start()
    print(humid_control.current_state.name,humid_control.desired_state.name,humid_control.time_in_state)
    humid_control.write_desired_state()
    time.sleep(5)
    #Give it some time to fetch values
    humid_control.update_state()
    print(humid_control.current_state.name,humid_control.desired_state.name,humid_control.time_in_state)
    last_update_time = datetime.now()
    update_frequency = 60
    while True:
        #print(humid_control.current_state.name,humid_control.desired_state.name,humid_control.time_in_state)
        humid_control.update_state()
        changed = humid_control.update_desired_state()
        if changed:
            print(f"Changed desired state to {humid_control.desired_state.name} at {datetime.now()}.  Current state is: {humid_control.current_state.name}") 
        if humid_control.current_state.name != humid_control.previous_state.name:
            print(f"Verified state change to {humid_control.current_state.name} at {datetime.now()} from state: {humid_control.previous_state.name}")
        ##Changing to only write the desired state if it's not there.
        ## I don't know if this is sufficient, who knows exactly how MQTT message que stuff works, but 
        ## as long it's not in desired state, it will keep trying.
        if not humid_control.in_desired_state():
            humid_control.write_desired_state()
            #Don't want to spam
            time.sleep(1)

        if (datetime.now()-last_update_time).total_seconds() > update_frequency:
            print(humid_control.current_state.name,humid_control.desired_state.name,humid_control.time_in_state)
            last_update_time = datetime.now()

    mqtt_handler.loop_stop()


if __name__ == "__main__":

    control_points = {point_name:ControlPoint(point_name,f"mush/controller2/control/{point_name}",f"mush/controller2/readback/{point_name}") 
                      for point_name in ["led1","pin25","pin26","pin32","pin33"]}

    outputs_instances = {}
    #"Off":[output_value("pin25","Off"),output_value("pin33","Off")]
    state_names = state_output_defs.keys()
    for state_name,outputs in state_output_defs.items():
        #print(state_name,outputs)

        outputs_instances[state_name] = Outputs({control_points[output.point_name]:output for output in outputs})

    states = {}
    for state_name in state_names:
        states[state_name] = State(state_name,outputs_instances[state_name],state_rules[state_name])

    mqtt_handler = MQTTHandler(mqtt_client_id, mqtt_broker, mqtt_port, mqtt_uname, mqtt_pwd,userdata=control_points)
    mqtt_handler.connect()
    humid_control = Humidity_Control(states,states["Off"],mqtt_handler)

    #I don't like how this is separate, but you can't add args to the callbacks...
    for topic in to_subscribe:
        mqtt_handler.client.subscribe(topic)

    main()