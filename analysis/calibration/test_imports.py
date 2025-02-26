# Test our imports
import polars as pl
from influxdb_client.client.influxdb_client import InfluxDBClient
from influxdb_client import __version__ as influxdb_version

print(f"Polars version: {pl.__version__}")
print(f"InfluxDB Client version: {influxdb_version}") 