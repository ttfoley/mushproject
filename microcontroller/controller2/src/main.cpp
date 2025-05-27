#include <Arduino.h>
#include "NtpService.h" // Assuming NtpService.h is in common_firmware_lib/include
                       // and common_firmware_lib is correctly linked.
#include <WiFi.h>
#include "autogen_config.h" // For WiFi credentials and MQTT configuration
#include "JsonBuilder.h" // For testing ADR-10 JSON payload construction
#include "MqttService.h" // For MQTT communication
#include "ActuatorControlPoint.h" // For actuator management
#include "PublishData.h" // For publish queue
#include <map>
#include <queue>
#include <set>
#include <vector>

// =============================================================================
// ACTUATOR CREATION MACRO (DRY Principle)
// =============================================================================

// Macro to automatically create ActuatorControlPoint instances from autogen_config.h naming pattern
// Usage: CREATE_ACTUATOR(C2_HumidifierRelay) expands to full constructor call
#define CREATE_ACTUATOR(name) \
    new ActuatorControlPoint( \
        PIN_##name, \
        MODE_##name, \
        INITIAL_STATE_##name, \
        POINT_NAME_##name, \
        TOPIC_##name##_WRITE, \
        TOPIC_##name##_READBACK, \
        UUID_##name##_READBACK, \
        OUTPUT_REPUBLISH_FREQUENCY_MS, \
        MAX_TIME_NO_PUBLISH_MS \
    )

// =============================================================================
// GLOBAL COMMAND MANAGEMENT STRUCTURES (ADR-22 Section 2.3.1)
// =============================================================================

// Global vector to hold all actuator control points for this controller
std::vector<ActuatorControlPoint*> g_actuatorPoints;

// Command Management for "Latest Wins" Logic
std::map<ActuatorControlPoint*, String> g_pendingActuatorCommands;
std::queue<ActuatorControlPoint*> g_actuatorsToProcessQueue;
std::set<ActuatorControlPoint*> g_actuatorsInProcessQueueSet;

// Global publish queue for all outgoing MQTT messages
std::queue<PublishData> g_publishQueue;

// =============================================================================
// EXISTING CONFIGURATION AND SERVICES
// =============================================================================

// MQTT Configuration (will later come from autogen_config.h)
const char* MQTT_HUMIDIFIER_READBACK_TOPIC = "mush/controllers/C2/control_points/CP_25/readback/raw/value";

// MQTT Connection Retry Logic for Setup
const unsigned long MQTT_CONNECT_RETRY_INTERVAL_MS = 2000; // How often to call connectBroker()

NtpService ntpService;
// Instantiate MqttService with credentials from auto_gen_config.h
MqttService mqttService(MQTT_CLIENT_ID, MQTT_BROKER_ADDRESS, MQTT_BROKER_PORT, 
                        MQTT_USERNAME, MQTT_PASSWORD);

// How often to attempt NTP update in the loop (milliseconds)
const unsigned long NTP_LOOP_UPDATE_INTERVAL = 60000; // Every 60 seconds
unsigned long lastNtpLoopUpdate = 0;

// How often to print the time in the loop (milliseconds)
const unsigned long PRINT_TIME_INTERVAL = 5000; // Every 5 seconds
unsigned long lastTimePrint = 0;

// How often to print debug queue status (milliseconds)
const unsigned long DEBUG_QUEUE_INTERVAL = 30000; // Every 30 seconds
unsigned long lastDebugPrint = 0;

void setupWifi() {
    Serial.print("Connecting to WiFi: ");
    Serial.println(WIFI_SSID);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    unsigned long startTime = millis();
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
        if (millis() - startTime > 20000) { // 20 second timeout
            Serial.println("\nWiFi connection FAILED. Restarting...");
            // In a real FSM, this would trigger RestartReasonLogger.storeRestartReason(WIFI_TIMEOUT);
            // and then ESP.restart();
            delay(1000);
            ESP.restart(); 
        }
    }
    Serial.println("\nWiFi connected!");
    Serial.print("IP Address: ");
    Serial.println(WiFi.localIP());
}

void setupNtp() {
    Serial.println("Initializing NTP Service...");
    ntpService.begin();

    Serial.println("Attempting initial NTP synchronization...");
    unsigned long startTime = millis();
    bool initialSyncDone = false;
    while(!initialSyncDone) {
        // NtpService.update() internally calls timeClient.update()
        // It's non-blocking in the sense that timeClient.update() is.
        // We need to call it until isTimeSet() is true or we timeout.
        ntpService.update(); 
        if (ntpService.isTimeSet()) {
            Serial.println("\nInitial NTP sync successful!");
            Serial.print("Current UTC Time (from getFormattedISO8601Time): ");
            Serial.println(ntpService.getFormattedISO8601Time());
            Serial.print("Current Epoch Time (from getEpochTime -> gettimeofday): ");
            Serial.println(ntpService.getEpochTime());
            initialSyncDone = true;
        } else {
            Serial.print("u"); // Update attempt
        }
        
        if (millis() - startTime > 30000 && !initialSyncDone) { // 30 second timeout for initial sync
            Serial.println("\nInitial NTP sync FAILED after timeout.");
            // In a real FSM, this would trigger RestartReasonLogger.storeRestartReason(NTP_TIMEOUT);
            // and potentially lead to a restart or other error handling.
            // For now, we proceed, but time will be unsynchronized.
            break; 
        }
        delay(1000); // Wait a bit between attempts
    }

    // --- Test JsonBuilder --- (Commented out as we are now testing MQTT which uses JsonBuilder)
    /*
    if (initialSyncDone) { // Only test if we have a valid timestamp
        Serial.println("\n--- Testing JsonBuilder --- ");
        String currentTimestamp = ntpService.getFormattedISO8601Time();

        String json_string = JsonBuilder::buildPayload(currentTimestamp, "hello world");
        Serial.print("Test 1 (const char*): "); Serial.println(json_string);

        String json_int = JsonBuilder::buildPayload(currentTimestamp, 12345);
        Serial.print("Test 2 (int): "); Serial.println(json_int);

        String json_float = JsonBuilder::buildPayload(currentTimestamp, 3.14159f, 3); // 3 decimal places
        Serial.print("Test 3 (float): "); Serial.println(json_float);

        String json_bool_true = JsonBuilder::buildPayload(currentTimestamp, true);
        Serial.print("Test 4 (bool true): "); Serial.println(json_bool_true);

        String json_bool_false = JsonBuilder::buildPayload(currentTimestamp, false);
        Serial.print("Test 5 (bool false): "); Serial.println(json_bool_false);
        Serial.println("--- End JsonBuilder Test ---");
    }
    */
    // --- End Test JsonBuilder ---
}

void setupActuators() {
    Serial.println("Initializing Actuator Control Points...");
    
    // Create ActuatorControlPoint instances for all 4 actuators in Controller C2
    // Based on autogen_config.h definitions
    
    // 1. Humidifier Relay
    g_actuatorPoints.push_back(CREATE_ACTUATOR(C2_HumidifierRelay));
    Serial.print("Created actuator: "); Serial.println(POINT_NAME_C2_HumidifierRelay);
    
    // 2. Heating Pad Relay
    g_actuatorPoints.push_back(CREATE_ACTUATOR(C2_HeatingPadRelay));
    Serial.print("Created actuator: "); Serial.println(POINT_NAME_C2_HeatingPadRelay);
    
    // 3. Light Relay
    g_actuatorPoints.push_back(CREATE_ACTUATOR(C2_LightRelay));
    Serial.print("Created actuator: "); Serial.println(POINT_NAME_C2_LightRelay);
    
    // 4. Vent Fan Relay
    g_actuatorPoints.push_back(CREATE_ACTUATOR(C2_VentFanRelay));
    Serial.print("Created actuator: "); Serial.println(POINT_NAME_C2_VentFanRelay);
    
    Serial.print("Total actuators created: "); Serial.println(g_actuatorPoints.size());
    
    // Initialize all actuators (calls pinMode and sets initial hardware state)
    Serial.println("Initializing actuator hardware...");
    for (ActuatorControlPoint* actuator : g_actuatorPoints) {
        actuator->initialize();
        Serial.print("Initialized hardware for: "); Serial.println(actuator->getPointName());
    }
    
    // Setup initial commands for all actuators (ADR-22 Section 2.5 SETUP_HW state)
    Serial.println("Setting up initial actuator commands...");
    for (ActuatorControlPoint* actuator : g_actuatorPoints) {
        // Set initial command payload to "off" for all actuators
        String initialPayload = "off";
        
        // Populate command management structures
        g_pendingActuatorCommands[actuator] = initialPayload;
        g_actuatorsToProcessQueue.push(actuator);
        g_actuatorsInProcessQueueSet.insert(actuator);
        
        Serial.print("Queued initial command '"); 
        Serial.print(initialPayload);
        Serial.print("' for: ");
        Serial.println(actuator->getPointName());
    }
    
    Serial.print("Total actuators queued for initial command processing: ");
    Serial.println(g_actuatorsToProcessQueue.size());
    
    Serial.println("Actuator setup complete.");
}

// =============================================================================
// DEBUG HELPER FUNCTIONS
// =============================================================================

void printCommandQueueStatus() {
    Serial.println("\n--- Command Queue Status ---");
    Serial.print("Pending commands: "); Serial.println(g_pendingActuatorCommands.size());
    Serial.print("Actuators to process: "); Serial.println(g_actuatorsToProcessQueue.size());
    Serial.print("Actuators in process set: "); Serial.println(g_actuatorsInProcessQueueSet.size());
    
    if (!g_pendingActuatorCommands.empty()) {
        Serial.println("Pending commands details:");
        for (const auto& pair : g_pendingActuatorCommands) {
            Serial.print("  - ");
            Serial.print(pair.first->getPointName());
            Serial.print(": '");
            Serial.print(pair.second);
            Serial.println("'");
        }
    }
    Serial.println("--- End Command Queue Status ---\n");
}

void printPublishQueueStatus() {
    Serial.println("\n--- Publish Queue Status ---");
    Serial.print("Items in publish queue: "); Serial.println(g_publishQueue.size());
    Serial.println("--- End Publish Queue Status ---\n");
}

void setup() {
    Serial.begin(115200);
    while (!Serial); // Wait for serial to connect (especially for some boards)
    Serial.println("\n\n--- Controller C2 (Refactored) MQTT Test ---");

    setupWifi();
    setupNtp();
    setupActuators();
    
    // Debug: Print command queue status after setup
    printCommandQueueStatus();

    Serial.println("Initializing MQTT Service...");
    mqttService.begin(); // Sets server and callback, does not connect

    Serial.println("Attempting to connect to MQTT broker...");
    unsigned long mqttConnectStartMs = millis();
    unsigned long lastMqttConnectAttemptMs = 0;

    while (!mqttService.isConnected() && (millis() - mqttConnectStartMs < MQTT_CONNECT_TIMEOUT_MS)) {
        unsigned long currentMs = millis();
        // Try to connect at defined intervals
        if (currentMs - lastMqttConnectAttemptMs >= MQTT_CONNECT_RETRY_INTERVAL_MS || lastMqttConnectAttemptMs == 0) {
            if (mqttService.connectBroker()) { // connectBroker() attempts connection
                Serial.println("MQTT connectBroker() successful.");
                // No need to print "connected", connectBroker itself does upon success
                break; // Exit while loop
            } else {
                Serial.print("m"); // Indication of a connection attempt by connectBroker()
                // connectBroker already prints failure details
            }
            lastMqttConnectAttemptMs = currentMs;
        }
        mqttService.loop(); // IMPORTANT: Allow PubSubClient to process outgoing/incoming packets
        delay(50); // Small delay to prevent busy-looping if not much else is happening
    }

    if (mqttService.isConnected()) {
        Serial.println("\nMQTT connection established.");
        // Test publishing humidifier status
        if (ntpService.isTimeSet()) {
            Serial.println("Testing Humidifier Status Publish via MQTT...");
            String timestamp = ntpService.getFormattedISO8601Time();
            bool published = mqttService.publishJson(MQTT_HUMIDIFIER_READBACK_TOPIC, timestamp, "on");
            if (published) {
                Serial.println("Test publish attempted successfully.");
            } else {
                Serial.println("Test publish attempt failed.");
            }
        } else {
            Serial.println("NTP time not set, cannot test MQTT publish with timestamp.");
        }
    } else {
        Serial.println("\nMQTT connection FAILED after timeout.");
    }

    Serial.println("Setup complete. Entering loop...");
    lastNtpLoopUpdate = millis(); // Initialize for loop updates
    lastTimePrint = millis();
    lastDebugPrint = millis(); // Initialize debug timer
}

void loop() {
    unsigned long currentTime = millis();

    mqttService.loop(); // Process MQTT messages and maintain connection

    // Periodically try to update NTP
    if (currentTime - lastNtpLoopUpdate >= NTP_LOOP_UPDATE_INTERVAL) {
        Serial.println("Attempting periodic NTP update...");
        if (ntpService.update()) {
            Serial.println("Periodic NTP update successful.");
            // Optional: Log if it *re*-established sync after being lost
        } else {
            Serial.println("Periodic NTP update attempt made (may not have changed time if already set).");
        }
        lastNtpLoopUpdate = currentTime;
    }

    // Periodically print the current time
    if (currentTime - lastTimePrint >= PRINT_TIME_INTERVAL) {
        if (ntpService.isTimeSet()) {
            Serial.print(millis());
            Serial.print(" - Current UTC Time: ");
            Serial.println(ntpService.getFormattedISO8601Time());
        } else {
            Serial.print(millis());
            Serial.println(" - NTP time not set.");
        }
        lastTimePrint = currentTime;
    }

    // Periodically print debug queue status
    if (currentTime - lastDebugPrint >= DEBUG_QUEUE_INTERVAL) {
        printCommandQueueStatus();
        printPublishQueueStatus();
        lastDebugPrint = currentTime;
    }

    // Placeholder for future FSM logic
    delay(10); 
} 