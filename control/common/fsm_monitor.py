from datetime import datetime
from points import MonitoredPoint, Writable_Point, FSM_StateTimePoint
from points_core import PointsRegistry


class FSMMonitor:
    """Monitors FSM state and manages state/time points.
    Requires that the points already exist in the registry."""
    def __init__(self, fsm, registry: PointsRegistry):
        self.fsm = fsm
        self.registry = registry
        self._time_started = datetime.now()
        
        # Get points from registry and validate types
        time_point = self.registry.state_time_point
        state_point = self.registry.state_point
        
        if not isinstance(time_point, FSM_StateTimePoint):
            raise TypeError("state_time_point must be FSM_StateTimePoint")
        if not isinstance(state_point, Writable_Point):
            raise TypeError("state_point must be Writable_Point")
            
        time_point.set_time_provider(self)
        
        # Create monitored points
        """
        I know it might seem a little funny having these points exist only here with the registry never knowing
        about them, but it makes since because 1) the registry knows about the points they're built on and 2)
        this keeps them isolated so only their owner will ever be able to change them.
        """
        self._state_point = MonitoredPoint(state_point, self.fsm.messenger)
        self._time_point = MonitoredPoint(time_point, self.fsm.messenger)

    def reset_time(self):
        """Reset the time started to now."""
        self._time_started = datetime.now()

    def on_state_change(self):
        """Called when FSM state changes"""
        self.reset_time()
        print(f"FSM Monitor - New state: {self.fsm.current_state.name}")  # Debug
        self._state_point.requested_value = self.fsm.current_state.name
        self._time_point.requested_value = 0
        self._state_point.publish_point(force=True)
        self._time_point.publish_point(force=True)

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