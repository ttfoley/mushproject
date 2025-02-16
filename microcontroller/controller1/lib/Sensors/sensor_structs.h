#ifndef SENSOR_STRUCTS_H
#define SENSOR_STRUCTS_H

#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_SHT31.h>
#include <SparkFun_SCD4x_Arduino_Library.h>
#include <DHT.h>
#include "calibration.h"
#include "utils.h"

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
    static const int READ_DELAY_MS = 100;
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
    virtual bool hasHumidity() { return false; }
    virtual bool hasTemperature() { return false; }
    virtual bool hasCO2() { return false; }
    virtual float readHumidity() { return 0.0; }
    virtual float readTemperature() { return 0.0; }
    virtual float readCO2() { return 0.0; }
    virtual const char* getHumidityTopic() = 0;
    virtual const char* getTemperatureTopic() = 0;
    virtual const char* getCO2Topic() { return nullptr; }

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

    bool hasHumidity() override { return true; }
    bool hasTemperature() override { return true; }

    float readHumidity() override {
        return sht31.readHumidity() * humidity_slope + humidity_offset;
    }

    float readTemperature() override {
        return celsiusToFahrenheit(sht31.readTemperature()) * temperature_slope + temperature_offset;
    }

    const char* getHumidityTopic() override {
        return humidity_topic;
    }

    const char* getTemperatureTopic() override {
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

    bool hasHumidity() override { return true; }
    bool hasTemperature() override { return true; }

    float readHumidity() override {
        return dht.readHumidity() * humidity_slope + humidity_offset;
    }

    float readTemperature() override {
        return celsiusToFahrenheit(dht.readTemperature()) * temperature_slope + temperature_offset;
    }

    const char* getHumidityTopic() override {
        return humidity_topic;
    }

    const char* getTemperatureTopic() override {
        return temperature_topic;
    }

    SensorType getType() const override { return SensorType::DHT; }

    const char* getTypeString() const override { return "DHT"; }
};

class SCDSensor : public Sensor {
private:
    SCD4x scd4x;
    char humidity_topic[64];
    char temperature_topic[64];
    char co2_topic[64];
    bool is_measuring = false;
    unsigned long measure_start_time = 0;
    static const unsigned long MEASURE_TIME = 5000; // 5 seconds

public:
    SCDSensor(const char* root_topic, const CalibrationParams& params)
        : Sensor(root_topic, params), scd4x() {
        snprintf(humidity_topic, sizeof(humidity_topic), "%shumidity", root_topic);
        snprintf(temperature_topic, sizeof(temperature_topic), "%stemperature", root_topic);
        snprintf(co2_topic, sizeof(co2_topic), "%sco2", root_topic);
    }

    bool begin() override {
        return scd4x.begin();
    }

    bool hasHumidity() override { return true; }
    bool hasTemperature() override { return true; }
    bool hasCO2() override { return true; }

    float readHumidity() override {
        return scd4x.getHumidity() * humidity_slope + humidity_offset;
    }

    float readTemperature() override {
        return celsiusToFahrenheit(scd4x.getTemperature()) * temperature_slope + temperature_offset;
    }

    float readCO2() override {
        return scd4x.getCO2() * co2_slope + co2_offset;
    }

    const char* getHumidityTopic() override {
        return humidity_topic;
    }

    const char* getTemperatureTopic() override {
        return temperature_topic;
    }

    const char* getCO2Topic() override {
        return co2_topic;
    }

    void startMeasurement() {
        scd4x.measureSingleShot();  // Start actual SCD measurement
        is_measuring = true;
        measure_start_time = millis();
    }

    bool isMeasuring() {
        if (!is_measuring) return false;
        
        if (millis() - measure_start_time >= MEASURE_TIME) {
            is_measuring = false;  // Measurement complete
            return false;
        }
        return true;
    }

    void completeMeasurement() {
        is_measuring = false;
    }

    SensorType getType() const override { return SensorType::SCD; }

    const char* getTypeString() const override { return "SCD"; }
};

#endif // SENSOR_STRUCTS_H