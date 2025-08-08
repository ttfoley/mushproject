#ifndef SENSOR_CONFIGS_H
#define SENSOR_CONFIGS_H

#include <stdint.h>

/**
 * @file SensorConfigs.h
 * @brief Common sensor configuration structures for all microcontrollers
 * 
 * This header defines configuration structs for different sensor types.
 * Controller-specific autogen_config.h files include this header and 
 * define instances of these structs with their specific parameters.
 * 
 * Following ADR-25: Struct-Based Configuration for Microcontroller Components
 */

// === Base Configuration Structure ===

/**
 * @brief Base configuration structure containing fields common to all sensors
 * Used as a member in sensor-specific config structs to eliminate duplication
 */
struct BaseSensorConfig {
    const char* point_name;            // Human-readable point name (e.g., "FruitingChamber_SHT85_0")
    unsigned long publish_interval_ms; // How often to publish readings
    unsigned long main_loop_delay_ms;  // Main loop delay for timing calculations
    unsigned long max_time_no_publish_ms; // Timeout for publish failure detection
};

// === I2C Sensor Configuration Structs ===

/**
 * @brief Configuration structure for SHT85 I2C Temperature/Humidity Sensor
 */
struct SHT85Config {
    const char* point_name;            // Human-readable point name
    unsigned long publish_interval_ms; // How often to publish readings
    unsigned long main_loop_delay_ms;  // Main loop delay for timing calculations
    unsigned long max_time_no_publish_ms; // Timeout for publish failure detection
    uint8_t address;                    // I2C address
    bool c_to_f;                       // Convert Celsius to Fahrenheit
    const char* temp_topic;            // MQTT topic for temperature
    const char* temp_uuid;             // UUID for temperature reading
    const char* humidity_topic;        // MQTT topic for humidity
    const char* humidity_uuid;         // UUID for humidity reading
};

/**
 * @brief Configuration structure for BME280 I2C Temperature/Humidity/Pressure Sensor
 */
struct BME280Config {
    const char* point_name;            // Human-readable point name
    unsigned long publish_interval_ms; // How often to publish readings
    unsigned long main_loop_delay_ms;  // Main loop delay for timing calculations
    unsigned long max_time_no_publish_ms; // Timeout for publish failure detection
    uint8_t address;                    // I2C address
    bool c_to_f;                       // Convert Celsius to Fahrenheit
    const char* temp_topic;            // MQTT topic for temperature
    const char* temp_uuid;             // UUID for temperature reading
    const char* humidity_topic;        // MQTT topic for humidity
    const char* humidity_uuid;         // UUID for humidity reading
    const char* pressure_topic;        // MQTT topic for pressure
    const char* pressure_uuid;         // UUID for pressure reading
};

/**
 * @brief Configuration structure for SCD4x I2C CO2/Temperature/Humidity Sensor
 */
struct SCD4xConfig {
    const char* point_name;            // Human-readable point name
    unsigned long publish_interval_ms; // How often to publish readings
    unsigned long main_loop_delay_ms;  // Main loop delay for timing calculations
    unsigned long max_time_no_publish_ms; // Timeout for publish failure detection
    uint8_t address;                    // I2C address (typically 0x62)
    bool c_to_f;                       // Convert Celsius to Fahrenheit
    const char* co2_topic;             // MQTT topic for CO2 concentration
    const char* co2_uuid;              // UUID for CO2 reading
    const char* temp_topic;            // MQTT topic for temperature
    const char* temp_uuid;             // UUID for temperature reading
    const char* humidity_topic;        // MQTT topic for humidity
    const char* humidity_uuid;         // UUID for humidity reading
};

// === Digital Sensor Configuration Structs ===

/**
 * @brief Configuration structure for DHT22 Digital Temperature/Humidity Sensor
 */
struct DHT22Config {
    const char* point_name;            // Human-readable point name
    unsigned long publish_interval_ms; // How often to publish readings
    unsigned long main_loop_delay_ms;  // Main loop delay for timing calculations
    unsigned long max_time_no_publish_ms; // Timeout for publish failure detection
    uint8_t pin;                       // Digital pin number
    bool c_to_f;                       // Convert Celsius to Fahrenheit
    const char* temp_topic;            // MQTT topic for temperature
    const char* temp_uuid;             // UUID for temperature reading
    const char* humidity_topic;        // MQTT topic for humidity
    const char* humidity_uuid;         // UUID for humidity reading
};

// === OneWire Sensor Configuration Structs ===

/**
 * @brief Configuration structure for DS18B20 OneWire Temperature Sensor
 */
struct DS18B20Config {
    const char* point_name;            // Human-readable point name
    unsigned long publish_interval_ms; // How often to publish readings
    unsigned long main_loop_delay_ms;  // Main loop delay for timing calculations
    unsigned long max_time_no_publish_ms; // Timeout for publish failure detection
    uint8_t pin;                       // Digital pin number for OneWire bus
    uint8_t resolution_bits;           // Resolution: 9-12 bits (9=0.5°C, 10=0.25°C, 11=0.125°C, 12=0.0625°C)
    bool c_to_f;                       // Convert Celsius to Fahrenheit
    const char* temp_topic;            // MQTT topic for temperature
    const char* temp_uuid;             // UUID for temperature reading
};


#endif // SENSOR_CONFIGS_H 