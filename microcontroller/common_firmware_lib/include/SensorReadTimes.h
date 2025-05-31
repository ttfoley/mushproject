#ifndef SENSOR_READ_TIMES_H
#define SENSOR_READ_TIMES_H

// Sensor read timing constants (in milliseconds)
// These represent the minimum time between read attempts to avoid overwhelming sensors

// I2C Sensors
#define SHT85_READ_TIME_MS 500      // SHT85 temperature/humidity sensor
#define BME280_READ_TIME_MS 500     // BME280 temperature/humidity/pressure sensor

// DHT Sensors  
#define DHT22_READ_TIME_MS 500      // DHT22 temperature/humidity sensor (actual ~250ms but being safe)

// OneWire Sensors
#define DS18B20_READ_TIME_MS 500    // DS18B20 temperature sensor

// Special sensors (for controller3)
#define SCD41_READ_TIME_MS 5000     // SCD41 CO2/temperature/humidity sensor (very slow)

// Default fallback
#define DEFAULT_SENSOR_READ_TIME_MS 500

#endif // SENSOR_READ_TIMES_H 