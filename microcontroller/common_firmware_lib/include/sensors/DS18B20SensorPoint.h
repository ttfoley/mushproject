#ifndef DS18B20_SENSOR_POINT_H
#define DS18B20_SENSOR_POINT_H

#include "SensorPoint.h"
#include "SensorReadTimes.h"
#include "../SensorConfigs.h"  // For DS18B20Config struct (up one level)
#include <OneWire.h>
#include <DallasTemperature.h>

class DS18B20SensorPoint : public SensorPoint {
private:
    OneWire _oneWire;
    DallasTemperature _sensors;
    uint8_t _pin;
    bool _convertToFahrenheit;
    const char* _sensorType = "DS18B20";  // Reduce repetition
    
    // Topics and UUIDs for this specific sensor instance
    const char* _temperatureTopic;
    const char* _temperatureUUID;
    
    // Last successful readings with timestamp
    float _lastTemperatureC;
    String _lastReadTimestamp;  // Timestamp when reading was taken
    bool _hasValidReading;
    
public:
    DS18B20SensorPoint(const DS18B20Config& config)
        : SensorPoint(DS18B20_READ_TIME_MS, config.publish_interval_ms, config.main_loop_delay_ms)
        , _oneWire(config.pin)
        , _sensors(&_oneWire)
        , _pin(config.pin)
        , _convertToFahrenheit(config.c_to_f)
        , _temperatureTopic(config.temp_topic)
        , _temperatureUUID(config.temp_uuid)
        , _lastTemperatureC(0.0)
        , _hasValidReading(false) {}
    
    bool initialize() override {
        _sensors.begin();
        
        // Check if any sensors are connected
        int deviceCount = _sensors.getDeviceCount();
        if (deviceCount == 0) {
            Serial.print(_sensorType);
            Serial.print(" initialization failed - no devices found on pin ");
            Serial.println(_pin);
            return false;
        }
        
        Serial.print(_sensorType);
        Serial.print(" initialized on pin ");
        Serial.print(_pin);
        Serial.print(" - found ");
        Serial.print(deviceCount);
        Serial.println(" device(s)");
        
        // Set resolution for better accuracy (9, 10, 11, or 12 bits)
        _sensors.setResolution(12);
        
        return true;
    }
    
    bool read(const String& timestamp) override {
        _sensors.requestTemperatures(); // Request temperature from all devices on the bus
        
        // Read temperature from the first device (index 0)
        float tempC = _sensors.getTempCByIndex(0);
        
        // Check for invalid reading (DEVICE_DISCONNECTED_C = -127.0)
        if (tempC == DEVICE_DISCONNECTED_C || tempC == 85.0) {
            Serial.print(_sensorType);
            Serial.println(" read failed - device disconnected or invalid reading");
            _hasValidReading = false;
            return false;
        }
        
        // Store successful reading with provided timestamp
        _lastTemperatureC = tempC;
        _lastReadTimestamp = timestamp;
        _hasValidReading = true;
        
        Serial.print(_sensorType);
        Serial.print(" read: ");
        Serial.print(tempC);
        Serial.print("°C at ");
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
        
        return readings;
    }
};

#endif // DS18B20_SENSOR_POINT_H 