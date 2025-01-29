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
    virtual void read() = 0;
    virtual const char* getHumidityTopic() = 0;
    virtual const char* getTemperatureTopic() = 0;
    virtual const char* getCO2Topic() { return nullptr; }
    virtual float getHumidity() = 0;
    virtual float getTemperature() = 0;
    virtual float getCO2() { return 0.0; }

    void resetTimeLastPublished() {
        time_last_published = millis();
    }

    unsigned long getTimeLastPublished() {
        return time_last_published;
    }

    float applySlopeAndOffset(float reading, float slope, float offset) {
        return reading * slope + offset;
    }
};

class SHTSensor : public Sensor {
private:
    float humidity;
    float temperature;
    Adafruit_SHT31 sensor;
    const char* humidity_topic;
    const char* temperature_topic;

public:
    SHTSensor(uint8_t addr, const char* hum_topic, const char* temp_topic, const std::string& sensor_instance)
        : Sensor(getCalibrationParams(sensor_instance)), humidity(0.0), temperature(0.0), sensor(addr),
          humidity_topic(hum_topic), temperature_topic(temp_topic) {}

    bool begin() override {
        return sensor.begin();
    }

    void read() override {
        humidity = applySlopeAndOffset(sensor.readHumidity(), humidity_slope, humidity_offset);
        temperature = applySlopeAndOffset(celsiusToFahrenheit(sensor.readTemperature()), temperature_slope, temperature_offset);
    }

    const char* getHumidityTopic() override {
        return humidity_topic;
    }

    const char* getTemperatureTopic() override {
        return temperature_topic;
    }

    float getHumidity() override {
        return humidity;
    }

    float getTemperature() override {
        return temperature;
    }
};

class DHTSensor : public Sensor {
private:
    float humidity;
    float temperature;
    DHT sensor;
    const char* humidity_topic;
    const char* temperature_topic;

public:
    DHTSensor(uint8_t pin, uint8_t type, const char* hum_topic, const char* temp_topic, const std::string& sensor_instance)
        : Sensor(getCalibrationParams(sensor_instance)), humidity(0.0), temperature(0.0), sensor(pin, type),
          humidity_topic(hum_topic), temperature_topic(temp_topic) {}

    bool begin() override {
        sensor.begin();
        return true; // DHT library does not provide a way to check if the sensor began successfully
    }

    void read() override {
        humidity = applySlopeAndOffset(sensor.readHumidity(), humidity_slope, humidity_offset);
        temperature = applySlopeAndOffset(celsiusToFahrenheit(sensor.readTemperature()), temperature_slope, temperature_offset);
    }

    const char* getHumidityTopic() override {
        return humidity_topic;
    }

    const char* getTemperatureTopic() override {
        return temperature_topic;
    }

    float getHumidity() override {
        return humidity;
    }

    float getTemperature() override {
        return temperature;
    }
};

class SCDSensor : public Sensor {
private:
    float humidity;
    float temperature;
    float co2;
    SCD4x sensor;
    const char* humidity_topic;
    const char* temperature_topic;
    const char* co2_topic;

public:
    SCDSensor(const char* hum_topic, const char* temp_topic, const char* co2_topic, const std::string& sensor_instance)
        : Sensor(getCalibrationParams(sensor_instance)), humidity(0.0), temperature(0.0), co2(0.0),
          humidity_topic(hum_topic), temperature_topic(temp_topic), co2_topic(co2_topic) {}

    bool begin() override {
        return sensor.begin();
    }

    void read() override {
        if (sensor.readMeasurement()) {
            humidity = applySlopeAndOffset(sensor.getHumidity(), humidity_slope, humidity_offset);
            temperature = applySlopeAndOffset(celsiusToFahrenheit(sensor.getTemperature()), temperature_slope, temperature_offset);
            co2 = applySlopeAndOffset(sensor.getCO2(), co2_slope, co2_offset);
        }
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

    float getHumidity() override {
        return humidity;
    }

    float getTemperature() override {
        return temperature;
    }

    float getCO2() override {
        return co2;
    }
};

#endif // SENSOR_STRUCTS_H