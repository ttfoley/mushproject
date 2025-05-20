# common/config_models/core_ssot_models.py

import enum
from typing import Any, Dict, List, Optional, Union, Literal
from pydantic import BaseModel, Field
from pydantic_core import core_schema
from pydantic.annotated_handlers import GetCoreSchemaHandler # For PointUUID
# Import for __get_pydantic_json_schema__ if you decide to re-add it.
# from pydantic.json_schema import JsonSchemaValue, GenerateJsonSchemaHandler


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

    # If you want to customize JSON Schema output for PointUUID,
    # you can re-add the __get_pydantic_json_schema__ method here.
    # For example:
    # @classmethod
    # def __get_pydantic_json_schema__(
    # cls, core_schema_obj: core_schema.CoreSchema, handler: GenerateJsonSchemaHandler
    # ) -> JsonSchemaValue:
    # json_schema = handler(core_schema_obj)
    #     schema_updates = {
    #         "format": "uuid",
    #         "examples": ["00000000-0000-0000-0000-000000000000"],
    #     }
    # json_schema.update(schema_updates)
    # return json_schema


# --- Enums for controlled vocabulary ---
class ValueType(str, enum.Enum):
    CONTINUOUS = "CONTINUOUS"
    DISCRETE = "DISCRETE"
    BOOLEAN = "BOOLEAN"

class DataSourceLayer(str, enum.Enum):
    MICROCONTROLLER = "microcontroller"
    DRIVER = "driver"
    DATA_PROCESSOR = "data_processor"
    GOVERNOR = "governor"
    MANUAL_INPUT = "manual_input"

class AccessMode(str, enum.Enum):
    READ_ONLY = "READ_ONLY"
    READ_WRITE = "READ_WRITE"

class ComponentType(str, enum.Enum):
    MICROCONTROLLER = "microcontroller"
    DRIVER = "driver"
    GOVERNOR = "governor"
    DATA_PROCESSOR = "data_processor"

# --- Core SSOT Models ---
class MQTTBrokerConfig(BaseModel):
    host: str = Field(..., description="Hostname or IP address of the MQTT broker.")
    port: int = Field(1883, description="Port number for the MQTT broker.")
    model_config = {"extra": "forbid"}

class PointValidationRules(BaseModel):
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    allowed_values: Optional[List[Any]] = None
    model_config = {"extra": "forbid"}

class PointDefinition(BaseModel):
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

# --- Component Definitions ---
class ComponentDefinition(BaseModel):
    id: str = Field(..., description="Unique identifier for this component instance.")
    config_file: str = Field(..., description="Path to the component's specific YAML configuration file.")
    mqtt_client_id: Optional[str] = Field(None, description="Optional MQTT client ID. If None, defaults to component 'id'.")
    model_config = {"extra": "forbid"}

class MicrocontrollerComponentDefinition(ComponentDefinition):
    type: Literal[ComponentType.MICROCONTROLLER] = ComponentType.MICROCONTROLLER
    points_provided: List[PointUUID] = Field(..., description="List of point UUIDs that this microcontroller directly provides.")

class DriverComponentDefinition(ComponentDefinition):
    type: Literal[ComponentType.DRIVER] = ComponentType.DRIVER
    controls_microcontroller: str = Field(..., description="The 'id' of the microcontroller component this driver controls.")
    virtual_points_provided: List[PointUUID] = Field([], description="List of point UUIDs synthesized or managed by this driver.")

class GovernorComponentDefinition(ComponentDefinition):
    type: Literal[ComponentType.GOVERNOR] = ComponentType.GOVERNOR
    controls_drivers: List[str] = Field(..., description="List of driver component 'id's that this governor controls.")
    virtual_points_provided: Optional[List[PointUUID]] = Field([], description="List of point UUIDs synthesized or managed by this governor.")

# --- Main System Definition ---
AnyComponent = Union[
    MicrocontrollerComponentDefinition,
    DriverComponentDefinition,
    GovernorComponentDefinition
]

class SystemDefinition(BaseModel):
    mqtt_broker: MQTTBrokerConfig = Field(..., description="MQTT broker connection details.")
    command_hierarchy: List[str] = Field(..., description="List defining command authority levels.")
    points: List[PointDefinition] = Field(..., description="Master list of all logical points in the system.")
    components: List[AnyComponent] = Field(..., description="List of all running component instances.")
    model_config = {"extra": "forbid"}
