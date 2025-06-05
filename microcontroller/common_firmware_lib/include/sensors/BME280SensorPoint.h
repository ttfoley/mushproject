#ifndef BME280_SENSOR_POINT_H
#define BME280_SENSOR_POINT_H

#include "SensorPoint.h"
#include "SensorReadTimes.h"
#include "SensorConfigs.h"  // For BME280Config struct (now in same directory)
#include <Adafruit_BME280.h>

class BME280SensorPoint : public SensorPoint {
private:
    Adafruit_BME280 _bme280;
    uint8_t _i2cAddress;
    bool _convertToFahrenheit;
    const char* _sensorType = "BME280";
    
    // Topics and UUIDs for this specific sensor instance
    const char* _temperatureTopic;
    const char* _temperatureUUID;
    const char* _humidityTopic;  
    const char* _humidityUUID;
    const char* _pressureTopic;
    const char* _pressureUUID;
    
    // Last successful readings with timestamp
    float _lastTemperatureC;
    float _lastHumidity;
    float _lastPressurePa;  // Pressure in Pascals
    String _lastReadTimestamp;  // Timestamp when reading was taken
    bool _hasValidReading;
    
public:
    BME280SensorPoint(const BME280Config& config)
        : SensorPoint(BME280_READ_TIME_MS, config.publish_interval_ms, config.main_loop_delay_ms, config.max_time_no_publish_ms, config.point_name)
        , _i2cAddress(config.address)
        , _convertToFahrenheit(config.c_to_f)
        , _temperatureTopic(config.temp_topic)
        , _temperatureUUID(config.temp_uuid)
        , _humidityTopic(config.humidity_topic)
        , _humidityUUID(config.humidity_uuid)
        , _pressureTopic(config.pressure_topic)
        , _pressureUUID(config.pressure_uuid)
        , _lastTemperatureC(0.0)
        , _lastHumidity(0.0)
        , _lastPressurePa(0.0)
        , _hasValidReading(false) {}
    
    bool initialize() override {
        if (!_bme280.begin(_i2cAddress)) {
            Serial.print("Failed to initialize ");
            Serial.print(_sensorType);
            Serial.print(" at address 0x");
            Serial.println(_i2cAddress, HEX);
            return false;
        } else {
            Serial.print(_sensorType);
            Serial.print(" initialized at address 0x");
            Serial.println(_i2cAddress, HEX);
            return true;
        }
    }
    
    bool read(const String& timestamp) override {
        float tempC = _bme280.readTemperature();
        float humidity = _bme280.readHumidity();
        float pressurePa = _bme280.readPressure();  // Returns pressure in Pascals
        
        // Check for NaN values (sensor error)
        if (isnan(tempC) || isnan(humidity) || isnan(pressurePa)) {
            Serial.print(_sensorType);
            Serial.println(" read failed - NaN values");
            _hasValidReading = false;
            return false;
        }
        
        // Store successful readings with provided timestamp
        _lastTemperatureC = tempC;
        _lastHumidity = humidity;
        _lastPressurePa = pressurePa;
        _lastReadTimestamp = timestamp;
        _hasValidReading = true;
        
        Serial.print(_sensorType);
        Serial.print(" read: ");
        Serial.print(tempC);
        Serial.print("°C, ");
        Serial.print(humidity);
        Serial.print("% RH, ");
        Serial.print(pressurePa);
        Serial.print(" Pa at ");
        Serial.println(timestamp);
        
        return true;
    }
    
    std::vector<SensorReading> getAllReadings() override {
        std::vector<SensorReading> readings;
        
        if (!_hasValidReading) {
            Serial.print(_sensorType);
            Serial.println(": No valid reading available");
            return readings;  // Return empty vector
        }
        
        // Use the timestamp from when the reading was actually taken
        String timestamp = _lastReadTimestamp;
        
        // Temperature reading
        float tempValue = _convertToFahrenheit ? 
            (_lastTemperatureC * 9.0f / 5.0f + 32.0f) : _lastTemperatureC;
        readings.emplace_back(_temperatureTopic, String(tempValue, 2), timestamp, _temperatureUUID);
        
        // Humidity reading
        readings.emplace_back(_humidityTopic, String(_lastHumidity, 2), timestamp, _humidityUUID);
        
        // Pressure reading (always in Pascals as per config)
        readings.emplace_back(_pressureTopic, String(_lastPressurePa, 2), timestamp, _pressureUUID);
        
        return readings;
    }
};

#endif // BME280_SENSOR_POINT_H 