from __future__ import annotations

from typing import Any, Optional, Set, Union, get_args, get_origin

from pydantic import BaseModel

from shared_libs.config_models.core_ssot_models import PointUUID
from shared_libs.config_models.component_configs import (
    DriverConfig,
    MicrocontrollerConfig,
    GovernorConfig,
)


class UUIDUtils:
    """Utility class for UUID-related operations."""

    @staticmethod
    def extract_uuids_from_instance(instance: Optional[Any], uuids_set: Set[str]):
        """
        Recursively extracts UUIDs from a Pydantic model instance or iterable
        by checking if field annotations are PointUUID or generics containing PointUUID.
        """
        if instance is None:
            return

        if isinstance(instance, BaseModel):
            for field_name, field_definition in instance.model_fields.items():
                field_value = getattr(instance, field_name)
                annotation = field_definition.annotation

                origin = get_origin(annotation)
                args = get_args(annotation)

                if annotation is PointUUID:
                    if isinstance(field_value, str):
                        uuids_set.add(field_value)
                elif origin is Union and PointUUID in args:
                    if isinstance(field_value, str):
                        uuids_set.add(field_value)
                elif origin is list and args and args[0] is PointUUID:
                    if isinstance(field_value, list):
                        for item in field_value:
                            if isinstance(item, str):
                                uuids_set.add(item)
                elif origin is Union:  # Handles Optional[List[PointUUID]]
                    is_optional_list_of_uuid = False
                    for union_arg in args:
                        if get_origin(union_arg) is list and get_args(union_arg) and get_args(union_arg)[0] is PointUUID:
                            is_optional_list_of_uuid = True
                            break
                    if is_optional_list_of_uuid and isinstance(field_value, list):
                        for item in field_value:
                            if isinstance(item, str):  # PointUUID is a str
                                uuids_set.add(item)
                elif origin is dict and args and len(args) == 2:  # Dict[_, PointUUID] or Dict[_, Optional[PointUUID]]
                    value_type_in_dict = args[1]
                    dict_val_origin = get_origin(value_type_in_dict)
                    dict_val_args = get_args(value_type_in_dict)

                    if value_type_in_dict is PointUUID:
                        if isinstance(field_value, dict):
                            for val_item in field_value.values():
                                if isinstance(val_item, str):
                                    uuids_set.add(val_item)
                    elif dict_val_origin is Union and PointUUID in dict_val_args:  # Optional[PointUUID]
                        if isinstance(field_value, dict):
                            for val_item in field_value.values():
                                if isinstance(val_item, str):
                                    uuids_set.add(val_item)
                elif isinstance(field_value, BaseModel):  # Recurse nested models
                    UUIDUtils.extract_uuids_from_instance(field_value, uuids_set)
                elif isinstance(field_value, list):
                    for item in field_value:
                        UUIDUtils.extract_uuids_from_instance(item, uuids_set)
                elif isinstance(field_value, dict):
                    for value_in_dict in field_value.values():
                        UUIDUtils.extract_uuids_from_instance(value_in_dict, uuids_set)
        elif isinstance(instance, list):
            for item in instance:
                UUIDUtils.extract_uuids_from_instance(item, uuids_set)
        elif isinstance(instance, dict):
            for value in instance.values():
                UUIDUtils.extract_uuids_from_instance(value, uuids_set)

    @staticmethod
    def extract_driver_point_uuids(config: DriverConfig) -> Set[str]:
        uuids: Set[str] = set()
        UUIDUtils.extract_uuids_from_instance(config, uuids)
        return uuids

    @staticmethod
    def extract_microcontroller_point_uuids(config: MicrocontrollerConfig) -> Set[str]:
        uuids: Set[str] = set()
        UUIDUtils.extract_uuids_from_instance(config, uuids)
        return uuids

    @staticmethod
    def extract_governor_point_uuids(config: GovernorConfig) -> Set[str]:
        uuids: Set[str] = set()
        UUIDUtils.extract_uuids_from_instance(config, uuids)
        return uuids


