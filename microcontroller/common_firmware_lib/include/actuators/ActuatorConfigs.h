#ifndef ACTUATOR_CONFIGS_H
#define ACTUATOR_CONFIGS_H

#include <stdint.h>

/**
 * @file ActuatorConfigs.h
 * @brief Common actuator configuration structures for all microcontrollers
 * 
 * This header defines configuration structs for different actuator types.
 * Controller-specific autogen_config.h files include this header and 
 * define instances of these structs with their specific parameters.
 * 
 * Following ADR-25: Struct-Based Configuration for Microcontroller Components
 */

// === Digital Actuator Configuration Structs ===

/**
 * @brief Configuration structure for digital relay/switch actuators
 * Used for simple on/off control of devices like humidifiers, heaters, lights, fans
 */
struct ActuatorConfig {
    uint8_t pin;                        // Digital pin number
    uint8_t pin_mode;                   // Pin mode (typically OUTPUT)
    uint8_t initial_state;              // Initial state (HIGH or LOW)
    const char* point_name;             // Human-readable point name
    const char* write_topic;            // MQTT topic for receiving commands
    const char* readback_topic;         // MQTT topic for publishing status
    const char* readback_uuid;          // UUID for readback/status publishing
    unsigned long republish_frequency_ms; // How often to republish status
    unsigned long max_time_no_publish_ms; // Timeout for publish failure detection
};


#endif // ACTUATOR_CONFIGS_H 