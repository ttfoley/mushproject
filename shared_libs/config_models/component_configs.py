# common/config_models/component_configs.py

import enum
from typing import Any, Dict, List, Optional, Union, Literal, Self, Type
from pydantic import BaseModel, Field, model_validator, ValidationInfo
from pydantic_core import core_schema
# Correct import path for GetCoreSchemaHandler in Pydantic V2
from pydantic.annotated_handlers import GetCoreSchemaHandler

# Assuming PointUUID, ValueType, AccessMode are defined in core_ssot_models
# and PointDefinition structure is known for lookups.
from .core_ssot_models import PointUUID, ValueType, AccessMode, PointDefinition


# --- Enums ---
class ComparatorType(str, enum.Enum):
    EQ = "=="
    NE = "!="
    GT = ">"
    LT = "<"
    GE = ">="
    LE = "<="

# --- Action Definitions ---
class WriteAction(BaseModel):
    action_type: Literal["write_to_point"] = Field("write_to_point", description="Type indicator for this action.")
    point_uuid: PointUUID = Field(..., description="UUID of the Point to write to.")
    value: Any = Field(..., description="The value to write to the point.")
    model_config = {"extra": "forbid"}

AnyAction = WriteAction

# --- State Definition ---
class StateCondition(BaseModel):
    point_uuid: PointUUID = Field(..., description="UUID of the point whose value is checked.")
    expected_value: Any = Field(..., description="The value the point must have.")
    model_config = {"extra": "forbid"}

class StateDefinition(BaseModel):
    defining_conditions: List[StateCondition] = Field(...,
        description="List of conditions that MUST ALL be true simultaneously for the system to BE considered in this state.")
    entry_actions: List[AnyAction] = Field([],
        description="List of actions to perform immediately upon entering this state.")
    exit_actions: List[AnyAction] = Field([],
        description="List of actions to perform immediately upon exiting this state.")
    model_config = {"extra": "forbid"}

# --- Constraint Definitions ---
class BaseConstraintDefinition(BaseModel):
    description: Optional[str] = Field(None, description="Optional description of the constraint's purpose.")
    id: Optional[int] = Field(None, description="Optional numeric identifier for this constraint definition.")
    model_config = {"extra": "forbid"}

class ValueConstraintDefinition(BaseConstraintDefinition):
    type: Literal["value", "discrete_value", "continuous_value"] = Field(..., description="Type indicator for value comparison.")
    value_A_point_uuid: PointUUID = Field(..., description="UUID of the primary Point (A) whose value is being checked.")
    comparator: ComparatorType = Field(..., description="The comparison operator.")
    comparand_B_static_value: Optional[Any] = Field(None, description="Static value (B) to compare against. Use EITHER this OR comparand_B_point_uuid.")
    comparand_B_point_uuid: Optional[PointUUID] = Field(None, description="UUID of the Point (B) providing the dynamic value to compare against. Use EITHER this OR comparand_B_static_value.")

    @model_validator(mode='after')
    def check_comparand_b_source(self) -> Self:
        static_present = self.comparand_B_static_value is not None
        point_present = self.comparand_B_point_uuid is not None
        if static_present == point_present:
            raise ValueError('Exactly one of "comparand_B_static_value" or "comparand_B_point_uuid" must be provided for ValueConstraintDefinition')
        return self

class StateTimeConstraintDefinition(BaseConstraintDefinition):
    type: Literal["state_time"] = Field(..., description="Type indicator for state time comparison.")
    value_A_point_uuid: PointUUID = Field(..., description="UUID of the Point representing time elapsed in the current state (A).")
    comparator: ComparatorType = Field(ComparatorType.GE, description="Comparison operator (usually >= for time).")
    comparand_B_static_value: Optional[float] = Field(None, description="Static duration value (B, in seconds). Use EITHER this OR comparand_B_point_uuid.")
    comparand_B_point_uuid: Optional[PointUUID] = Field(None, description="UUID of the Point (B) providing the dynamic duration value. Use EITHER this OR comparand_B_static_value.")

    @model_validator(mode='after')
    def check_comparand_b_source(self) -> Self:
        static_present = self.comparand_B_static_value is not None
        point_present = self.comparand_B_point_uuid is not None
        if static_present == point_present:
            raise ValueError('Exactly one of "comparand_B_static_value" or "comparand_B_point_uuid" must be provided for StateTimeConstraintDefinition')
        return self

AnyConstraintDefinition = Union[StateTimeConstraintDefinition, ValueConstraintDefinition]

class ConstraintDefinition(BaseModel):
    definition: AnyConstraintDefinition = Field(..., description="The specific parameters defining the constraint's logic.")
    type: str = Field(..., description="Type of the constraint (e.g., state_time, discrete_value). Must match the type within 'definition'.")
    description: Optional[str] = Field(None, description="Overall description of this constraint instance.")

    @model_validator(mode='after')
    def check_type_match(self) -> Self:
        if self.definition and hasattr(self.definition, 'type') and self.type != self.definition.type:
             raise ValueError(f"Outer constraint type '{self.type}' does not match definition type '{self.definition.type}'")
        return self
    model_config = {"extra": "forbid"}

class ConstraintGroup(BaseModel):
    id: Optional[int] = Field(None, description="Optional numeric identifier for the group.")
    constraints: List[ConstraintDefinition] = Field(..., description="List of constraints in this group (AND logic).")
    description: Optional[str] = Field(None, description="Description of this constraint group's purpose.")
    priority: int = Field(0, description="Priority for evaluating this group (lower value = higher priority).")
    model_config = {"extra": "forbid"}

class TransitionDefinition(BaseModel):
    constraint_groups: List[ConstraintGroup] = Field(...,
        description="List of constraint groups. Transition occurs if ANY group is met (OR logic). Evaluated in priority order.")
    model_config = {"extra": "forbid"}

# --- PWM Output Mapping ---
class DriverPWMOutputMapping(BaseModel):
    input_point_uuid: PointUUID = Field(..., description="UUID of the Point providing the PWM setpoint (e.g., 0.0-1.0 value).")
    output_actuator_uuid: PointUUID = Field(..., description="UUID of the ON/OFF Point controlling the physical actuator.")
    pwm_period_seconds: float = Field(..., gt=0, description="The period (in seconds) over which the PWM cycle repeats (must be > 0).")
    model_config = {"extra": "forbid"}

    @model_validator(mode='after')
    def check_point_types(self, info: ValidationInfo) -> Self:
        points_map: Optional[Dict[PointUUID, PointDefinition]] = info.context.get("points_by_uuid_map") if info.context else None
        if not points_map:
            return self

        input_p_def = points_map.get(self.input_point_uuid)
        if input_p_def and input_p_def.value_type != ValueType.CONTINUOUS:
            raise ValueError(
                f"PWM input_point_uuid '{self.input_point_uuid}' (name: {input_p_def.name}) "
                f"must refer to a CONTINUOUS point, but it is {input_p_def.value_type.value}."
            )

        output_p_def = points_map.get(self.output_actuator_uuid)
        if output_p_def:
            if output_p_def.value_type not in [ValueType.DISCRETE, ValueType.BOOLEAN]:
                raise ValueError(
                    f"PWM output_actuator_uuid '{self.output_actuator_uuid}' (name: {output_p_def.name}) "
                    f"must refer to a DISCRETE or BOOLEAN point, but it is {output_p_def.value_type.value}."
                )
            if output_p_def.access != AccessMode.READ_WRITE:
                raise ValueError(
                    f"PWM output_actuator_uuid '{self.output_actuator_uuid}' (name: {output_p_def.name}) "
                    f"must be READ_WRITE, but it is {output_p_def.access.value}."
                )
        return self

# --- Driver Config Root Model ---
class DriverConfig(BaseModel):
    initial_state: str = Field(..., description="The name of the state the driver should start in.")
    states: Dict[str, StateDefinition] = Field(..., description="Definitions for each possible state (map of state_name -> state_definition).")
    transitions: Dict[str, Dict[str, TransitionDefinition]] = Field(..., description="Definitions for transitions between states.")
    pwm_outputs: Optional[List[DriverPWMOutputMapping]] = Field(None, description="Optional list of PWM output configurations handled by this driver.")
    model_config = {"extra": "forbid"}

    @model_validator(mode='after')
    def check_initial_state_and_transitions(self, info: ValidationInfo) -> Self:
        defined_state_names = set(self.states.keys()) if self.states else set()
        if self.initial_state not in defined_state_names:
            raise ValueError(
                f"'initial_state' ('{self.initial_state}') is not a defined state. "
                f"Defined states: {defined_state_names or '{}'}."
            )
        if self.transitions:
            for from_state, to_states_dict in self.transitions.items():
                if from_state not in defined_state_names:
                    raise ValueError(
                        f"Transition defined FROM non-existent state '{from_state}'. "
                        f"Defined states: {defined_state_names or '{}'}."
                    )
                if to_states_dict:
                    for to_state in to_states_dict.keys():
                        if to_state not in defined_state_names:
                            raise ValueError(
                                f"Transition defined FROM '{from_state}' TO non-existent state '{to_state}'. "
                                f"Defined states: {defined_state_names or '{}'}."
                            )
        return self


# ==============================================================================
# === MICROCONTROLLER HARDWARE POINTS MODELS (NEW) ===========================
# ==============================================================================

# --- Supporting Sub-Models for Microcontroller ---
class WiFiConfig(BaseModel):
    ssid: Optional[str] = Field(None, description="WiFi network SSID. If not provided, uses global setting.")
    password: Optional[str] = Field(None, description="WiFi network password. If not provided, uses global setting.")
    model_config = {"extra": "forbid"}

class MQTTBrokerConfigOptional(BaseModel):
    address: Optional[str] = Field(None, description="MQTT broker address. If not provided, uses global setting.")
    port: Optional[int] = Field(None, description="MQTT broker port. If not provided, uses global setting.")
    username: Optional[str] = Field(None, description="MQTT username. If not provided, uses global setting.")
    password: Optional[str] = Field(None, description="MQTT password. If not provided, uses global setting.")
    model_config = {"extra": "forbid"}

class NTPServerConfigOptional(BaseModel):
    address: Optional[str] = Field(None, description="NTP server address. If not provided, uses global setting.")
    utc_offset_seconds: Optional[int] = Field(None, description="UTC offset in seconds. If not provided, uses global setting.")
    update_interval_ms: Optional[int] = Field(None, description="NTP update interval in milliseconds. If not provided, uses global setting.")
    model_config = {"extra": "forbid"}

class TimingConstants(BaseModel):
    publish_interval_ms: int = Field(..., gt=0, description="Sensor publish interval in milliseconds (e.g., 15000 for 15 seconds).")
    wifi_connect_timeout_ms: Optional[int] = Field(30000, gt=0, description="WiFi connection timeout in milliseconds.")
    mqtt_connect_timeout_ms: Optional[int] = Field(20000, gt=0, description="MQTT connection timeout in milliseconds.")
    ntp_sync_timeout_ms: Optional[int] = Field(15000, gt=0, description="NTP synchronization timeout in milliseconds.")
    model_config = {"extra": "forbid"}

class MicrocontrollerTimingConstants(BaseModel):
    """FSM and logic-specific timing constants for microcontroller behavior."""
    # Sensor and status publishing intervals
    sensor_and_status_publish_interval_ms: int = Field(30000, gt=0, description="How often sensors publish data (milliseconds).")
    status_publish_interval_ms: int = Field(300000, gt=0, description="How often status messages are published (milliseconds).")
    
    # FSM retry configuration  
    max_wifi_attempts: int = Field(10, gt=0, description="Maximum WiFi connection attempts before restart.")
    wifi_attempt_timeout_ms: int = Field(20000, gt=0, description="Timeout for each WiFi connection attempt (milliseconds).")
    max_ntp_attempts: int = Field(5, gt=0, description="Maximum NTP sync attempts before restart.")
    ntp_attempt_timeout_ms: int = Field(30000, gt=0, description="Timeout for each NTP sync attempt (milliseconds).")
    
    # Operational timeouts and maintenance
    max_time_no_publish_ms: int = Field(300000, gt=0, description="Maximum time without publishing before restart (milliseconds).")
    maintenance_restart_interval_ms: int = Field(604800000, gt=0, description="Automatic restart interval for maintenance (milliseconds, default 1 week).")
    periodic_checks_interval_ms: int = Field(3600000, gt=0, description="Interval for periodic health checks (milliseconds, default 1 hour).")
    
    # Loop and retry delays
    main_loop_delay_ms: int = Field(10, gt=0, description="Delay in main loop iteration (milliseconds).")
    mqtt_retry_delay_ms: int = Field(2000, gt=0, description="Delay between MQTT connection retries (milliseconds).")
    restart_delay_ms: int = Field(1000, gt=0, description="Delay before restarting controller (milliseconds).")
    ntp_loop_update_interval_ms: int = Field(60000, gt=0, description="Interval for NTP updates in main loop (milliseconds).")
    debug_queue_interval_ms: int = Field(30000, gt=0, description="Interval for debug queue status prints (milliseconds).")
    
    model_config = {"extra": "forbid"}

# --- Hardware Point Base Classes ---
class HardwarePointBase_MicrocontrollerImpl(BaseModel):
    name: str = Field(..., description="Logical name for this hardware point (used for C++ define prefixes).")
    point_kind: str = Field(..., description="Type of hardware point (actuator, sensor_data, system_info).")
    model_config = {"extra": "forbid"}

class ActuatorHardwarePoint_MicrocontrollerImpl(HardwarePointBase_MicrocontrollerImpl):
    point_kind: Literal["actuator"] = Field("actuator", description="Type indicator for actuator hardware points.")
    write_point_uuid_ref: PointUUID = Field(..., description="UUID of the command point that this actuator listens to.")
    readback_point_uuid_ref: PointUUID = Field(..., description="UUID of the readback/status point that this actuator reports.")
    pin: int = Field(..., description="GPIO pin number for this actuator.")
    pin_mode: Literal["OUTPUT"] = Field("OUTPUT", description="Pin mode (OUTPUT for actuators).")
    initial_state: Literal["HIGH", "LOW"] = Field("LOW", description="Initial pin state on startup.")
    model_config = {"extra": "forbid"}

class SensorDataHardwarePoint_MicrocontrollerImpl(HardwarePointBase_MicrocontrollerImpl):
    point_kind: Literal["sensor_data"] = Field("sensor_data", description="Type indicator for sensor data hardware points.")
    data_point_uuid_ref: PointUUID = Field(..., description="UUID of the data point that this sensor provides.")
    pin: Optional[int] = Field(None, description="GPIO pin number if applicable (e.g., for DHT sensors).")
    pin_mode: Optional[Literal["INPUT", "INPUT_PULLUP"]] = Field(None, description="Pin mode if applicable.")
    attributes: Optional[Dict[str, Any]] = Field(None, description="Additional sensor-specific attributes (e.g., I2C address, sensor model).")
    model_config = {"extra": "forbid"}

class SystemInfoHardwarePoint_MicrocontrollerImpl(HardwarePointBase_MicrocontrollerImpl):
    point_kind: Literal["system_info"] = Field("system_info", description="Type indicator for system info hardware points.")
    data_point_uuid_ref: PointUUID = Field(..., description="UUID of the system status point that this provides.")
    model_config = {"extra": "forbid"}

# Union type for all hardware points
AnyHardwarePoint_MicrocontrollerImpl = Union[
    ActuatorHardwarePoint_MicrocontrollerImpl,
    SensorDataHardwarePoint_MicrocontrollerImpl,
    SystemInfoHardwarePoint_MicrocontrollerImpl
]

# ==============================================================================
# === MICROCONTROLLER AND GOVERNOR MODELS (UPDATED) ==========================
# ==============================================================================

# --- Microcontroller Supporting Sub-Models (Legacy) ---
class I2CConfig(BaseModel):
    sda_pin: int = Field(..., description="GPIO pin number for I2C SDA.")
    scl_pin: int = Field(..., description="GPIO pin number for I2C SCL.")
    clock_speed: Optional[int] = Field(None, description="Optional I2C clock speed in Hz (e.g., 100000).")
    model_config = {"extra": "forbid"}

class I2CDevice(BaseModel):
    sensor_model: Literal["SHT85", "BME280", "SCD41", "SHT31", "SHT40", "MCP23017"] = Field(...,
        description="Specific model of the sensor/device (e.g., 'SHT85', 'BME280').")
    address: Union[int, str] = Field(..., description="I2C address (e.g., 0x44 or 68).")
    point_uuids: Dict[Literal["temperature", "humidity", "co2", "pressure"], PointUUID] = Field(...,
        description="Mapping of measurement type (e.g., 'temperature', 'humidity') to Point UUID.")
    settings: Optional[Dict[str, Any]] = Field(None, description="Optional device-specific settings (e.g., {'automatic_self_calibration': False}).")
    model_config = {"extra": "forbid"}

class OneWireConfig(BaseModel):
    pin: int = Field(..., description="GPIO pin number for the OneWire bus.")
    model_config = {"extra": "forbid"}

class OneWireDevice(BaseModel):
    sensor_model: Literal["DS18B20"]
    pin: int = Field(..., description="GPIO pin number for this OneWire device's bus.")
    point_uuid: PointUUID = Field(..., description="Point UUID for the temperature reading from this sensor.")
    model_config = {"extra": "forbid"}

class DHTSensorConfig(BaseModel):
    sensor_model: Literal["DHT11", "DHT22"] = Field(..., description="Specific model of the DHT sensor ('DHT11' or 'DHT22').")
    pin: int = Field(..., description="GPIO pin number connected to the DHT sensor.")
    point_uuids: Dict[Literal["temperature", "humidity"], PointUUID] = Field(...,
        description="Mapping of measurement type to Point UUID.")
    model_config = {"extra": "forbid"}

class DigitalOutputConfig(BaseModel):
    pin: int = Field(..., description="GPIO pin number for the digital output.")
    name: Optional[str] = Field(None, description="Logical name for this output (e.g., 'MisterRelay').")
    point_uuid: PointUUID = Field(..., description="Point UUID for the command/status of this output.")
    initial_state: Optional[Literal["on", "off"]] = Field("off", description="Initial state on startup ('on' or 'off').")
    model_config = {"extra": "forbid"}

class MicrocontrollerConfig(BaseModel):
    # New primary fields
    device_id: Optional[str] = Field(None, description="Device identifier for this microcontroller.")
    description: Optional[str] = Field(None, description="Human-readable description of this microcontroller's purpose.")
    wifi: Optional[WiFiConfig] = Field(None, description="WiFi configuration (overrides global settings if provided).")
    mqtt_broker: Optional[MQTTBrokerConfigOptional] = Field(None, description="MQTT broker configuration (overrides global settings if provided).")
    ntp_server: Optional[NTPServerConfigOptional] = Field(None, description="NTP server configuration (overrides global settings if provided).")
    timing_constants: Optional[TimingConstants] = Field(None, description="Infrastructure timing configuration for this microcontroller.")
    microcontroller_timing: Optional[MicrocontrollerTimingConstants] = Field(None, description="FSM and logic-specific timing configuration for this microcontroller.")
    hardware_points: Optional[List[AnyHardwarePoint_MicrocontrollerImpl]] = Field(None, description="List of hardware points managed by this microcontroller (new approach).")
    output_republish_frequency_ms: Optional[int] = Field(None, description="Output status republish interval in milliseconds.")
    
    # Legacy fields (for backward compatibility)
    i2c: Optional[I2CConfig] = Field(None, description="I2C bus configuration, required if i2c_devices are listed.")
    onewire: Optional[OneWireConfig] = Field(None, description="OneWire bus configuration, required if onewire_devices are listed.")
    i2c_devices: Optional[List[I2CDevice]] = Field(None, description="List of sensors/devices connected via I2C.")
    onewire_devices: Optional[List[OneWireDevice]] = Field(None, description="List of sensors connected via OneWire.")
    dht_sensors: Optional[List[DHTSensorConfig]] = Field(None, description="List of connected DHT sensors.")
    digital_outputs: Optional[List[DigitalOutputConfig]] = Field(None, description="List of configured digital output pins.")
    publish_frequency_ms: Optional[int] = Field(None,
        description="Sensor publish interval in milliseconds used by the microcontroller. (e.g., 15000 for 15 seconds). If not set, firmware default applies.")

    @model_validator(mode='after')
    def check_bus_configs(self) -> Self:
        if self.i2c_devices and not self.i2c:
            raise ValueError("i2c bus configuration must be provided if i2c_devices are listed.")
        return self
    model_config = {"extra": "forbid"}

# --- Governor Supporting Sub-Models ---
class _BaseGovernorControllerConfig(BaseModel):
    """Base for governor controllers to share validation logic if needed."""
    pass

    def _validate_point_property(
        self,
        points_map: Optional[Dict[PointUUID, PointDefinition]],
        point_uuid: PointUUID,
        point_attr_name: str, # Name of the attribute in the controller config model
        component_id: Optional[str], # ID of the governor component
        expected_access: Optional[AccessMode] = None,
        expected_value_type: Optional[ValueType] = None,
        check_writable_by: bool = False
    ) -> List[str]: # Returns list of error messages
        errors = []
        if not points_map: return ["Context (points_map) not available for validation."]

        p_def = points_map.get(point_uuid)
        if not p_def:
            errors.append(f"Point UUID '{point_uuid}' for '{point_attr_name}' not found in master point list.")
            return errors

        if expected_access and p_def.access != expected_access:
            errors.append(
                f"Point '{point_uuid}' ({p_def.name}) for '{point_attr_name}' "
                f"requires access '{expected_access.value}', but has '{p_def.access.value}'."
            )
        if expected_value_type and p_def.value_type != expected_value_type:
            errors.append(
                f"Point '{point_uuid}' ({p_def.name}) for '{point_attr_name}' "
                f"requires value_type '{expected_value_type.value}', but has '{p_def.value_type.value}'."
            )
        if check_writable_by and component_id:
            if not (p_def.writable_by and component_id in p_def.writable_by):
                errors.append(
                    f"Point '{point_uuid}' ({p_def.name}) for '{point_attr_name}' "
                    f"is not listed as writable_by component '{component_id}'."
                )
        return errors


class BangBangControllerConfig(_BaseGovernorControllerConfig):
    controller_type: Literal["bang_bang"] = Field("bang_bang", description="Discriminator field for controller type.")
    sensor_point_uuid: PointUUID = Field(..., description="UUID of the Point providing the process variable.")
    target_setpoint_point_uuid: PointUUID = Field(..., description="UUID of the Point providing the desired target value.")
    hysteresis_point_uuid: PointUUID = Field(..., description="UUID of the Point providing the hysteresis value (deadband).")
    output_command_point_uuid: PointUUID = Field(..., description="UUID of the Point where the Governor writes the calculated command ('on' or 'off').")
    model_config = {"extra": "forbid"}

    @model_validator(mode='after')
    def check_point_config(self, info: ValidationInfo) -> Self:
        points_map: Optional[Dict[PointUUID, PointDefinition]] = info.context.get("points_by_uuid_map") if info.context else None
        component_id: Optional[str] = info.context.get("component_id") if info.context else None
        all_errors: List[str] = []

        all_errors.extend(self._validate_point_property(points_map, self.sensor_point_uuid, "sensor_point_uuid", component_id, expected_access=AccessMode.READ_ONLY))
        all_errors.extend(self._validate_point_property(points_map, self.target_setpoint_point_uuid, "target_setpoint_point_uuid", component_id, expected_access=AccessMode.READ_WRITE))
        all_errors.extend(self._validate_point_property(points_map, self.hysteresis_point_uuid, "hysteresis_point_uuid", component_id, expected_access=AccessMode.READ_WRITE))
        all_errors.extend(self._validate_point_property(points_map, self.output_command_point_uuid, "output_command_point_uuid", component_id, expected_access=AccessMode.READ_WRITE, check_writable_by=True))

        if all_errors:
            raise ValueError(". ".join(all_errors))
        return self

class PIDControllerConfig(_BaseGovernorControllerConfig):
    controller_type: Literal["pid"] = Field("pid", description="Discriminator field for controller type.")
    sensor_point_uuid: PointUUID = Field(..., description="UUID of the Point providing the process variable (e.g., temperature sensor).")
    target_setpoint_point_uuid: PointUUID = Field(..., description="UUID of the Point providing the desired target value (e.g., target temperature setpoint).")
    output_pwm_setpoint_point_uuid: PointUUID = Field(..., description="UUID of the Point where the Governor writes the calculated PWM duty cycle (0.0-1.0).")
    output_on_duration_point_uuid: PointUUID = Field(..., description="UUID of the Point where the Governor writes the calculated ON duration (seconds) for the PWM cycle.")
    output_off_duration_point_uuid: PointUUID = Field(..., description="UUID of the Point where the Governor writes the calculated OFF duration (seconds) for the PWM cycle.")
    mode_command_point_uuid: PointUUID = Field(..., description="UUID of the Point where the Governor writes its mode command (e.g., 'PWM', 'OFF') to the corresponding Driver.")
    kp: float = Field(..., description="Proportional gain.")
    ki: float = Field(..., description="Integral gain.")
    kd: float = Field(..., description="Derivative gain.")
    min_output: float = Field(0.0, ge=0.0, le=1.0, description="Minimum output clamp value (usually 0.0).")
    max_output: float = Field(1.0, ge=0.0, le=1.0, description="Maximum output clamp value (usually 1.0).")
    pwm_period_seconds: float = Field(..., gt=0, description="The PWM period this PID loop targets (used to calculate ON/OFF durations). Must match the corresponding Driver's PWM configuration period.")
    model_config = {"extra": "forbid"}

    @model_validator(mode='after')
    def check_point_config(self, info: ValidationInfo) -> Self:
        points_map: Optional[Dict[PointUUID, PointDefinition]] = info.context.get("points_by_uuid_map") if info.context else None
        component_id: Optional[str] = info.context.get("component_id") if info.context else None
        all_errors: List[str] = []

        all_errors.extend(self._validate_point_property(points_map, self.sensor_point_uuid, "sensor_point_uuid", component_id, expected_access=AccessMode.READ_ONLY, expected_value_type=ValueType.CONTINUOUS))
        all_errors.extend(self._validate_point_property(points_map, self.target_setpoint_point_uuid, "target_setpoint_point_uuid", component_id, expected_access=AccessMode.READ_WRITE, expected_value_type=ValueType.CONTINUOUS)) # Typically RW
        all_errors.extend(self._validate_point_property(points_map, self.output_pwm_setpoint_point_uuid, "output_pwm_setpoint_point_uuid", component_id, expected_access=AccessMode.READ_WRITE, check_writable_by=True, expected_value_type=ValueType.CONTINUOUS))
        all_errors.extend(self._validate_point_property(points_map, self.output_on_duration_point_uuid, "output_on_duration_point_uuid", component_id, expected_access=AccessMode.READ_WRITE, check_writable_by=True, expected_value_type=ValueType.CONTINUOUS))
        all_errors.extend(self._validate_point_property(points_map, self.output_off_duration_point_uuid, "output_off_duration_point_uuid", component_id, expected_access=AccessMode.READ_WRITE, check_writable_by=True, expected_value_type=ValueType.CONTINUOUS))
        all_errors.extend(self._validate_point_property(points_map, self.mode_command_point_uuid, "mode_command_point_uuid", component_id, expected_access=AccessMode.READ_WRITE, check_writable_by=True, expected_value_type=ValueType.DISCRETE))


        if all_errors:
            raise ValueError(". ".join(all_errors))
        return self

class TimeScheduleControllerConfig(_BaseGovernorControllerConfig):
    controller_type: Literal["time_schedule"] = Field("time_schedule", description="Discriminator field for controller type.")
    on_interval_minutes_point_uuid: PointUUID = Field(..., description="UUID of the Point providing the ON duration in minutes.")
    off_interval_minutes_point_uuid: PointUUID = Field(..., description="UUID of the Point providing the OFF duration in minutes.")
    output_command_point_uuid: PointUUID = Field(..., description="UUID of the Point where the Governor writes the calculated command ('on' or 'off').")
    initial_phase: Optional[Literal["on", "off"]] = Field("off", description="The initial phase of the cycle on startup.")
    model_config = {"extra": "forbid"}

    @model_validator(mode='after')
    def check_point_config(self, info: ValidationInfo) -> Self:
        points_map: Optional[Dict[PointUUID, PointDefinition]] = info.context.get("points_by_uuid_map") if info.context else None
        component_id: Optional[str] = info.context.get("component_id") if info.context else None
        all_errors: List[str] = []

        all_errors.extend(self._validate_point_property(points_map, self.on_interval_minutes_point_uuid, "on_interval_minutes_point_uuid", component_id, expected_access=AccessMode.READ_WRITE, expected_value_type=ValueType.CONTINUOUS)) # Intervals are continuous
        all_errors.extend(self._validate_point_property(points_map, self.off_interval_minutes_point_uuid, "off_interval_minutes_point_uuid", component_id, expected_access=AccessMode.READ_WRITE, expected_value_type=ValueType.CONTINUOUS))
        all_errors.extend(self._validate_point_property(points_map, self.output_command_point_uuid, "output_command_point_uuid", component_id, expected_access=AccessMode.READ_WRITE, check_writable_by=True, expected_value_type=ValueType.DISCRETE))

        if all_errors:
            raise ValueError(". ".join(all_errors))
        return self

AnyControllerConfig = Union[PIDControllerConfig, BangBangControllerConfig, TimeScheduleControllerConfig]

class GovernorConfig(BaseModel):
    update_interval_seconds: float = Field(10.0, gt=0, description="How often the Governor runs its control logic loop (in seconds).")
    controllers: List[AnyControllerConfig] = Field(...,
        description="List of control loops (e.g., PID, Bang-Bang) managed by this Governor. The 'controller_type' field determines the specific parameters required for each.")
    model_config = {"extra": "forbid"}
