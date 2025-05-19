#ifndef MQTTSERVICE_H
#define MQTTSERVICE_H

#include <Arduino.h>
#include <WiFiClient.h>      // For PubSubClient
#include <PubSubClient.h>    // The MQTT client library
#include "NtpService.h"      // To get timestamps for MQTT payloads
#include "JsonBuilder.h"     // To build the JSON part of the payload
// #include "CommandQueue.h" // Will be needed later for P1.C2.4

// Default MQTT configuration (will later come from autogen_config.h)
#define MQTT_RECONNECT_INTERVAL 5000 // Milliseconds

class MqttService {
public:
    // Constructor: Takes MQTT broker details and client credentials.
    // NtpService is no longer directly passed or stored here for publishJson timestamping,
    // as timestamps will be provided by the caller to publishJson.
    MqttService(const char* client_id, 
                const char* server, int port, 
                const char* user = "", const char* password = "");

    // Initializes the MQTT client and sets the callback.
    // Call after WiFi is connected.
    void begin();

    // Main loop function for the MQTT client. Call this regularly.
    // Primarily processes incoming/outgoing MQTT messages and keepalives via mqttClient.loop().
    // Does NOT automatically attempt to reconnect; FSM should call connectBroker() for that.
    bool loop();

    // Attempts to connect to the MQTT broker. Performs a single connection attempt.
    // Returns true if connection was successful, false otherwise.
    // The FSM is responsible for calling this and managing retries/timeouts.
    bool connectBroker(); 

    // Checks if the MQTT client is currently connected.
    bool isConnected();

    // Publishes a JSON payload to the specified topic.
    // The caller is responsible for providing the correct timestamp_utc.
    // These methods will use JsonBuilder to construct the ADR-10 payload and then publish it.
    // Returns true if publishing was successful (or at least attempted without immediate error).
    bool publishJson(const char* topic, const String& timestamp_utc, const char* value);
    bool publishJson(const char* topic, const String& timestamp_utc, String value);
    bool publishJson(const char* topic, const String& timestamp_utc, int value);
    bool publishJson(const char* topic, const String& timestamp_utc, float value, int decimalPlaces = 2);
    bool publishJson(const char* topic, const String& timestamp_utc, double value, int decimalPlaces = 2);
    bool publishJson(const char* topic, const String& timestamp_utc, bool value);

    // TODO: Add subscribe and more sophisticated callback mechanisms later based on P1.C2.4

private:
    WiFiClient wifiClient;      // Underlying TCP client for MQTT
    PubSubClient mqttClient;    // The actual MQTT client
    // NtpService* _ntpService; // No longer needed here for publishJson timestamping

    // MQTT Connection Parameters
    String _clientId;
    String _server;
    int _port;
    String _user;
    String _password;

    // Static callback function required by PubSubClient library.
    // This will call the instance-specific callback.
    static void staticMqttCallback(char* topic, byte* payload, unsigned int length);
    
    // Instance-specific callback to handle incoming messages.
    void instanceMqttCallback(char* topic, byte* payload, unsigned int length);

    // Static pointer to the current instance, for the static callback to use.
    // (Assumes only one MqttService instance, typical for microcontrollers)
    static MqttService* _instance;
};

#endif // MQTTSERVICE_H 