from datetime import datetime
from points import  MonitoredPoint


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