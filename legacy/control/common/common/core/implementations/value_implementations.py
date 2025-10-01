# control/common/core/implementations/value_implementations.py

from datetime import datetime
from typing import Any, Tuple, Optional, List, Dict, Set, Type

# Assuming BaseValue is correctly importable from core_values
# Adjust import path if necessary
try:
    from ..core_values import BaseValue
except ImportError:
    # Fallback import - adjust as needed for your environment
    import sys
    import os
    sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..')) # Add common/ to path
    from core.core_values import BaseValue


class CoreConcreteValueError(ValueError):
    """Custom exception for value implementation errors."""
    pass

# --- Refactored CoreConcreteDiscreteValue ---
class CoreConcreteDiscreteValue(BaseValue):
    """
    Concrete implementation of BaseValue for discrete values.
    Manages state, validity based on a predefined set of allowed values,
    and optional input value mapping. Refactored to use internal helper.
    """

    def __init__(self,
                 uuid: int,
                 addr: str,
                 valid_values: List[Any],
                 value_mapper: Optional[Dict[Any, Any]] = None,
                 initial_value: Optional[Any] = None):
        """
        Initializes the discrete value holder.
        (Args documentation omitted for brevity - see previous versions)
        """
        assert isinstance(uuid, int), "UUID must be an integer."
        assert isinstance(addr, str) and addr, "Address must be a non-empty string."
        assert isinstance(valid_values, list) and valid_values, "valid_values must be a non-empty list."

        self._uuid = uuid
        self._addr = addr
        self._valid_values_set: Set[Any] = set(valid_values)
        self._value_mapper: Dict[Any, Any] = value_mapper if value_mapper is not None else {}

        # Internal state variables
        self._value: Any | None = None
        self._raw_value: Any | None = None
        self._is_valid: bool = False
        self._last_update_time: datetime | None = None
        self._last_raw_update_time: datetime | None = None

        # Set initial value if provided and valid
        if initial_value is not None:
            success, processed = self.try_update(initial_value)
            if not success:
                print(f"Warning: Initial value '{initial_value}' for UUID {self._uuid} ({self._addr}) is invalid. Value remains uninitialized.")
            # else: print(f"Initialized UUID {self._uuid} ({self._addr}) with value: {processed}") # Optional debug

    # --- Properties ---
    @property
    def uuid(self) -> int:
        return self._uuid

    @property
    def addr(self) -> str:
        return self._addr

    @property
    def value(self) -> Any | None:
        return self._value if self._is_valid else None

    @property
    def raw_value(self) -> Any | None:
        return self._raw_value

    @property
    def is_valid(self) -> bool:
        return self._is_valid

    @property
    def last_update_time(self) -> datetime | None:
        return self._last_update_time

    @property
    def last_raw_update_time(self) -> datetime | None:
        return self._last_raw_update_time

    # --- Internal Validation Helper ---
    def _try_map_and_validate(self, value_to_check: Any) -> Tuple[bool, Optional[Any]]:
        """
        Internal helper: Applies mapping (if any) and validates against the allowed set.

        Returns:
            Tuple (success: bool, processed_value: Optional[Any])
        """
        processed_value = value_to_check
        # Apply mapping if a mapper exists
        if self._value_mapper:
            if value_to_check in self._value_mapper:
                processed_value = self._value_mapper[value_to_check]
            # Decide: if not in mapper keys, is it implicitly invalid or check raw?
            # Current: Check the potentially mapped value against the valid set.

        # Validate the (potentially mapped) value against the set of valid values
        if processed_value in self._valid_values_set:
            return True, processed_value
        else:
            return False, None

    # --- BaseValue Interface Methods ---
    def is_value_valid(self, value: Any) -> bool:
        """Checks if the value is valid for this discrete set (after mapping)."""
        success, _ = self._try_map_and_validate(value)
        return success

    def try_update(self, raw_input: Any) -> Tuple[bool, Optional[Any]]:
        """
        Attempts to process and validate the raw_input for a discrete value
        using the internal helper method. Updates internal state only if
        validation succeeds.
        """
        now = datetime.now()
        self._raw_value = raw_input
        self._last_raw_update_time = now

        # Perform mapping and validation using the helper
        is_valid_input, processed_value = self._try_map_and_validate(raw_input)

        if is_valid_input:
            # Update internal state only if the value has changed or was previously invalid
            if self._value != processed_value or not self._is_valid:
                self._value = processed_value
                self._is_valid = True
                self._last_update_time = now
            return True, self._value # Return the valid, processed value
        else:
            # Input was invalid
            if self._is_valid: # Only print if changing from valid to invalid
                 print(f"Warning (UUID {self.uuid}): Invalid input '{raw_input}' received. Setting state to invalid.")
            self._is_valid = False
            # self._value remains the last known *valid* value
            return False, None # Return None as processed_value on failure


# --- Refactored CoreConcreteContinuousValue ---
class CoreConcreteContinuousValue(BaseValue):
    """
    Concrete implementation of BaseValue for continuous values (like floats).
    Manages state, validity based on a numeric range, and type conversion.
    Refactored to use internal helper.
    """

    def __init__(self,
                 uuid: int,
                 addr: str,
                 valid_range: Dict[str, float], # Expects {"lower": float, "upper": float}
                 value_type: Type = float, # The expected Python type (e.g., float, int)
                 initial_value: Optional[Any] = None):
        """
        Initializes the continuous value holder.
        (Args documentation omitted for brevity - see previous versions)
        """
        assert isinstance(uuid, int), "UUID must be an integer."
        assert isinstance(addr, str) and addr, "Address must be a non-empty string."
        assert isinstance(valid_range, dict) and "lower" in valid_range and "upper" in valid_range, \
               "valid_range must be a dict with 'lower' and 'upper' keys."
        assert isinstance(valid_range["lower"], (int, float)) and isinstance(valid_range["upper"], (int, float)), \
               "valid_range lower and upper bounds must be numeric."
        assert valid_range["lower"] <= valid_range["upper"], "valid_range lower bound cannot be greater than upper bound."
        assert isinstance(value_type, type) and value_type in [float, int], \
               "value_type must be a valid numeric type like float or int."

        self._uuid = uuid
        self._addr = addr
        self._valid_range = valid_range
        self._value_type = value_type

        # Internal state variables
        self._value: Optional[value_type] = None
        self._raw_value: Any | None = None
        self._is_valid: bool = False
        self._last_update_time: datetime | None = None
        self._last_raw_update_time: datetime | None = None

        # Set initial value if provided and valid
        if initial_value is not None:
            success, processed = self.try_update(initial_value)
            if not success:
                 print(f"Warning: Initial value '{initial_value}' for UUID {self._uuid} ({self._addr}) is invalid. Value remains uninitialized.")
            # else: print(f"Initialized UUID {self._uuid} ({self._addr}) with value: {processed}") # Optional debug

    # --- Properties ---
    @property
    def uuid(self) -> int:
        return self._uuid

    @property
    def addr(self) -> str:
        return self._addr

    @property
    def value(self) -> Any | None:
        return self._value if self._is_valid else None

    @property
    def raw_value(self) -> Any | None:
        return self._raw_value

    @property
    def is_valid(self) -> bool:
        return self._is_valid

    @property
    def last_update_time(self) -> datetime | None:
        return self._last_update_time

    @property
    def last_raw_update_time(self) -> datetime | None:
        return self._last_raw_update_time

    # --- Internal Validation Helper ---
    def _try_convert_and_validate(self, value_to_check: Any) -> Tuple[bool, Optional[Any]]:
        """
        Internal helper: Attempts conversion and range validation.

        Returns:
            Tuple (success: bool, converted_value: Optional[Any])
        """
        try:
            converted_value = self._value_type(value_to_check)
            if self._valid_range["lower"] <= converted_value <= self._valid_range["upper"]:
                return True, converted_value
            else:
                return False, None # Out of range
        except (ValueError, TypeError):
            return False, None # Conversion failed

    # --- BaseValue Interface Methods ---
    def is_value_valid(self, value: Any) -> bool:
        """Checks if the value is convertible and within the valid range."""
        success, _ = self._try_convert_and_validate(value)
        return success

    def try_update(self, raw_input: Any) -> Tuple[bool, Optional[Any]]:
        """
        Attempts to process and validate the raw_input for a continuous value
        using the internal helper method. Updates internal state only if
        conversion and validation succeed.
        """
        now = datetime.now()
        self._raw_value = raw_input
        self._last_raw_update_time = now

        is_valid_input, processed_value = self._try_convert_and_validate(raw_input)

        if is_valid_input:
            if self._value != processed_value or not self._is_valid:
                self._value = processed_value
                self._is_valid = True
                self._last_update_time = now
            return True, self._value
        else:
            if self._is_valid:
                 print(f"Warning (UUID {self.uuid}): Invalid input '{raw_input}' received. Setting state to invalid.")
            self._is_valid = False
            return False, None