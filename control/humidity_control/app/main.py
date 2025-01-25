import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
from datetime import datetime
import time
import sys
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
lib_path = os.path.join(current_dir, '../../common')
config_path = os.path.join(current_dir, '../config')
sys.path.append(lib_path)
from mqtt_handler import MQTTHandler
from controller import FSM
from construction import Configuration, Constructor
from surveyor import Surveyor


def main(fsm:FSM, mqtt_handler:MQTTHandler,surveyor:Surveyor):
    #TODO: verify the connection, add reconnect logic
    mqtt_handler.loop_start()
    fsm.print_update()
    fsm.write_desired_state(immediately=True)
    time.sleep(5)
    #Give it some time to fetch values
    fsm.update_state()
    fsm.print_update()
    last_update_time = datetime.now()
    update_frequency = 10
    gap_between_set_readback =0
    desired_set = datetime.now()
    while True:
        #print(fsm.current_state.name,fsm.desired_state.name,fsm.time_in_state)
        fsm.update_state()
        changed = fsm.update_desired_state()
        if changed:
            print(f"Changed desired state to {fsm.desired_state.name} at {datetime.now()}.  Current state is: {fsm.current_state.state.name}") 
            desired_set = datetime.now()
        if fsm.current_state.state.name != fsm.previous_state.name:
            print(f"Verified state change to {fsm.current_state.state.name} at {datetime.now()} from state: {fsm.previous_state.name}")
            gap_between_set_readback = (datetime.now()-desired_set).total_seconds()
            print(f"Gap between set and readback: {gap_between_set_readback}")

        ##Changing to only write the desired state if it's not there.
        ## I don't know if this is sufficient, who knows exactly how MQTT message que stuff works, but 
        ## as long it's not in desired state, it will keep trying.
        if not fsm.in_desired_state():
            if changed:
                fsm.write_desired_state(immediately=True)
            else:
                fsm.write_desired_state()
            #Don't want to spam
            time.sleep(1)

        if (datetime.now()-last_update_time).total_seconds() > update_frequency:
            fsm.print_update()
            last_update_time = datetime.now()

    mqtt_handler.loop_stop()


if __name__ == "__main__":

    config = Configuration(config_path)
    constructor = Constructor(config)
    mqtt_handler = constructor.mqtt_handler
    mqtt_handler.connect()
    constructor.subscribe_mqtt(mqtt_handler)
    fsm = constructor.fsm

    #I don't like how this is separate, but you can't add args to the callbacks...


    main(fsm, mqtt_handler,constructor.surveyor)