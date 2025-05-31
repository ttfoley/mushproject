#ifndef SENSOR_MACROS_H
#define SENSOR_MACROS_H

#include "SHT85SensorPoint.h"
// TODO: Include other sensor point headers as they're created

// =============================================================================
// SENSOR CREATION MACROS (DRY Principle)
// =============================================================================

// Macro to create I2C sensor instances based on model type
#define CREATE_I2C_SENSOR_SHT85(name) \
    new SHT85SensorPoint( \
        SENSOR_##name##_ADDRESS, \
        SENSOR_##name##_C_TO_F, \
        SENSOR_##name##_READING_TEMPERATURE_TOPIC, \
        SENSOR_##name##_READING_TEMPERATURE_UUID, \
        SENSOR_##name##_READING_HUMIDITY_TOPIC, \
        SENSOR_##name##_READING_HUMIDITY_UUID, \
        SENSOR_AND_STATUS_PUBLISH_INTERVAL_MS, \
        MAIN_LOOP_DELAY_MS \
    )

// Combined macro that creates sensor and adds to vector in one call
#define CREATE_AND_ADD_I2C_SENSOR(name) \
    do { \
        if (strcmp(SENSOR_##name##_MODEL, "SHT85") == 0) { \
            g_sensorPoints.push_back(CREATE_I2C_SENSOR_SHT85(name)); \
            Serial.print("Created I2C sensor: "); Serial.println(SENSOR_##name##_MODEL); \
        } else if (strcmp(SENSOR_##name##_MODEL, "BME280") == 0) { \
            /* TODO: CREATE_I2C_SENSOR_BME280(name) when BME280 class is ready */ \
            Serial.print("BME280 sensor creation TODO: "); Serial.println(#name); \
        } else { \
            Serial.print("Unknown I2C sensor model: "); Serial.println(SENSOR_##name##_MODEL); \
        } \
    } while(0)

// TODO: Add similar macros for DHT and OneWire sensors

#endif // SENSOR_MACROS_H 