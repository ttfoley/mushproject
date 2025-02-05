from datetime import datetime
from values import Discrete_Value, Continuous_Value
from points import Writeable_Discrete_Point, Writeable_Continuous_Point, FSM_StateTimePoint

def create_monitor_points(driver_name: str, state_names: list[str], points_manager) -> tuple[dict, Writeable_Discrete_Point, FSM_StateTimePoint]:
    """Create state and time points for FSM monitoring"""
    # Create state point
    state_topic = f"mush/drivers/{driver_name}/sensors/status/state"
    state_uuid = points_manager.next_uuid()
    state_value = Discrete_Value(state_uuid, state_topic, "unknown", "driver state", 
                           state_names + ["unknown"])
    settings = points_manager.get_point_settings('state')
    state_point = Writeable_Discrete_Point(state_value, **settings)
    points_manager.update_uuid_lookup(state_uuid, state_point)
    
    # Create time point
    time_topic = f"mush/drivers/{driver_name}/sensors/status/state_time"
    time_uuid = points_manager.next_uuid()
    time_value = Continuous_Value(time_uuid, time_topic, 0, "state time",
                               {"lower": 0, "upper": 1000000})
    settings = points_manager.get_point_settings('state_time')
    time_point = FSM_StateTimePoint(
        value_class=time_value, 
        time_provider=None,  # Will be set later in FSMMonitor.__init__
        **settings
    )
    points_manager.update_uuid_lookup(time_uuid, time_point)
    
    # Structure points dict
    points = {
        "drivers": {
            driver_name: {
                "sensors": {
                    "status": {
                        "state": state_point,
                        "time_in_state": time_point
                    }
                }
            }
        }
    }
    
    return points, state_point, time_point

class FSMMonitor:
    """Monitors FSM state and manages state/time points"""
    def __init__(self, fsm, points_manager, state_point=None, time_point=None):
        self.fsm = fsm
        self.pm = points_manager
        self._time_started = datetime.now()
        
        # Use existing points or create new ones
        if state_point and time_point:
            self._state_point = state_point
            self._time_point = time_point
        else:
            points, self._state_point, self._time_point = create_monitor_points(
                driver_name=fsm._driver_name,
                state_names=fsm._SM.state_names,
                points_manager=points_manager
            )
            self.pm.points.update(points)
        
        # Set time provider for time point
        self._time_point._time_provider = fsm

    def on_state_change(self):
        """Called when FSM state changes"""
        self._time_started = datetime.now()
        self._state_point.requested_value = self.fsm.current_state.state.name
        self._time_point.requested_value = 0
        self.pm.publish_point(self._state_point)
        self.pm.publish_point(self._time_point)

    def update(self):
        """Update time in state"""
        time_in_state = (datetime.now() - self._time_started).total_seconds()
        self._time_point.requested_value = time_in_state 