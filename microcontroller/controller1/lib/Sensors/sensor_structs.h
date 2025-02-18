#ifndef SENSOR_STRUCTS_H
#define SENSOR_STRUCTS_H

#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_SHT31.h>
#include <SparkFun_SCD4x_Arduino_Library.h>
#include <DHT.h>
#include "calibration.h"
#include "utils.h"
#include <DallasTemperature.h>
#include "SensirionI2CScd4x.h"
#include "timing_constants.h"

enum class SensorType {
    DHT,
    SHT,
    SCD,
    DS18B20
};

class Sensor {
protected:
    unsigned long time_last_published;
    float humidity_slope;
    float humidity_offset;
    float temperature_slope;
    float temperature_offset;
    float co2_slope;
    float co2_offset;
    static const unsigned long readDelayMs = READ_DELAY_MS;
    unsigned long publish_frequency = 15000;  // Default 15s
    const char* root_topic;  // Store the root topic path

public:
    Sensor(const char* root_topic, const CalibrationParams& params)
        : time_last_published(0), humidity_slope(params.humidity_slope), 
          humidity_offset(params.humidity_offset),
          temperature_slope(params.temperature_slope), 
          temperature_offset(params.temperature_offset),
          co2_slope(params.co2_slope), co2_offset(params.co2_offset),
          root_topic(root_topic) {}

    virtual bool begin() = 0;
    virtual bool hasHumidity() const { return false; }
    virtual bool hasTemperature() const { return false; }
    virtual bool hasCO2() const { return false; }
    virtual float readHumidity() { return 0.0; }
    virtual float readTemperature() { return 0.0; }
    virtual float readCO2() { return 0.0; }
    virtual const char* getHumidityTopic() const = 0;
    virtual const char* getTemperatureTopic() const = 0;
    virtual const char* getCO2Topic() const { return nullptr; }

    void resetTimeLastPublished() {
        time_last_published = millis();
    }

    unsigned long getTimeLastPublished() {
        return time_last_published;
    }

    // Add getter/setter for publish frequency
    void setPublishFrequency(unsigned long freq) {
        publish_frequency = freq;
    }
    
    unsigned long getPublishFrequency() {
        return publish_frequency;
    }

    // Add method to get sensor name for logging
    const char* getRootTopic() {
        return root_topic;
    }

    virtual SensorType getType() const = 0;
    
    const char* getName() const {
        const char* sensor_part = strstr(root_topic, "sensors/");
        if (sensor_part) {
            sensor_part += 8; // Skip "sensors/"
            static char name[32]; // Static buffer to hold the name
            const char* end = strchr(sensor_part, '/');
            if (end) {
                size_t len = end - sensor_part;
                strncpy(name, sensor_part, len);
                name[len] = '\0';
                return name;
            }
        }
        return "unknown";
    }

    virtual const char* getTypeString() const = 0;

    enum class MeasurementType {
        TEMPERATURE,
        HUMIDITY,
        CO2
    };

    virtual bool hasMeasurement(MeasurementType type) const {
        switch(type) {
            case MeasurementType::TEMPERATURE: return hasTemperature();
            case MeasurementType::HUMIDITY: return hasHumidity();
            case MeasurementType::CO2: return hasCO2();
            default: return false;
        }
    }

    virtual float read(MeasurementType type) {
        switch(type) {
            case MeasurementType::TEMPERATURE: return readTemperature();
            case MeasurementType::HUMIDITY: return readHumidity();
            case MeasurementType::CO2: return readCO2();
            default: return 0.0;
        }
    }

    virtual const char* getTopic(MeasurementType type) const {
        switch(type) {
            case MeasurementType::TEMPERATURE: return getTemperatureTopic();
            case MeasurementType::HUMIDITY: return getHumidityTopic();
            case MeasurementType::CO2: return getCO2Topic();
            default: return nullptr;
        }
    }

    static const char* getMeasurementTypeName(MeasurementType type) {
        switch(type) {
            case MeasurementType::TEMPERATURE: return "temperature";
            case MeasurementType::HUMIDITY: return "humidity";
            case MeasurementType::CO2: return "CO2";
            default: return "unknown";
        }
    }
};

// Derived classes for specific sensors
class SHTSensor : public Sensor {
private:
    Adafruit_SHT31 sht31;
    uint8_t addr;
    char humidity_topic[64];
    char temperature_topic[64];

public:
    SHTSensor(uint8_t addr, const char* root_topic, const CalibrationParams& params)
        : Sensor(root_topic, params), sht31(), addr(addr) {
        snprintf(humidity_topic, sizeof(humidity_topic), "%shumidity", root_topic);
        snprintf(temperature_topic, sizeof(temperature_topic), "%stemperature", root_topic);
    }
    bool begin() override {
        return sht31.begin(addr); // replace 0x44 with the actual address if different
    }

    bool hasHumidity() const override { return true; }
    bool hasTemperature() const override { return true; }

    float readHumidity() override {
        return sht31.readHumidity() * humidity_slope + humidity_offset;
    }

    float readTemperature() override {
        return celsiusToFahrenheit(sht31.readTemperature()) * temperature_slope + temperature_offset;
    }

    const char* getHumidityTopic() const override {
        return humidity_topic;
    }

    const char* getTemperatureTopic() const override {
        return temperature_topic;
    }

    SensorType getType() const override { return SensorType::SHT; }

    const char* getTypeString() const override { return "SHT"; }
};

class DHTSensor : public Sensor {
private:
    DHT dht;
    char humidity_topic[64];
    char temperature_topic[64];

public:
    DHTSensor(uint8_t pin, uint8_t type, const char* root_topic, const CalibrationParams& params)
        : Sensor(root_topic, params), dht(pin, type) {
        snprintf(humidity_topic, sizeof(humidity_topic), "%shumidity", root_topic);
        snprintf(temperature_topic, sizeof(temperature_topic), "%stemperature", root_topic);
    }

    bool begin() override {
        dht.begin();
        return true;
    }

    bool hasHumidity() const override { return true; }
    bool hasTemperature() const override { return true; }

    float readHumidity() override {
        return dht.readHumidity() * humidity_slope + humidity_offset;
    }

    float readTemperature() override {
        return celsiusToFahrenheit(dht.readTemperature()) * temperature_slope + temperature_offset;
    }

    const char* getHumidityTopic() const override {
        return humidity_topic;
    }

    const char* getTemperatureTopic() const override {
        return temperature_topic;
    }

    SensorType getType() const override { return SensorType::DHT; }

    const char* getTypeString() const override { return "DHT"; }
};

class SCDSensor : public Sensor {
private:
    SensirionI2CScd4x scd4x;
    char humidity_topic[64];
    char temperature_topic[64];
    char co2_topic[64];
    bool is_measuring = false;
    unsigned long measure_start_time = 0;
    static const unsigned long scd_measure_time = MEASURE_TIME;
    uint16_t co2;
    float temperature;
    float humidity;
    bool have_current_reading = false;

public:
    SCDSensor(const char* root_topic, const CalibrationParams& params)
        : Sensor(root_topic, params), scd4x() {
        snprintf(humidity_topic, sizeof(humidity_topic), "%shumidity", root_topic);
        snprintf(temperature_topic, sizeof(temperature_topic), "%stemperature", root_topic);
        snprintf(co2_topic, sizeof(co2_topic), "%sco2", root_topic);
    }

    bool begin() override {
        Serial.print("SCD40: Attempting to begin... ");
        scd4x.begin(Wire);
        delay(1000);
        
        Serial.print("SCD40: Performing factory reset... ");
        uint16_t error = scd4x.performFactoryReset();
        if (error) {
            Serial.print("FAILED (error: 0x");
            Serial.print(error, HEX);
            Serial.println(")");
            return false;
        }
        Serial.println("SUCCESS");

        Serial.print("SCD40: Stopping periodic measurement... ");
        error = scd4x.stopPeriodicMeasurement();
        Serial.println(error ? "FAILED" : "SUCCESS");
        if (error) return false;

        Serial.print("SCD40: Disabling auto-calibration... ");
        error = scd4x.setAutomaticSelfCalibration(0);
        Serial.println(error ? "FAILED" : "SUCCESS");
        return error == 0;
    }

    bool hasHumidity() const override { return true; }
    bool hasTemperature() const override { return true; }
    bool hasCO2() const override { return true; }

    float readHumidity() override {
        if (updateMeasurements()) {
            return humidity * humidity_slope + humidity_offset;
        }
        return 0.0;
    }

    float readTemperature() override {
        if (updateMeasurements()) {
            return celsiusToFahrenheit(temperature) * temperature_slope + temperature_offset;
        }
        return 0.0;
    }

    float readCO2() override {
        if (updateMeasurements()) {
            Serial.print("SCD40 raw CO2: "); Serial.println(co2);
            return co2 * co2_slope + co2_offset;
        }
        return 0.0;
    }

    const char* getHumidityTopic() const override {
        return humidity_topic;
    }

    const char* getTemperatureTopic() const override {
        return temperature_topic;
    }

    const char* getCO2Topic() const override {
        return co2_topic;
    }

    void startMeasurement() {
        Serial.println("SCD40: Starting measurement");
        
        uint16_t error = scd4x.reinit();
        if (error) {
            Serial.print("Error reinitializing: 0x");
            Serial.println(error, HEX);
        }
        
        measure_start_time = millis();
        error = scd4x.measureSingleShot();
        if (error) {
            Serial.print("Error starting measurement: 0x");
            Serial.println(error, HEX);
            set_measuring(false);
        } else {
            set_measuring(true);
            Serial.println("SCD40: Measurement started successfully");
            delay(1000);
        }
    }

    bool isMeasuring() {
        //Serial.println("isMeasuring() called");
        if (!is_measuring) return false;
        
        bool dataReady = false;
        uint16_t error = scd4x.getDataReadyFlag(dataReady);
        if (error) {
            Serial.print("Error checking if done measuring: 0x");
            Serial.println(error, HEX);
            return true;
        }
        
        if (dataReady) {
            unsigned long elapsed = millis() - measure_start_time;
            Serial.print("SCD40: Measurement completed after ");
            Serial.print(elapsed);
            Serial.println("ms");
            set_measuring(false);
            return false;
        }
        return true;//still measuring
    }

    void completeMeasurement() {
        Serial.println("SCD40: Completing measurement");
        set_measuring(false);
        have_current_reading = false;  // Reset for next cycle
    }

    bool getDataReadyFlag() {
        Serial.println("getDataReadyFlag() called");
        bool dataReady = false;
        uint16_t error = scd4x.getDataReadyFlag(dataReady);
        if (error) {
            Serial.print("Error in getDataReadyFlag: 0x");
            Serial.println(error, HEX);
        }
        unsigned long elapsed = millis() - measure_start_time;
        if (elapsed % 1000 == 0) {  // Print every second
            Serial.print("Waiting for data ready: ");
            Serial.print(elapsed);
            Serial.println("ms");
        }
        return !error && dataReady;
    }

    SensorType getType() const override { return SensorType::SCD; }

    const char* getTypeString() const override { return "SCD"; }

private:
    bool updateMeasurements() {
        Serial.println("SCD40: updateMeasurements() called");
        if (!have_current_reading) {
            Serial.println("SCD40: No current reading, checking data ready");
            bool dataReady = false;
            uint16_t error = scd4x.getDataReadyFlag(dataReady);
            if (error) {
                Serial.print("Error checking data ready: 0x");
                Serial.println(error, HEX);
                return false;
            }
            if (!dataReady) {
                Serial.println("Data not ready yet");
                return false;
            }
            error = scd4x.readMeasurement(co2, temperature, humidity);
            if (error) {
                Serial.print("Error reading measurements: 0x");
                Serial.println(error, HEX);
                return false;
            }
            have_current_reading = true;
            Serial.println("SCD40: Successfully read new measurements");
        } else {
            Serial.println("SCD40: Using cached reading");
        }
        return true;
    }

    void set_measuring(bool val) {
        Serial.print("is_measuring changing from ");
        Serial.print(is_measuring);
        Serial.print(" to ");
        Serial.println(val);
        is_measuring = val;
    }
};

class DS18B20Sensor : public Sensor {
private:
    OneWire oneWire;
    DallasTemperature sensor;
    char temperature_topic[64];

public:
    DS18B20Sensor(uint8_t pin, const char* root_topic, const CalibrationParams& params)
        : Sensor(root_topic, params), oneWire(pin), sensor(&oneWire) {
        snprintf(temperature_topic, sizeof(temperature_topic), "%stemperature", root_topic);
    }

    bool begin() override {
        sensor.begin();
        return sensor.getDeviceCount() > 0;
    }

    bool hasTemperature() const override { return true; }

    float readTemperature() override {
        sensor.requestTemperatures();
        float tempC = sensor.getTempCByIndex(0);
        if (tempC == DEVICE_DISCONNECTED_C) return 0.0;
        return celsiusToFahrenheit(tempC) * temperature_slope + temperature_offset;
    }

    const char* getTemperatureTopic() const override {
        return temperature_topic;
    }

    const char* getHumidityTopic() const override {
        return nullptr;
    }

    SensorType getType() const override { return SensorType::DS18B20; }

    const char* getTypeString() const override { return "DS18B20"; }
};

#endif // SENSOR_STRUCTS_H