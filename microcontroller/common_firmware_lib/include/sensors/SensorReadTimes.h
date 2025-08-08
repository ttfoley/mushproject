#ifndef SENSOR_READ_TIMES_H
#define SENSOR_READ_TIMES_H

// Minimum time to wait between sensor read attempts (milliseconds)
// These values are optimized based on actual communication timing, not internal sensor intervals
// NOTE: All timing estimates assume 100kHz I2C clock speed (ESP32 default)

// === Digital I2C Sensors ===
#define SHT85_READ_TIME_MS 43      // SHT85: I2C communication ~5-10ms (not measurement time)
#define BME280_READ_TIME_MS 4     // BME280: Very fast sensor, can handle frequent reads  

// === Digital Pin Sensors ===
#define DHT22_READ_TIME_MS 8      // DHT22: 5ms communication time + safety margin
#define DS18B20_READ_TIME_MS 63    // DS18B20: Actual read time ~5-10ms (not conversion time)

// Special sensors (for controller3)
#define SCD41_READ_TIME_MS 5000  // SCD41 measureSingleShot() blocking time

// Default fallback
#define DEFAULT_SENSOR_READ_TIME_MS 500


#endif // SENSOR_READ_TIMES_H 