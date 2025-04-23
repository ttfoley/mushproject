# common/governor/controllers/bangbang.py

class BangBangController:
    """
    Implements simple bang-bang (on/off) control logic
    with a deadband.
    """

    def __init__(self):
        pass # Configuration likely handled externally

    def calculate_command(self, sensor_value: float | None, setpoint: float, deadband: float) -> str | None:
        """
        Calculates the desired output state ("on" or "off") based on inputs.

        Args:
            sensor_value: The current sensor reading.
            setpoint: The target value.
            deadband: The tolerance band around the setpoint.

        Returns:
            "on" or "off" if a state change is required.
            None if the value is within the deadband (no change needed).

        Raises:
            ValueError: If sensor_value is None or other input is invalid.
        """
        if sensor_value is None:
            # Raise an exception for invalid/missing input
            raise ValueError("Cannot calculate command: Invalid sensor value (None).")
        
        # We could add checks for setpoint/deadband validity here too if needed
        if deadband < 0:
             raise ValueError(f"Cannot calculate command: Invalid deadband ({deadband}).")


        upper_bound = setpoint + deadband
        lower_bound = setpoint - deadband

        # Core bang-bang logic
        if sensor_value > upper_bound:
            # Value is too high, need to turn actuator OFF
            # (Assuming actuator ON increases sensor value)
            return "off"
        elif sensor_value < lower_bound:
            # Value is too low, need to turn actuator ON
            return "on"
        else:
            # Value is within the deadband, maintain current state.
            # Returning None signals no *change* is required.
            return None