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

// Combined macro that creates actuator, adds to vector, and maps topic in one call
// Usage: CREATE_AND_MAP_ACTUATOR(C2_HumidifierRelay) does everything
#define CREATE_AND_MAP_ACTUATOR(name) \
    do { \
        g_actuatorPoints.push_back(CREATE_ACTUATOR(name)); \
        Serial.print("Created actuator: "); Serial.println(POINT_NAME_##name); \
        g_topicToActuatorMap[String(TOPIC_##name##_WRITE)] = g_actuatorPoints.back(); \
        Serial.print("Mapped topic "); Serial.print(TOPIC_##name##_WRITE); \
        Serial.print(" to actuator: "); Serial.println(g_actuatorPoints.back()->getPointName()); \
    } while(0)

// Macro to automatically subscribe to actuator WRITE topics from autogen_config.h naming pattern
// Usage: SUBSCRIBE_TO_ACTUATOR(C2_HumidifierRelay) expands to subscription call
#define SUBSCRIBE_TO_ACTUATOR(name) \
    do { \
        if (mqttService.subscribe(TOPIC_##name##_WRITE)) { \
            Serial.print("Subscribed to: "); Serial.println(TOPIC_##name##_WRITE); \
        } else { \
            Serial.print("Failed to subscribe to: "); Serial.println(TOPIC_##name##_WRITE); \
        } \
    } while(0)

// =============================================================================
// GLOBAL COMMAND MANAGEMENT STRUCTURES (ADR-22 Section 2.3.1)
// =============================================================================

// Global vector to hold all actuator control points for this controller
std::vector<ActuatorControlPoint*> g_actuatorPoints;

// Topic-to-Actuator mapping for efficient MQTT command processing
std::map<String, ActuatorControlPoint*> g_topicToActuatorMap;

// Command Management for "Latest Wins" Logic
std::map<ActuatorControlPoint*, String> g_pendingActuatorCommands;
std::queue<ActuatorControlPoint*> g_actuatorsToProcessQueue;
std::set<ActuatorControlPoint*> g_actuatorsInProcessQueueSet;

// Global publish queue for all outgoing MQTT messages
std::queue<PublishData> g_publishQueue;

// =============================================================================
// FSM STATE MANAGEMENT (ADR-17, ADR-22)
// =============================================================================

// FSM States based on ADR-17 and microcontroller plan
enum State {
    SETUP_HW,           // Hardware initialization (done in setup())
    CONNECT_WIFI,       // WiFi connection (done in setup())  
    SYNC_NTP,           // NTP synchronization (done in setup())
    CONNECT_MQTT,       // MQTT broker connection
    PROCESS_COMMANDS,   // Process queued actuator commands
    PUBLISH_DATA,       // Publish data from publish queue
    OPERATIONAL_PERIODIC_CHECKS, // Periodic maintenance tasks
    WAIT,               // Idle state, check what needs to be done
    RESTART             // Restart the controller
};

State currentState = CONNECT_MQTT; // Start with MQTT connection since setup() handles initial states
unsigned long stateStartTime = 0;  // For state timeouts

// =============================================================================
// EXISTING CONFIGURATION AND SERVICES
// =============================================================================


// MQTT Connection Retry Logic for Setup
const unsigned long MQTT_CONNECT_RETRY_INTERVAL_MS = 2000; // How often to call connectBroker()

NtpService ntpService;
// Instantiate MqttService with credentials from auto_gen_config.h
MqttService mqttService(MQTT_CLIENT_ID, MQTT_BROKER_ADDRESS, MQTT_BROKER_PORT, 
                        MQTT_USERNAME, MQTT_PASSWORD);

// How often to attempt NTP update in the loop (milliseconds)
const unsigned long NTP_LOOP_UPDATE_INTERVAL = 60000; // Every 60 seconds
unsigned long lastNtpLoopUpdate = 0;

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
}

void setupActuators() {
    Serial.println("Initializing Actuator Control Points...");
    
    // Create ActuatorControlPoint instances for all actuators using X-Macro pattern
    // Based on ACTUATOR_LIST from autogen_config.h
    
    #define X(name) CREATE_AND_MAP_ACTUATOR(name);
    ACTUATOR_LIST
    #undef X
    
    Serial.print("Total actuators created: "); Serial.println(g_actuatorPoints.size());
    Serial.print("Topic mappings created: "); Serial.println(g_topicToActuatorMap.size());
    
    // Initialize all actuators (calls pinMode and sets initial hardware state)
    Serial.println("Initializing actuator hardware...");
    for (ActuatorControlPoint* actuator : g_actuatorPoints) {
        actuator->initialize();
        Serial.print("Initialized hardware for: "); Serial.println(actuator->getPointName());
    }
    
    // Setup initial commands for all actuators (ADR-22 Section 2.5 SETUP_HW state)
    Serial.println("Setting up initial actuator commands...");
    for (ActuatorControlPoint* actuator : g_actuatorPoints) {
        // Use helper method to get the initial command payload
        // This respects the INITIAL_STATE_##name values from autogen_config.h
        String initialPayload = actuator->getInitialCommandPayload();
        
        Serial.print("Initial state for ");
        Serial.print(actuator->getPointName());
        Serial.print(": ");
        Serial.print(actuator->getInitialState() == HIGH ? "HIGH" : "LOW");
        Serial.print(" -> command: '");
        Serial.print(initialPayload);
        Serial.println("'");
        
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

void setupSubscriptions() {
    Serial.println("Setting up MQTT subscriptions...");
    
    // Subscribe to all actuator WRITE topics using X-Macro pattern
    #define X(name) SUBSCRIBE_TO_ACTUATOR(name);
    ACTUATOR_LIST
    #undef X
    
    Serial.println("MQTT subscriptions complete.");
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

// =============================================================================
// CONNECTIVITY AND PERIODIC FUNCTIONS
// =============================================================================

bool isWiFiConnected() {
    return true; // Skeleton - just return true for now
}

bool isMqttConnected() {
    return true; // Skeleton - just return true for now  
}

void checkPeriodicRepublishing() {
    for (ActuatorControlPoint* actuator : g_actuatorPoints) {
        if (actuator->isTimeToRepublish() && actuator->isLastStateSet()) {
            String timestamp = ntpService.getFormattedISO8601Time();
            PublishData periodicReadback(
                actuator->getReadbackTopic(),
                actuator->getReadbackUUID(),
                actuator->getLastSuccessfulPayload(),
                timestamp,
                actuator
            );
            g_publishQueue.push(periodicReadback);
        }
    }
}

void setup() {
    Serial.begin(115200);
    while (!Serial); // Wait for serial to connect (especially for some boards)
    Serial.println("\n\n--- Controller C2 (Refactored) Starting ---");

    setupWifi();
    setupNtp();
    setupActuators();
    
    // Debug: Print command queue status after setup
    printCommandQueueStatus();

    Serial.println("Initializing MQTT Service...");
    mqttService.begin();// Sets server and callback, does not connect
    
    // Set up command management for MQTT service
    mqttService.setCommandManagement(
        &g_topicToActuatorMap,
        &g_pendingActuatorCommands,
        &g_actuatorsToProcessQueue,
        &g_actuatorsInProcessQueueSet
    );

    Serial.println("Setup complete. Entering main FSM loop...");
    lastNtpLoopUpdate = millis(); // Initialize for loop updates
    lastDebugPrint = millis(); // Initialize debug timer
}

void loop() {
    unsigned long currentTime = millis();

    mqttService.loop(); // Process MQTT messages and maintain connection

    // Main FSM Logic
    switch (currentState) {
        case CONNECT_WIFI:
            // Skeleton - just transition back to WAIT for now
            currentState = WAIT;
            break;

        case CONNECT_MQTT:
            Serial.println("State: CONNECT_MQTT");
            if (mqttService.connectBroker()) {
                Serial.println("MQTT connected successfully!");
                setupSubscriptions(); // Subscribe to all actuator WRITE topics
                currentState = PROCESS_COMMANDS;
                stateStartTime = currentTime;
            } else {
                Serial.println("MQTT connection failed, retrying...");
                currentState = CONNECT_MQTT; // Explicit: stay in this state
                delay(2000); // Simple retry delay for now
            }
            break;

        case PROCESS_COMMANDS:
            Serial.println("State: PROCESS_COMMANDS");
            if (!g_actuatorsToProcessQueue.empty()) {
                // Process one command from the queue
                ActuatorControlPoint* actuatorToProcess = g_actuatorsToProcessQueue.front();
                g_actuatorsToProcessQueue.pop();
                g_actuatorsInProcessQueueSet.erase(actuatorToProcess);
                
                // Get the latest command for this actuator
                String latestPayload = g_pendingActuatorCommands[actuatorToProcess];
                
                Serial.print("Processing command '");
                Serial.print(latestPayload);
                Serial.print("' for: ");
                Serial.println(actuatorToProcess->getPointName());
                
                // Execute the command on the actuator
                if (actuatorToProcess->executeDeviceCommand(latestPayload)) {
                    // Command executed successfully - store the successful payload and create readback
                    actuatorToProcess->setLastSuccessfulPayload(latestPayload);
                    
                    String timestamp = ntpService.getFormattedISO8601Time();
                    
                    PublishData readback(
                        actuatorToProcess->getReadbackTopic(),
                        actuatorToProcess->getReadbackUUID(),
                        latestPayload,  // Use the payload we know succeeded
                        timestamp,
                        actuatorToProcess
                    );
                    
                    g_publishQueue.push(readback);
                    
                    Serial.print("Queued readback: ");
                    Serial.print(latestPayload);
                    Serial.print(" for topic: ");
                    Serial.println(actuatorToProcess->getReadbackTopic());
                } else {
                    // Command execution failed, Note that bad payloads are simply ignored instead trying to be interpreted as something "safe" like "off"
                    Serial.print("Command execution failed for payload: ");
                    Serial.println(latestPayload);
                    // Could add error handling/logging here in future
                }
                
                // Remove the processed command (whether successful or not)
                g_pendingActuatorCommands.erase(actuatorToProcess);
                
                // Transition to publish the readback (if any was created)
                currentState = PUBLISH_DATA;
            } else {
                // No commands to process, go to wait state

                currentState = WAIT;
            }
            break;

        case PUBLISH_DATA:
            Serial.println("State: PUBLISH_DATA");
            if (!g_publishQueue.empty()) {
                PublishData item = g_publishQueue.front();
                g_publishQueue.pop();
                
                Serial.print("Publishing to ");
                Serial.print(item.topic);
                Serial.print(": ");
                Serial.print(item.serializedValue);
                Serial.print(" at ");
                Serial.println(item.timestampIsoUtc);
                
                // Publish via MQTT using publishJson with the raw value
                if (mqttService.publishJson(item.topic, item.timestampIsoUtc, item.uuid, item.serializedValue)) {
                    Serial.println("Publish successful!");
                    
                    // Update the source actuator's last publish time
                    if (item.sourceActuator != nullptr) {
                        item.sourceActuator->setLastPublishTimeMillis(currentTime);
                    }
                } else {
                    Serial.println("Publish failed!");
                    // For now, just continue - could implement retry logic later
                }
                
                // Check if there are more items to publish
                if (!g_publishQueue.empty()) {
                    currentState = PUBLISH_DATA; // Stay in this state
                } else {
                    currentState = WAIT; // Go to wait state
                }
            } else {
                currentState = WAIT;
            }
            break;

        case WAIT:
            // Check connectivity first (highest priority)
            if (!isWiFiConnected()) {
                currentState = CONNECT_WIFI;
            } else if (!isMqttConnected()) {
                currentState = CONNECT_MQTT;
            }
            // Check for work to do
            else if (!g_actuatorsToProcessQueue.empty()) {
                currentState = PROCESS_COMMANDS;
            } else if (!g_publishQueue.empty()) {
                currentState = PUBLISH_DATA;
            } else {
                // Check for periodic republishing (lowest priority)
                checkPeriodicRepublishing();
                currentState = WAIT;
            }
            break;

        case RESTART:
            Serial.println("State: RESTART - Restarting controller...");
            delay(1000);
            ESP.restart();
            break;

        default:
            Serial.println("Unknown state! Going to RESTART");
            currentState = RESTART;
            break;
    }

    // Periodically try to update NTP
    if (currentTime - lastNtpLoopUpdate >= NTP_LOOP_UPDATE_INTERVAL) {
        if (ntpService.update()) {
            Serial.println("NTP update successful.");
        }
        lastNtpLoopUpdate = currentTime;
    }

    // Periodically print debug queue status
    if (currentTime - lastDebugPrint >= DEBUG_QUEUE_INTERVAL) {
        printCommandQueueStatus();
        printPublishQueueStatus();
        lastDebugPrint = currentTime;
    }

    delay(10); 
} 