import polars as pl
from influxdb_client.client.influxdb_client import InfluxDBClient
from datetime import datetime, timedelta

# InfluxDB connection parameters
url = "http://localhost:8086"
token = "YOUR_TOKEN_HERE"  # You'll need to get this from your InfluxDB UI
org = "mush"
bucket = "bucket"

def fetch_data(measurement, start_time=None, stop_time=None):
    """
    Fetch data from InfluxDB and convert to Polars DataFrame
    
    Args:
        measurement (str): Name of the measurement to query
        start_time (datetime, optional): Start time for the query
        stop_time (datetime, optional): End time for the query
    """
    if start_time is None:
        start_time = datetime.now() - timedelta(days=1)  # Last 24 hours by default
    if stop_time is None:
        stop_time = datetime.now()

    # Initialize the InfluxDB client
    client = InfluxDBClient(url=url, token=token, org=org)
    query_api = client.query_api()

    # Construct the Flux query
    query = f'''
    from(bucket: "{bucket}")
        |> range(start: {start_time.isoformat()}, stop: {stop_time.isoformat()})
        |> filter(fn: (r) => r["_measurement"] == "{measurement}")
    '''
    
    # Execute the query
    result = query_api.query(query)
    
    # Convert to a list of dictionaries
    records = []
    for table in result:
        for record in table.records:
            records.append({
                'time': record.get_time(),
                'measurement': record.get_measurement(),
                'field': record.get_field(),
                'value': record.get_value(),
                **record.values
            })
    
    # Convert to Polars DataFrame
    if records:
        df = pl.DataFrame(records)
        return df
    else:
        return pl.DataFrame()

def list_measurements():
    """List all available measurements in the bucket"""
    client = InfluxDBClient(url=url, token=token, org=org)
    query_api = client.query_api()
    
    query = f'''
    import "influxdata/influxdb/schema"
    schema.measurements(bucket: "{bucket}")
    '''
    
    result = query_api.query(query)
    measurements = [record.values["_value"] for table in result for record in table]
    return measurements

def main():
    # First list available measurements
    print("Available measurements:")
    print(list_measurements())
    
    # Example usage
    # Replace 'your_measurement' with the actual measurement name from your data
    df = fetch_data('your_measurement')
    
    if not df.is_empty():
        print("Data Summary:")
        print(df.head())
        
        # Example analysis
        print("\nBasic Statistics:")
        print(df.describe())
    else:
        print("No data found")

if __name__ == "__main__":
    main() 