from datetime import datetime
from values import Discrete_Value, Continuous_Value
from points import Writeable_Discrete_Point, Writeable_Continuous_Point, FSM_StateTimePoint, MonitoredPoint

def create_monitor_points(driver_name: str, state_names: list[str], points_manager) -> tuple[dict, Writeable_Discrete_Point, Writeable_Continuous_Point]:
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
    """Monitors FSM state and manages state/time points.
    Requires that the points already exist in the points manager."""
    def __init__(self, fsm, points_manager):
        self.fsm = fsm
        self.pm = points_manager
        self._time_started = datetime.now()
        
        # Get points directly from points manager
        time_point = self.pm.state_time_point
        time_point._time_provider = self
        
        # Create monitored points
        """
        I know it might seem a little funny having these points exist only here with the PM never knowing
        about them, but it makes since because 1) the PM knows about the points they're built on and 2)
        this keeps them isolated so only their owner will ever be able to change them.
        """
        self._state_point = MonitoredPoint(self.pm.state_point, points_manager)
        self._time_point = MonitoredPoint(time_point, points_manager)

    def reset_time(self):
        """Reset the time started to now."""
        self._time_started = datetime.now()

    def on_state_change(self):
        """Called when FSM state changes"""
        self.reset_time()
        self._state_point.requested_value = self.fsm.current_state.name
        self._time_point.requested_value = 0
        self._state_point.publish(force=True)
        self._time_point.publish(force=True)

    def update(self):
        """Update time in state and handle periodic publishing"""
        time_in_state = (datetime.now() - self._time_started).total_seconds()
        self._time_point.requested_value = time_in_state

        # Check republish for both points
        self._time_point.check_republish()
        self._state_point.check_republish()

    def get_time_in_state(self) -> float:
        """Implement TimeProvider protocol"""
        return (datetime.now() - self._time_started).total_seconds() 