import pandas as pd

from influxdb_client import InfluxDBClient, Point, WriteOptions

# Create a sample DataFrame
data = {
    'time': pd.date_range(start='2025-01-01', periods=5, freq='D'),
    'value': [10, 20, 30, 40, 50]
}
df = pd.DataFrame(data)

# Set up InfluxDB client
token = "token"
org = "docs"
bucket = "home"
url = "http://localhost:8086"

client = InfluxDBClient(url=url, token=token, org=org)
write_api = client.write_api(write_options=WriteOptions(batch_size=1))

# Write DataFrame to InfluxDB
for index, row in df.iterrows():
    point = Point("my_measurement").tag("location", "Prague").field("value", row['value']).time(index)
    write_api.write(bucket=bucket, org=org, record=point)

print("Data written to InfluxDB successfully.")