#ifndef SHT85_SENSOR_POINT_H
#define SHT85_SENSOR_POINT_H

#include "SensorPoint.h"
#include "SensorReadTimes.h"
#include <Adafruit_SHT31.h>  // Using SHT31 library for SHT85 (compatible)

class SHT85SensorPoint : public SensorPoint {
private:
    Adafruit_SHT31 _sht85;
    uint8_t _i2cAddress;
    bool _convertToFahrenheit;
    const char* _sensorType = "SHT85";  // Reduce repetition
    
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
    SHT85SensorPoint(uint8_t i2cAddress, 
                     bool convertToFahrenheit,
                     const char* temperatureTopic,
                     const char* temperatureUUID,
                     const char* humidityTopic,
                     const char* humidityUUID,
                     unsigned long publishIntervalMs,
                     unsigned long mainLoopDelayMs)
        : SensorPoint(SHT85_READ_TIME_MS, publishIntervalMs, mainLoopDelayMs)
        , _i2cAddress(i2cAddress)
        , _convertToFahrenheit(convertToFahrenheit)
        , _temperatureTopic(temperatureTopic)
        , _temperatureUUID(temperatureUUID)
        , _humidityTopic(humidityTopic)
        , _humidityUUID(humidityUUID)
        , _lastTemperatureC(0.0)
        , _lastHumidity(0.0)
        , _hasValidReading(false) {}
    
    bool initialize() override {
        if (!_sht85.begin(_i2cAddress)) {
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
        float tempC = _sht85.readTemperature();
        float humidity = _sht85.readHumidity();
        
        // Check for NaN values (sensor error)
        if (isnan(tempC) || isnan(humidity)) {
            Serial.print(_sensorType);
            Serial.println(" read failed - NaN values");
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

#endif // SHT85_SENSOR_POINT_H 