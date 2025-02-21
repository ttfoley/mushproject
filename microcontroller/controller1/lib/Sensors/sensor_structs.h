#ifndef SENSOR_STRUCTS_H
#define SENSOR_STRUCTS_H

#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_SHT31.h>
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

    virtual bool isDataReady() { return true; }
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