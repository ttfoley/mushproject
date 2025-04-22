from abc import ABC, abstractmethod
from typing import Any, Tuple, Optional
from datetime import datetime

class BaseValue(ABC):
    """
    Interface for storing a value, its validity rules,
    and tracking its state.
    """

    @property
    @abstractmethod
    def uuid(self) -> int:
        """Get the unique identifier for this value."""
        pass

    @property
    @abstractmethod
    def addr(self) -> str:
        """Get the address/topic associated with this value."""
        pass

    @property
    @abstractmethod
    def value(self) -> Any | None:
        """Get the last known valid processed value. Returns None if never valid."""
        pass

    @property
    @abstractmethod
    def raw_value(self) -> Any | None:
        """Get the last received raw value, even if invalid. Returns None if never updated."""
        pass

    @property
    @abstractmethod
    def is_valid(self) -> bool:
        """Check if the current processed value is considered valid according to rules."""
        pass

    @property
    @abstractmethod
    def last_update_time(self) -> datetime | None:
        """Get the timestamp of the last successful validation/update."""
        pass

    @property
    @abstractmethod
    def last_raw_update_time(self) -> datetime | None:
        """Get the timestamp when the last raw value was received."""
        pass

    @abstractmethod
    def try_update(self, raw_input: Any) -> Tuple[bool, Optional[Any]]:
        """
        Attempts to process and validate the raw_input.

        - Updates internal raw_value and last_raw_update_time regardless.
        - If processing and validation succeed:
            - Updates internal processed value.
            - Sets is_valid to True.
            - Updates last_update_time.
            - Returns (True, processed_value).
        - If processing or validation fail:
            - Sets is_valid to False (or keeps it False).
            - Does NOT update the internal processed value or last_update_time.
            - Returns (False, None).

        Args:
            raw_input: The new raw value received.

        Returns:
            A tuple: (success: bool, processed_value: Optional[Any])
                     Indicates if the update was valid and returns the
                     processed value if it was.
        """
        pass

    # Optional: Maybe an internal helper?
    # @abstractmethod
    # def _check_rules(self, processed_value: Any) -> bool:
    #     """Internal helper to check rules specific to the type."""
    #     pass