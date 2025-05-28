#ifndef PUBLISH_DATA_H
#define PUBLISH_DATA_H

#include <Arduino.h>

// Forward declarations to avoid circular includes
class ActuatorControlPoint;
class SensorPoint;

/**
 * PublishData Struct
 * 
 * Purpose: Represents a single item in the publish queue, containing all
 * information needed to publish an MQTT message with ADR-10 compliant payload.
 * 
 * Based on ADR-22 Section 2.3.2
 */
struct PublishData {
    const char* topic;              // MQTT topic to publish to
    const char* uuid;               // Futurepoofing
    String serializedValue;         // "on", "off", "23.5", etc.
    String timestampIsoUtc;         // YYYY-MM-DDTHH:MM:SS.sssZ
    ActuatorControlPoint* sourceActuator;  // nullptr if not from actuator
    SensorPoint* sourceSensor;             // nullptr if not from sensor

    // Default constructor
    PublishData() : topic(nullptr), uuid(nullptr), sourceActuator(nullptr), sourceSensor(nullptr) {}
    
    // Constructor for actuator readback
    PublishData(const char* topic, const char* uuid, const String& value, 
                const String& timestamp, ActuatorControlPoint* actuator)
        : topic(topic), uuid(uuid), serializedValue(value), timestampIsoUtc(timestamp),
          sourceActuator(actuator), sourceSensor(nullptr) {}
    
    // Constructor for sensor data
    PublishData(const char* topic, const char* uuid, const String& value, 
                const String& timestamp, SensorPoint* sensor)
        : topic(topic), uuid(uuid), serializedValue(value), timestampIsoUtc(timestamp),
          sourceActuator(nullptr), sourceSensor(sensor) {}
    
    // Constructor for general data (status, errors, etc.)
    PublishData(const char* topic, const char* uuid, const String& value, 
                const String& timestamp)
        : topic(topic), uuid(uuid), serializedValue(value), timestampIsoUtc(timestamp),
          sourceActuator(nullptr), sourceSensor(nullptr) {}
};

#endif // PUBLISH_DATA_H 