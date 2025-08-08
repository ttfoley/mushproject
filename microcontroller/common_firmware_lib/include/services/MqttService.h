#ifndef MQTTSERVICE_H
#define MQTTSERVICE_H

#include <Arduino.h>
#include <WiFiClient.h>      // For PubSubClient
#include <PubSubClient.h>    // The MQTT client library
#include "NtpService.h"      // To get timestamps for MQTT payloads
#include "../utils/JsonBuilder.h"     // To build the JSON part of the payload
#include <map>               // For topic-to-actuator mapping
#include <queue>             // For command processing queue
#include <set>               // For actuator tracking set
// #include "CommandQueue.h" // Will be needed later for P1.C2.4

// Forward declaration to avoid circular includes
class ActuatorControlPoint;

// Default MQTT configuration (will later come from autogen_config.h)
#define MQTT_RECONNECT_INTERVAL 5000 // Milliseconds

class MqttService {
public:
    // Constructor: Takes MQTT broker details and client credentials.
    MqttService(const char* client_id, 
                const char* server, int port, 
                const char* user = "", const char* password = "");

    // Initializes the MQTT client and sets the callback.
    void begin();

    // Set references to command management structures (called from main.cpp setup)
    void setCommandManagement(
        std::map<String, ActuatorControlPoint*>* topicToActuatorMap,
        std::map<ActuatorControlPoint*, String>* pendingCommands,
        std::queue<ActuatorControlPoint*>* processQueue,
        std::set<ActuatorControlPoint*>* processSet
    );

    // Main loop function for the MQTT client. Call this regularly.
    bool loop();

    // Attempts to connect to the MQTT broker. Performs a single connection attempt.
    // Returns true if connection was successful, false otherwise.
    // The FSM is responsible for calling this and managing retries/timeouts.
    bool connectBroker(); 

    // Checks if the MQTT client is currently connected.
    bool isConnected();

    // Publishes a JSON payload to the specified topic.
    // The caller is responsible for providing the correct timestamp_utc and UUID.
    // These methods will use JsonBuilder to construct the ADR-10 payload and then publish it.
    // Returns true if publishing was successful (or at least attempted without immediate error).
    bool publishJson(const char* topic, const String& timestamp_utc, const String& uuid, const char* value);
    bool publishJson(const char* topic, const String& timestamp_utc, const String& uuid, String value);
    bool publishJson(const char* topic, const String& timestamp_utc, const String& uuid, int value);
    bool publishJson(const char* topic, const String& timestamp_utc, const String& uuid, float value, int decimalPlaces = 2);
    bool publishJson(const char* topic, const String& timestamp_utc, const String& uuid, double value, int decimalPlaces = 2);
    bool publishJson(const char* topic, const String& timestamp_utc, const String& uuid, bool value);

    // Subscribe to a topic for receiving commands
    // Returns true if subscription was successful, false otherwise
    bool subscribe(const char* topic);

private:
    WiFiClient wifiClient;      // Underlying TCP client for MQTT
    PubSubClient mqttClient;    // The actual MQTT client


    // MQTT Connection Parameters
    String _clientId;
    String _server;
    int _port;
    String _user;
    String _password;

    // References to command management structures (set by main.cpp)
    std::map<String, ActuatorControlPoint*>* _topicToActuatorMap;
    std::map<ActuatorControlPoint*, String>* _pendingCommands;
    std::queue<ActuatorControlPoint*>* _processQueue;
    std::set<ActuatorControlPoint*>* _processSet;

    // Static callback function required by PubSubClient library.
    static void staticMqttCallback(char* topic, byte* payload, unsigned int length);
    
    // Instance-specific callback - handles command processing internally
    void instanceMqttCallback(char* topic, byte* payload, unsigned int length);

    // Static pointer to the current instance, for the static callback to use.
    // (Assumes only one MqttService instance, typical for microcontrollers)
    static MqttService* _instance;
};

#endif // MQTTSERVICE_H 