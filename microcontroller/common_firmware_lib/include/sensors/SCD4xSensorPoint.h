#ifndef SCD4X_SENSOR_POINT_H
#define SCD4X_SENSOR_POINT_H

#include "SensorPoint.h"
#include "SensorReadTimes.h"
#include "SensorConfigs.h"  // For SCD4xConfig struct
#include <SensirionI2CScd4x.h>  // SCD4x library
#include <Wire.h>

class SCD4xSensorPoint : public SensorPoint {
private:
    SensirionI2CScd4x _scd4x;
    uint8_t _i2cAddress;
    bool _convertToFahrenheit;
    const char* _sensorType = "SCD4x";  // Reduce repetition
    
    // Topics and UUIDs for this specific sensor instance
    const char* _co2Topic;
    const char* _co2UUID;
    const char* _temperatureTopic;
    const char* _temperatureUUID;
    const char* _humidityTopic;  
    const char* _humidityUUID;
    
    // Last successful readings with timestamp
    uint16_t _lastCO2;
    float _lastTemperatureC;
    float _lastHumidity;
    String _lastReadTimestamp;  // Timestamp when reading was taken
    bool _hasValidReading;
    
    // SCD4x specific timing constants (using values from SensorReadTimes.h)
    static const unsigned long SCD4X_WIRE_END_DELAY_MS = 100;           // Delay after Wire.end()
    static const unsigned long SCD4X_WIRE_SETUP_DELAY_MS = 100;         // Delay after Wire.begin() and setClock()
    static const unsigned long SCD4X_SENSOR_INIT_DELAY_MS = 1000;       // Delay after scd4x.begin()
    static const unsigned long SCD4X_CONFIG_DELAY_MS = 500;             // Delay between configuration commands
    static const unsigned long SCD4X_ADDITIONAL_DELAY_MS = 2000;        // Conservative delay after measurement
    
    // Total calculated timing (I2C reset + actual sensor requirements + safety margins)
    static const unsigned long SCD4X_I2C_RESET_TIME_MS = SCD4X_WIRE_END_DELAY_MS + 
                                                          SCD4X_WIRE_SETUP_DELAY_MS + 
                                                          SCD4X_SENSOR_INIT_DELAY_MS;  // 1200ms
    static const unsigned long SCD4X_TOTAL_READ_TIME_MS = SCD4X_I2C_RESET_TIME_MS + 
                                                          SCD4X_ADDITIONAL_DELAY_MS + 
                                                          SCD41_READ_TIME_MS; // 1200 + 5000 + 2000 + 100 = 8300ms
    
public:
    SCD4xSensorPoint(const SCD4xConfig& config)
        : SensorPoint(SCD4X_TOTAL_READ_TIME_MS, config.publish_interval_ms, config.main_loop_delay_ms, config.max_time_no_publish_ms, config.point_name)  // Use actual calculated read time
        , _i2cAddress(config.address)
        , _convertToFahrenheit(config.c_to_f)
        , _co2Topic(config.co2_topic)
        , _co2UUID(config.co2_uuid)
        , _temperatureTopic(config.temp_topic)
        , _temperatureUUID(config.temp_uuid)
        , _humidityTopic(config.humidity_topic)
        , _humidityUUID(config.humidity_uuid)
        , _lastCO2(0)
        , _lastTemperatureC(0.0)
        , _lastHumidity(0.0)
        , _hasValidReading(false) {}
    
    bool initialize() override {
        Serial.print("Initializing ");
        Serial.print(_sensorType);
        Serial.print(" at address 0x");
        Serial.println(_i2cAddress, HEX);
        
        // Test I2C communication first (like the old working code)
        Serial.println("Testing I2C communication...");
        Wire.beginTransmission(_i2cAddress);
        byte error = Wire.endTransmission();
        
        if (error == 0) {
            Serial.print("Found device at 0x");
            Serial.println(_i2cAddress, HEX);
        } else {
            Serial.print("No device at 0x");
            Serial.print(_i2cAddress, HEX);
            Serial.print(", error: ");
            Serial.println(error);
            return false;
        }
        
        delay(SCD4X_SENSOR_INIT_DELAY_MS);
        
        // Initialize sensor (basic setup, no I2C reset during init)
        _scd4x.begin(Wire);
        delay(SCD4X_SENSOR_INIT_DELAY_MS);
        
        // Configure sensor settings
        if (!initializeSensorConfiguration()) {
            Serial.print(_sensorType);
            Serial.println(" sensor configuration failed");
            return false;
        }
        
        Serial.print(_sensorType);
        Serial.println(" initialized successfully");
        return true;
    }
    
    bool read(const String& timestamp) override {
        Serial.print(_sensorType);
        Serial.println(" starting read sequence...");
        
        // Reset I2C before every read (critical for reliability)
        if (!resetI2CBus()) {
            Serial.print(_sensorType);
            Serial.println(" I2C reset failed during read");
            _hasValidReading = false;
            return false;
        }
        
        // Start single-shot measurement (this is BLOCKING for ~5 seconds)
        Serial.print(_sensorType);
        Serial.println(" starting single-shot measurement (5s blocking)...");
        uint16_t error = _scd4x.measureSingleShot();
        if (error) {
            Serial.print(_sensorType);
            Serial.print(" measureSingleShot failed, error: ");
            Serial.println(error);
            _hasValidReading = false;
            return false;
        }
        
        // Conservative additional delay after single-shot measurement
        delay(SCD4X_ADDITIONAL_DELAY_MS);
        
        // Read the measurement
        uint16_t co2;
        float temperature;
        float humidity;
        
        error = _scd4x.readMeasurement(co2, temperature, humidity);
        if (error) {
            Serial.print(_sensorType);
            Serial.print(" readMeasurement failed, error: ");
            Serial.println(error);
            _hasValidReading = false;
            return false;
        }
        
        // Check for invalid readings (CO2 = 0 often indicates sensor error)
        if (co2 == 0) {
            Serial.print(_sensorType);
            Serial.println(" invalid CO2 reading (0 ppm)");
            _hasValidReading = false;
            return false;
        }
        
        // Check for NaN values in temperature/humidity
        if (isnan(temperature) || isnan(humidity)) {
            Serial.print(_sensorType);
            Serial.println(" NaN values in temperature or humidity");
            _hasValidReading = false;
            return false;
        }
        
        // Store successful readings with provided timestamp
        _lastCO2 = co2;
        _lastTemperatureC = temperature;
        _lastHumidity = humidity;
        _lastReadTimestamp = timestamp;
        _hasValidReading = true;
        
        Serial.print(_sensorType);
        Serial.print(" read successful: ");
        Serial.print(co2);
        Serial.print(" ppm, ");
        Serial.print(temperature);
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
        
        // CO2 reading (ppm)
        readings.emplace_back(_co2Topic, String(_lastCO2), timestamp, _co2UUID);
        
        // Temperature reading (convert if needed)
        float tempValue = _convertToFahrenheit ? 
            (_lastTemperatureC * 9.0f / 5.0f + 32.0f) : _lastTemperatureC;
        readings.emplace_back(_temperatureTopic, String(tempValue, 2), timestamp, _temperatureUUID);
        
        // Humidity reading
        readings.emplace_back(_humidityTopic, String(_lastHumidity, 2), timestamp, _humidityUUID);
        
        return readings;
    }

private:
    bool resetI2CBus() {
        // Critical I2C reset sequence for SCD4x reliability
        Wire.end();
        delay(SCD4X_WIRE_END_DELAY_MS);
        
        // Use I2C pins from autogen_config.h instead of hardcoding
        #ifdef I2C_SDA_PIN
        #ifdef I2C_SCL_PIN
            Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
        #else
            Wire.begin(I2C_SDA_PIN, 22);  // Fallback SCL
        #endif
        #else
            Wire.begin(21, 22);  // Fallback to standard ESP32 pins
        #endif
        
        Wire.setClock(100000);  // 100kHz for reliability with SCD4x
        delay(SCD4X_WIRE_SETUP_DELAY_MS);
        
        // Re-initialize sensor after I2C reset
        _scd4x.begin(Wire);
        delay(SCD4X_SENSOR_INIT_DELAY_MS);
        
        return true;
    }
    
    bool initializeSensorConfiguration() {
        uint16_t error;
        
        // Stop any periodic measurement that might be running
        error = _scd4x.stopPeriodicMeasurement();
        if (error) {
            Serial.print(_sensorType);
            Serial.print(" failed to stop periodic measurement, error: ");
            Serial.println(error);
            return false;
        }
        delay(SCD4X_CONFIG_DELAY_MS);
        
        // Disable automatic self-calibration for consistent readings
        error = _scd4x.setAutomaticSelfCalibration(false);
        if (error) {
            Serial.print(_sensorType);
            Serial.print(" failed to disable auto-calibration, error: ");
            Serial.println(error);
            return false;
        }
        delay(SCD4X_CONFIG_DELAY_MS);
        
        return true;
    }
};

#endif // SCD4X_SENSOR_POINT_H 