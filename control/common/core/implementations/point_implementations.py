# control/common/core/implementations/point_implementations.py

from datetime import datetime
from typing import Any, Tuple, Optional

# Assuming BasePoint and BaseValue are correctly importable
# Adjust import paths if necessary
try:
    from ..core_points import BasePoint, CoreWritablePoint
    from ..core_values import BaseValue
except ImportError:
    # Fallback import - adjust as needed for your environment
    import sys
    import os
    # Add common/ to path - assumes this file is in common/core/implementations
    sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
    from core.core_points import BasePoint, CoreWritablePoint
    from core.core_values import BaseValue


class CoreConcretePointError(ValueError):
    """Custom exception for concrete point implementation errors."""
    pass


class CoreConcreteReadOnlyPoint(BasePoint):
    """
    Concrete implementation of BasePoint for read-only points.
    Wraps a BaseValue instance and delegates property access and updates to it.
    """

    def __init__(self, value_instance: BaseValue):
        """
        Initializes the read-only point.

        Args:
            value_instance: An instance of a class implementing the BaseValue interface
                           (e.g., CoreConcreteDiscreteValue, CoreConcreteContinuousValue).
        """
        assert isinstance(value_instance, BaseValue), "value_instance must be an instance of a BaseValue implementation."
        self._value_instance = value_instance

    # --- Property Implementations (Delegated to BaseValue instance) ---

    @property
    def uuid(self) -> int:
        """Get the UUID (delegated from BaseValue)."""
        return self._value_instance.uuid

    @property
    def addr(self) -> str:
        """Get the address/topic (delegated from BaseValue)."""
        return self._value_instance.addr

    @property
    def value(self) -> Any | None:
        """Get the last valid value (delegated from BaseValue)."""
        return self._value_instance.value

    @property
    def raw_value(self) -> Any | None:
        """Get the last received raw value (delegated from BaseValue)."""
        return self._value_instance.raw_value

    @property
    def is_valid(self) -> bool:
        """Check if the current value is valid (delegated from BaseValue)."""
        return self._value_instance.is_valid

    @property
    def last_update_time(self) -> datetime | None:
        """Get timestamp of last successful value update (delegated)."""
        return self._value_instance.last_update_time

    @property
    def last_raw_update_time(self) -> datetime | None:
        """Get timestamp of last raw value received (delegated)."""
        return self._value_instance.last_raw_update_time

    # --- Method Implementations ---

    def get_value_instance(self) -> BaseValue:
        """Return the contained BaseValue instance."""
        return self._value_instance

    def handle_incoming_update(self, raw_input: Any) -> Tuple[bool, Optional[Any]]:
        """
        Processes an incoming raw value by calling the managed
        BaseValue's try_update method.
        Returns the result from try_update.
        """
        # Delegate directly to the value instance's update logic
        return self._value_instance.try_update(raw_input)
    

class CoreConcreteWritablePoint(CoreConcreteReadOnlyPoint, CoreWritablePoint):
    """
    Concrete implementation for writable points.
    Extends ReadOnlyPoint and adds requested_value state and
    configuration for publishing behaviour (retry, republish).
    """

    def __init__(self,
                 value_instance: BaseValue,
                 republish_frequency: Optional[float] = None, # In seconds
                 retry_interval: Optional[float] = None):     # In seconds
        """
        Initializes the writable point.

        Args:
            value_instance: An instance of BaseValue (e.g., CoreConcreteDiscreteValue).
            republish_frequency: How often to republish the requested value (seconds). None means never.
            retry_interval: How often to retry publishing if confirmation isn't received (seconds). None means no retry.
        """
        # Initialize the base read-only point part
        super().__init__(value_instance)

        # Assertions for publish settings
        assert republish_frequency is None or isinstance(republish_frequency, (int, float)) and republish_frequency >= 0, \
               "republish_frequency must be a non-negative number or None."
        assert retry_interval is None or isinstance(retry_interval, (int, float)) and retry_interval >= 0, \
               "retry_interval must be a non-negative number or None."

        # Store configuration
        self._republish_frequency: Optional[float] = republish_frequency
        self._retry_interval: Optional[float] = retry_interval

        # Internal state for requested value
        # Initialize requested_value with the validated initial value from the BaseValue instance
        # Note: value_instance.value returns None if the initial_value in config was invalid
        self._requested_value: Any | None = self._value_instance.value
        if self._requested_value is not None:
            # Optional: Print initialization info
            # print(f"Info: Initialized Writable Point {self.addr} (UUID: {self.uuid}) requested_value to initial value: {self._requested_value}")
            pass
        else:
            # If initial value was invalid or not provided, requested_value starts as None
            print(f"Warning: Initialized Writable Point {self.addr} (UUID: {self.uuid}) requested_value to None (no valid initial value).")


    # --- CoreWritablePoint Interface Properties ---

    @property
    def requested_value(self) -> Any | None:
        """Get the last successfully set requested value for this point."""
        return self._requested_value

    @property
    def republish_frequency(self) -> float | None:
        """Get the configured republish frequency (seconds)."""
        return self._republish_frequency

    @property
    def retry_interval(self) -> float | None:
        """Get the configured retry interval (seconds)."""
        return self._retry_interval

    # --- CoreWritablePoint Interface Methods ---

    def set_requested_value(self, value: Any) -> bool:
        """
        Sets the desired value for the point after validating it against the
        underlying BaseValue's rules using its is_value_valid method.

        Args:
            value: The value to request.

        Returns:
            True if the value is considered valid, False otherwise.
        """
        # Delegate validation to the contained BaseValue instance
        if self._value_instance.is_value_valid(value):
            # Only update if the value actually changes
            if self._requested_value != value:
                self._requested_value = value
                # print(f"Debug (UUID {self.uuid}): Requested value set to {value}") # Optional debug
            return True
        else:
            print(f"Warning (UUID {self.uuid}): Attempted to set invalid requested value '{value}'. Request ignored.")
            return False