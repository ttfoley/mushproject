#include "MqttService.h"
#include <Arduino.h> // For Serial, millis(), etc.
#include "ActuatorControlPoint.h"

// Initialize static member pointer. This is crucial for the static callback.
MqttService* MqttService::_instance = nullptr;

MqttService::MqttService(const char* client_id, 
                         const char* server, int port, 
                         const char* user, const char* password)
    : mqttClient(wifiClient), // Initialize PubSubClient with the WiFiClient
      _clientId(client_id),
      _server(server),
      _port(port),
      _user(user),
      _password(password),
      _topicToActuatorMap(nullptr),
      _pendingCommands(nullptr),
      _processQueue(nullptr),
      _processSet(nullptr) {
    _instance = this;
}

void MqttService::begin() {
    mqttClient.setServer(_server.c_str(), _port);
    mqttClient.setCallback(MqttService::staticMqttCallback);
}

void MqttService::setCommandManagement(
    std::map<String, ActuatorControlPoint*>* topicToActuatorMap,
    std::map<ActuatorControlPoint*, String>* pendingCommands,
    std::queue<ActuatorControlPoint*>* processQueue,
    std::set<ActuatorControlPoint*>* processSet) {
    
    _topicToActuatorMap = topicToActuatorMap;
    _pendingCommands = pendingCommands;
    _processQueue = processQueue;
    _processSet = processSet;
    
    Serial.println("Command management structures set for MqttService");
}

bool MqttService::loop() {
    // if (!mqttClient.connected()) { // Logic moved to FSM control via connectBroker()
    //     unsigned long now = millis();
    //     if (now - lastReconnectAttempt > MQTT_RECONNECT_INTERVAL) {
    //         lastReconnectAttempt = now;
    //         connectBroker(); // Attempt to reconnect (this was reconnect() before)
    //     }
    // }
    return mqttClient.loop(); // Essential for PubSubClient to process messages and keepalive
}

bool MqttService::isConnected() {
    return mqttClient.connected();
}

// Renamed from reconnect() and made public. Returns bool for success.
bool MqttService::connectBroker() {
    if (mqttClient.connected()) {
        return true; // Already connected
    }

    Serial.print("Attempting MQTT connection to ");
    Serial.print(_server);
    Serial.print(":");
    Serial.print(_port);
    Serial.print(" as ");
    Serial.print(_clientId);
    Serial.print("...");

    bool result;
    if (_user.length() > 0) {
        result = mqttClient.connect(_clientId.c_str(), _user.c_str(), _password.c_str());
    } else {
        result = mqttClient.connect(_clientId.c_str());
    }

    if (result) {
        Serial.println(" connected.");
        // TODO: Resubscribe to topics here if needed after a reconnect
        // (Will be relevant for P1.C2.4 and beyond)
    } else {
        Serial.print(" failed, rc=");
        Serial.print(mqttClient.state());
        Serial.println("."); // Removed "Trying again in 5 seconds."
        // Note: The actual retry is governed by the FSM calling this method again.
    }
    return result; // Return the connection attempt status
}

bool MqttService::subscribe(const char* topic) {
    if (!isConnected()) {
        Serial.print("MQTT not connected. Cannot subscribe to: ");
        Serial.println(topic);
        return false;
    }
    
    bool result = mqttClient.subscribe(topic);
    if (result) {
        Serial.print("Successfully subscribed to: ");
        Serial.println(topic);
    } else {
        Serial.print("Failed to subscribe to: ");
        Serial.println(topic);
    }
    return result;
}

// Static callback function
void MqttService::staticMqttCallback(char* topic, byte* payload, unsigned int length) {
    if (_instance) {
        _instance->instanceMqttCallback(topic, payload, length);
    }
}

// Instance-specific callback (currently lean)
void MqttService::instanceMqttCallback(char* topic, byte* payload, unsigned int length) {
    Serial.print("Message arrived [");
    Serial.print(topic);
    Serial.print("] ");
    
    // Create null-terminated string from payload
    char msg[length + 1];
    memcpy(msg, payload, length);
    msg[length] = '\0'; // Null-terminate the string
    Serial.println(msg);

    // Check if command management is set up
    if (!_topicToActuatorMap || !_pendingCommands || !_processQueue || !_processSet) {
        Serial.println("Command management not initialized - ignoring message");
        return;
    }

    String topicStr = String(topic);
    String payloadStr = String(msg);
    
    // Look up actuator for this topic
    auto it = _topicToActuatorMap->find(topicStr);
    if (it == _topicToActuatorMap->end()) {
        Serial.print("No actuator found for topic: ");
        Serial.println(topicStr);
        return;
    }
    
    ActuatorControlPoint* targetActuator = it->second;
    Serial.print("Found actuator: ");
    Serial.println(targetActuator->getPointName());
    
    // Parse ADR-10 JSON payload
    if (!payloadStr.startsWith("{") || !payloadStr.endsWith("}")) {
        Serial.println("Invalid payload - expected ADR-10 JSON format");
        return;
    }
    
    // Extract value field from JSON
    int valueStart = payloadStr.indexOf("\"value\":\"");
    if (valueStart == -1) {
        Serial.println("Invalid payload - missing 'value' field");
        return;
    }
    
    valueStart += 9; // Move past "value":"
    int valueEnd = payloadStr.indexOf("\"", valueStart);
    if (valueEnd == -1) {
        Serial.println("Invalid payload - malformed 'value' field");
        return;
    }
    
    String commandValue = payloadStr.substring(valueStart, valueEnd);
    Serial.print("Parsed command: ");
    Serial.println(commandValue);
    
    // Validate command
    if (commandValue != "on" && commandValue != "off") {
        Serial.print("Invalid command value: ");
        Serial.println(commandValue);
        return;
    }
    
    // Update command management structures (latest wins logic)
    (*_pendingCommands)[targetActuator] = commandValue;
    
    // Add to processing queue if not already queued
    if (_processSet->find(targetActuator) == _processSet->end()) {
        _processQueue->push(targetActuator);
        _processSet->insert(targetActuator);
        Serial.print("Queued command '");
        Serial.print(commandValue);
        Serial.print("' for: ");
        Serial.println(targetActuator->getPointName());
    } else {
        Serial.print("Updated existing command to '");
        Serial.print(commandValue);
        Serial.print("' for: ");
        Serial.println(targetActuator->getPointName());
    }
}

// --- publishJson Implementations ---

bool MqttService::publishJson(const char* topic, const String& timestamp_utc, const char* value) {
    if (!isConnected()) {
        Serial.println("MQTT not connected. Cannot publish.");
        return false;
    }
    String payload = JsonBuilder::buildPayload(timestamp_utc, value);
    if (payload.indexOf("error") != -1 && payload.startsWith("{")) { // Basic check for error JSON
        Serial.print("JsonBuilder error: "); Serial.println(payload);
        return false;
    }
    //Serial.print("Publishing to "); Serial.print(topic); Serial.print(": "); Serial.println(payload); 
    return mqttClient.publish(topic, payload.c_str());
}

bool MqttService::publishJson(const char* topic, const String& timestamp_utc, String value) {
    return publishJson(topic, timestamp_utc, value.c_str());
}

bool MqttService::publishJson(const char* topic, const String& timestamp_utc, int value) {
    // Convert int to string for JsonBuilder
    char buffer[12];
    sprintf(buffer, "%d", value);
    return publishJson(topic, timestamp_utc, buffer);
}

bool MqttService::publishJson(const char* topic, const String& timestamp_utc, float value, int decimalPlaces) {
    // Convert float to string for JsonBuilder
    char buffer[32];
    dtostrf(value, 0, decimalPlaces, buffer);
    return publishJson(topic, timestamp_utc, buffer);
}

bool MqttService::publishJson(const char* topic, const String& timestamp_utc, double value, int decimalPlaces) {
    return publishJson(topic, timestamp_utc, static_cast<float>(value), decimalPlaces);
}

bool MqttService::publishJson(const char* topic, const String& timestamp_utc, bool value) {
    return publishJson(topic, timestamp_utc, value ? "true" : "false");
} 