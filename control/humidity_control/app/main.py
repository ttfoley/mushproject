import os
import sys
import time
from datetime import datetime
current_dir = os.path.dirname(os.path.abspath(__file__))
lib_path = os.path.join(current_dir, '../../common')
config_path = os.path.join(current_dir, '../config')
sys.path.append(lib_path)

from construction import Constructor, FSMBuilder
from controller import FSM
from mqtt_handler import MQTTHandler

def main(fsm:FSM, mqtt_handler:MQTTHandler):
    mqtt_handler.loop_start()
    fsm.print_update()
    fsm.write_desired_state(immediately=True)
    time.sleep(5)
    # Give it some time to fetch values
    fsm.update_state()
    fsm.print_update()
    last_update_time = datetime.now()
    update_frequency = 10
    gap_between_set_readback = 0
    desired_set = datetime.now()

    try:
        while True:
            fsm.update_state()
            changed = fsm.update_desired_state()
            if changed:
                print(f"Changed desired state to {fsm.desired_state.name} at {datetime.now()}. Current state is: {fsm.current_state.state.name}")
                desired_set = datetime.now()
            if fsm.current_state.state.name != fsm.previous_state.name:
                print(f"Verified state change to {fsm.current_state.state.name} at {datetime.now()} from state: {fsm.previous_state.name}")
                gap_between_set_readback = (datetime.now() - desired_set).total_seconds()
                print(f"Gap between set and readback: {gap_between_set_readback}")

            # Changing to only write the desired state if it's not there.
            if not fsm.in_desired_state:
                if changed:
                    fsm.write_desired_state(immediately=True)
                else:
                    fsm.write_desired_state()
                # Don't want to spam
                time.sleep(1)

            if (datetime.now()-last_update_time).total_seconds() > update_frequency:
                fsm.print_update()
                last_update_time = datetime.now()

    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        mqtt_handler.loop_stop()

if __name__ == "__main__":
    builder = FSMBuilder(config_path)
    fsm, pm, tm, mqtt = (builder
        .build_points_manager()
        .build_states_manager()
        .build_transitions_manager()
        .build_monitor_points()
        .build_fsm()
        .add_mqtt()
        .build())

    if not mqtt:
        raise RuntimeError("MQTT handler required but not created")

    # Run main loop
    main(fsm, mqtt)