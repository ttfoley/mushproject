from pathlib import Path
import shutil
from datetime import date

from mushbuild.validation.ssot import SSOTValidator
from mushbuild.validation.components import ComponentConfigValidator
from mushbuild.validation.cross import CrossValidator
from mushbuild.utils.topics import TopicGenerator  # noqa: F401 (used by generators)
from mushbuild.generators.points_registry import PointsRegistryGenerator
# Use the existing generator implementation to avoid unnecessary diffs
from mushbuild.generators.microcontrollers import MicrocontrollerConfigGenerator

from shared_libs.config_models.secrets import InfrastructureSecrets

import yaml


def load_infrastructure_with_secrets(config_base_dir: Path) -> tuple[dict, InfrastructureSecrets]:
    infra_path = config_base_dir / "infrastructure_definition.yaml"
    infrastructure = {}
    if infra_path.exists():
        with open(infra_path) as f:
            infrastructure = yaml.safe_load(f) or {}

    project_root = config_base_dir.parent
    secrets_path = project_root / "secrets" / "infrastructure_secrets.yaml"
    with open(secrets_path) as f:
        secrets_raw = yaml.safe_load(f) or {}

    if isinstance(secrets_raw, dict) and (
        'WIFI_SSID' in secrets_raw or 'MQTT_BROKER_ADDRESS' in secrets_raw
    ):
        secrets_converted = {
            'wifi': {
                'default': {
                    'ssid': secrets_raw.get('WIFI_SSID', ''),
                    'password': secrets_raw.get('WIFI_PASSWORD', ''),
                },
                'per_device': {}
            },
            'mqtt': {
                'default': {
                    'broker_address': secrets_raw.get('MQTT_BROKER_ADDRESS', ''),
                    'broker_port': secrets_raw.get('MQTT_BROKER_PORT', 1883),
                    'username': secrets_raw.get('MQTT_USERNAME', ''),
                    'password': secrets_raw.get('MQTT_PASSWORD', ''),
                },
                'per_device': {}
            }
        }
    else:
        secrets_converted = secrets_raw

    secrets_model = InfrastructureSecrets.model_validate(secrets_converted)
    return infrastructure, secrets_model


def main():
    config_base_dir = Path(__file__).parent.parent / "config_sources"
    ssot_file = config_base_dir / "system_definition.yaml"
    points_out = Path(__file__).parent.parent / "artifacts" / "points_registry" / "global_points_registry.json"
    micros_out_dir = config_base_dir / "microcontrollers" / "generated"

    infra, secrets_model = load_infrastructure_with_secrets(config_base_dir)
    ssot = SSOTValidator(ssot_file).validate()
    if ssot is None:
        raise SystemExit(1)

    points_by_uuid_map = {p.uuid: p for p in ssot.points}
    components_ok, validated = ComponentConfigValidator(ssot, config_base_dir, infra, secrets_model).validate(points_by_uuid_map)
    if not components_ok:
        raise SystemExit(1)

    if not CrossValidator(ssot).validate(validated):
        raise SystemExit(1)

    # Ensure output directory exists
    points_out.parent.mkdir(parents=True, exist_ok=True)
    PointsRegistryGenerator(ssot, points_out).generate()

    # Also write a dated copy under artifacts/points_registry/YYYY-MM-DD/
    dated_dir = points_out.parent / date.today().isoformat()
    dated_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(points_out, dated_dir / points_out.name)

    # Generate headers for all micros
    MicrocontrollerConfigGenerator(ssot, micros_out_dir).generate(validated)


if __name__ == "__main__":
    main()
