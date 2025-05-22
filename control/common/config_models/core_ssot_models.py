# common/config_models/core_ssot_models.py

import enum
from typing import Any, Dict, List, Optional, Union, Literal
from pydantic import BaseModel, Field, validator # validator might not be needed if reverting PointDefinition changes
from pydantic_core import core_schema
from pydantic.annotated_handlers import GetCoreSchemaHandler # For PointUUID

# --- Custom Type for Point UUIDs ---
class PointUUID(str):
    """
    Custom type for Point UUIDs. It's fundamentally a string,
    but this distinct type allows for semantic clarity and easier
    identification in model processing.
    """
    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        source_type: Any,
        handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        return core_schema.str_schema()

# --- Enums for controlled vocabulary (as per original uploaded file) ---
class ValueType(str, enum.Enum):
    CONTINUOUS = "CONTINUOUS"
    DISCRETE = "DISCRETE"
    BOOLEAN = "BOOLEAN"

class DataSourceLayer(str, enum.Enum):
    MICROCONTROLLER = "microcontroller"
    DRIVER = "driver"
    DATA_PROCESSOR = "data_processor" # Kept if it was in the original user upload
    GOVERNOR = "governor"
    MANUAL = "manual" # Reverted from MANUAL_INPUT

class AccessMode(str, enum.Enum):
    READ_ONLY = "READ_ONLY"
    READ_WRITE = "READ_WRITE"

class ComponentType(str, enum.Enum):
    MICROCONTROLLER = "microcontroller"
    DRIVER = "driver"
    GOVERNOR = "governor"
    DATA_PROCESSOR = "data_processor" # Kept if it was in the original user upload
    MANUAL = "manual"

# --- Global System Settings Models (NEW ADDITIONS) ---
class GlobalMQTTBrokerConfig(BaseModel):
    """Defines the mandatory global MQTT Broker configuration."""
    address: str = Field(..., description="Hostname or IP address of the global MQTT broker.")
    port: int = Field(1883, description="Port number for the global MQTT broker.")
    username: Optional[str] = Field(None, description="Optional username for the global MQTT broker.")
    password: Optional[str] = Field(None, description="Optional password for the global MQTT broker.")
    model_config = {"extra": "forbid"}

class GlobalNTPServerConfig(BaseModel):
    """Defines the mandatory global NTP Server configuration."""
    address: str = Field("pool.ntp.org", description="Address of the global NTP server.")
    utc_offset_seconds: int = Field(0, description="Global UTC offset in seconds.")
    update_interval_ms: int = Field(3600000, description="Global NTP update interval in milliseconds (e.g., 1 hour).")
    model_config = {"extra": "forbid"}

class GlobalSettings(BaseModel):
    """Defines global system settings, including MQTT prefix and default broker/NTP."""
    mqtt_topic_prefix: str = Field(..., description="Global MQTT topic prefix (e.g., 'mush/'). Must end with a slash if intended as a prefix path.")
    mqtt_broker: GlobalMQTTBrokerConfig = Field(..., description="Global MQTT broker connection details.")
    ntp_server: GlobalNTPServerConfig = Field(..., description="Global NTP server details.")
    model_config = {"extra": "forbid"}

# --- Core SSOT Models (PointDefinition, ComponentDefinition variants, SystemDefinition) ---
# Structure based on the original uploaded core_ssot_models.py, with GlobalSettings added to SystemDefinition
# MQTTBrokerConfig from original is now effectively GlobalMQTTBrokerConfig within GlobalSettings.

class PointValidationRules(BaseModel):
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    allowed_values: Optional[List[Any]] = None
    model_config = {"extra": "forbid"}

class PointDefinition(BaseModel): # Reverted to original structure (no ADR-20 topic fields)
    uuid: PointUUID = Field(..., description="Persistent unique identifier for the point.")
    name: str = Field(..., description="Human-readable identifier. Should be unique.")
    description: Optional[str] = Field(None, description="Optional longer description of the point.")
    value_type: ValueType = Field(..., description="The type of value the point holds.")
    units: str = Field(..., description="Units of measurement or value state.")
    data_source_layer: DataSourceLayer = Field(..., description="The system layer primarily responsible for publishing this point's data.")
    access: AccessMode = Field(..., description="Read/write access control for the point.")
    writable_by: Optional[List[str]] = Field(None, description="List of component IDs authorized to publish to this point's topic if access is READ_WRITE.")
    validation_rules: Optional[PointValidationRules] = Field(None, description="Optional rules to validate the point's value.")
    initial_value: Optional[Any] = Field(None, description="Optional default/initial logical value for the point.")
    persist_to_db: bool = Field(True, description="Flag indicating if this point's data should be persisted to the time-series database. Defaults to True.")
    readback_point_uuid: Optional[PointUUID] = Field(None, description="For a command/write point, the UUID of the corresponding status/readback point.")
    linked_points: Optional[Dict[str, PointUUID]] = Field(None, description="Optional dictionary linking this point to other related points by a descriptive key.")
    input_point_uuids: Optional[List[PointUUID]] = Field(None, description="UUIDs of points used as direct input for calculating this point's value (e.g., for a synthetic point).")
    model_config = {"extra": "forbid"}

class ComponentDefinition(BaseModel):
    id: str = Field(..., description="Unique identifier for this component instance.")
    config_file: Optional[str] = Field(None, description="Path to the component's specific YAML configuration file, if applicable.")
    mqtt_client_id: Optional[str] = Field(None, description="Optional MQTT client ID. If None, defaults to component 'id'.")
    model_config = {"extra": "forbid"}

class MicrocontrollerComponentDefinition(ComponentDefinition):
    type: Literal[ComponentType.MICROCONTROLLER] = ComponentType.MICROCONTROLLER
    points_provided: List[PointUUID] = Field(..., description="List of point UUIDs that this microcontroller directly provides.")

class DriverComponentDefinition(ComponentDefinition):
    type: Literal[ComponentType.DRIVER] = ComponentType.DRIVER
    controls_microcontroller: str = Field(..., description="The 'id' of the microcontroller component this driver controls.") # Reverted to mandatory
    # controls_drivers: Optional[List[str]] = Field(None, description="List of driver component 'id's that this driver controls (if any).") # Removed if not in original
    virtual_points_provided: List[PointUUID] = Field([], description="List of point UUIDs synthesized or managed by this driver.")

class GovernorComponentDefinition(ComponentDefinition):
    type: Literal[ComponentType.GOVERNOR] = ComponentType.GOVERNOR
    controls_drivers: List[str] = Field(..., description="List of driver component 'id's that this governor controls.")
    virtual_points_provided: Optional[List[PointUUID]] = Field([], description="List of point UUIDs synthesized or managed by this governor.")

class ManualSourceComponentDefinition(ComponentDefinition):
    type: Literal[ComponentType.MANUAL] = ComponentType.MANUAL
    virtual_points_provided: Optional[List[PointUUID]] = Field([], description="List of point UUIDs considered to be provided/sourced by manual input.")

# --- Main System Definition ---
AnyComponent = Union[
    MicrocontrollerComponentDefinition,
    DriverComponentDefinition,
    GovernorComponentDefinition,
    ManualSourceComponentDefinition
    # DataProcessorComponentDefinition - Removed if not in original
]

class SystemDefinition(BaseModel):
    # mqtt_broker: MQTTBrokerConfig was here in original, now part of GlobalSettings
    global_settings: GlobalSettings = Field(..., description="Global system-level settings.") # ADDED
    command_hierarchy: List[str] = Field(..., description="List defining command authority levels.")
    points: List[PointDefinition] = Field(..., description="Master list of all logical points in the system.")
    components: List[AnyComponent] = Field(..., description="List of all running component instances.")
    model_config = {"extra": "forbid"}
