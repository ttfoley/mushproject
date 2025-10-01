from abc import ABC, abstractmethod
from typing import Any, Optional, Tuple
from .core_values import BaseValue
from datetime import datetime

class BasePoint(ABC):
    """Interface for managing a BaseValue."""

    @property
    @abstractmethod
    def uuid(self) -> int:
        """Get the UUID (likely delegated from BaseValue)."""
        # Hint: implementations will likely do 'return self.get_value_instance().uuid'
        pass

    @property
    @abstractmethod
    def addr(self) -> str:
        """Get the address/topic (likely delegated from BaseValue)."""
        pass

    @property
    @abstractmethod
    def value(self) -> Any | None:
        """Get the last valid value (likely delegated from BaseValue)."""
        pass

    @property
    @abstractmethod
    def raw_value(self) -> Any | None:
        """Get the last received raw value (likely delegated from BaseValue)."""
        pass

    @property
    @abstractmethod
    def is_valid(self) -> bool:
        """Check if the current value is valid (likely delegated from BaseValue)."""
        pass

    @property
    @abstractmethod
    def last_update_time(self) -> datetime | None:
        """Get timestamp of last successful value update (likely delegated)."""
        pass

    @property
    @abstractmethod
    def last_raw_update_time(self) -> datetime | None:
        """Get timestamp of last raw value received (likely delegated)."""
        pass

    @abstractmethod
    def get_value_instance(self) -> BaseValue:
        """Return the contained BaseValue instance."""
        pass

    @abstractmethod
    def handle_incoming_update(self, raw_input: Any) -> Tuple[bool, Optional[Any]]:
        """
        Processes an incoming raw value by calling the managed
        BaseValue's try_update method.
        Returns the result from try_update.
        (Implementations will likely call self.get_value_instance().try_update())
        """
        pass


# Interface specifically for Writable Points
class CoreWritablePoint(BasePoint):
    """Interface for points that can have a desired value set."""

    @property
    @abstractmethod
    def requested_value(self) -> Any | None:
        """Get the last requested value for this point."""
        pass

    @abstractmethod
    def set_requested_value(self, value: Any) -> bool:
        """
        Sets the desired value for the point.
        May perform basic type checks/validation based on the underlying
        BaseValue's rules, returning True for success, False for failure.
        Does NOT trigger publishing directly.
        """
        pass

    # --- Configuration Properties (needed by the Point Manager) ---
    @property
    @abstractmethod
    def republish_frequency(self) -> float | None:
        """Get the configured republish frequency (seconds). None if not applicable."""
        pass

    @property
    @abstractmethod
    def retry_interval(self) -> float | None:
        """Get the configured retry interval (seconds). None if not applicable."""
        pass