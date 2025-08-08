#ifndef DHT22_SENSOR_POINT_H
#define DHT22_SENSOR_POINT_H

#include "SensorPoint.h"
#include "SensorReadTimes.h"
#include "SensorConfigs.h"  // For DHT22Config struct (now in same directory)
#include <DHT.h>  // DHT sensor library

class DHT22SensorPoint : public SensorPoint {
private:
    DHT _dht;
    uint8_t _pin;
    bool _convertToFahrenheit;
    const char* _sensorType = "DHT22";  // Reduce repetition
    
    // Topics and UUIDs for this specific sensor instance
    const char* _temperatureTopic;
    const char* _temperatureUUID;
    const char* _humidityTopic;  
    const char* _humidityUUID;
    
    // Last successful readings with timestamp
    float _lastTemperatureC;
    float _lastHumidity;
    String _lastReadTimestamp;  // Timestamp when reading was taken
    bool _hasValidReading;
    
public:
    DHT22SensorPoint(const DHT22Config& config)
        : SensorPoint(DHT22_READ_TIME_MS, config.publish_interval_ms, config.main_loop_delay_ms, config.max_time_no_publish_ms, config.point_name)
        , _dht(config.pin, DHT22)
        , _pin(config.pin)
        , _convertToFahrenheit(config.c_to_f)
        , _temperatureTopic(config.temp_topic)
        , _temperatureUUID(config.temp_uuid)
        , _humidityTopic(config.humidity_topic)
        , _humidityUUID(config.humidity_uuid)
        , _lastTemperatureC(0.0)
        , _lastHumidity(0.0)
        , _hasValidReading(false) {}
    
    bool initialize() override {
        _dht.begin();
        Serial.print(_sensorType);
        Serial.print(" initialized on pin ");
        Serial.println(_pin);
        return true;  // DHT.begin() doesn't return success/failure
    }
    
    bool read(const String& timestamp) override {
        float humidity = _dht.readHumidity();
        float tempC = _dht.readTemperature();
        
        // Check for NaN values (sensor error)
        if (isnan(tempC) || isnan(humidity)) {
            Serial.print(_sensorType);
            Serial.println(" read failed - NaN values (check wiring/power)");
            _hasValidReading = false;
            return false;
        }
        
        // Store successful readings with provided timestamp
        _lastTemperatureC = tempC;
        _lastHumidity = humidity;
        _lastReadTimestamp = timestamp;
        _hasValidReading = true;
        
        Serial.print(_sensorType);
        Serial.print(" read: ");
        Serial.print(tempC);
        Serial.print("°C, ");
        Serial.print(humidity);
        Serial.print("% RH at ");
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
        
        return readings;
    }
};

#endif // DHT22_SENSOR_POINT_H 