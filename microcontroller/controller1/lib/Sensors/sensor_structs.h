#ifndef SENSOR_STRUCTS_H
#define SENSOR_STRUCTS_H

#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_SHT31.h>
#include <SparkFun_SCD4x_Arduino_Library.h>
#include <DHT.h>
#include "calibration.h"
#include "utils.h"

class Sensor {
protected:
    unsigned long time_last_published;
    float humidity_slope;
    float humidity_offset;
    float temperature_slope;
    float temperature_offset;
    float co2_slope;
    float co2_offset;

public:
    Sensor(const CalibrationParams& params)
        : time_last_published(0), humidity_slope(params.humidity_slope), humidity_offset(params.humidity_offset),
          temperature_slope(params.temperature_slope), temperature_offset(params.temperature_offset),
          co2_slope(params.co2_slope), co2_offset(params.co2_offset) {}

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
};

// Derived classes for specific sensors
class SHTSensor : public Sensor {
private:
    Adafruit_SHT31 sht31;
    uint8_t addr;
    const char* humidity_topic;
    const char* temperature_topic;

public:
    SHTSensor(uint8_t addr, const char* humidity_topic, const char* temperature_topic, const CalibrationParams& params)
        : Sensor(params), sht31(), addr(addr), humidity_topic(humidity_topic), temperature_topic(temperature_topic) {}
    bool begin() override {
        return sht31.begin(addr); // replace 0x44 with the actual address if different
    }

    bool hasHumidity() override { return true; }
    bool hasTemperature() override { return true; }

    float readHumidity() override {
        return sht31.readHumidity() * humidity_slope + humidity_offset;
    }

    float readTemperature() override {
        return sht31.readTemperature() * temperature_slope + temperature_offset;
    }

    const char* getHumidityTopic() override {
        return humidity_topic;
    }

    const char* getTemperatureTopic() override {
        return temperature_topic;
    }
};

class DHTSensor : public Sensor {
private:
    DHT dht;

public:
    DHTSensor(uint8_t pin, uint8_t type, const char* humidity_topic, const char* temperature_topic, const CalibrationParams& params)
        : Sensor(params), dht(pin, type), humidity_topic(humidity_topic), temperature_topic(temperature_topic) {}

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
        return dht.readTemperature() * temperature_slope + temperature_offset;
    }

    const char* getHumidityTopic() override {
        return humidity_topic;
    }

    const char* getTemperatureTopic() override {
        return temperature_topic;
    }

private:
    const char* humidity_topic;
    const char* temperature_topic;
};

class SCDSensor : public Sensor {
private:
    SCD4x scd4x;

public:
    SCDSensor(const char* humidity_topic, const char* temperature_topic, const char* co2_topic, const CalibrationParams& params)
        : Sensor(params), scd4x(), humidity_topic(humidity_topic), temperature_topic(temperature_topic), co2_topic(co2_topic) {}

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
        return scd4x.getTemperature() * temperature_slope + temperature_offset;
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

private:
    const char* humidity_topic;
    const char* temperature_topic;
    const char* co2_topic;
};

#endif // SENSOR_STRUCTS_H