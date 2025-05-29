#include <Arduino.h>
#include "NtpService.h" // Assuming NtpService.h is in common_firmware_lib/include
                       // and common_firmware_lib is correctly linked.
#include <WiFi.h>
#include "autogen_config.h" // For WiFi credentials and MQTT configuration
#include "JsonBuilder.h" // For testing ADR-10 JSON payload construction
#include "MqttService.h" // For MQTT communication
#include "ActuatorControlPoint.h" // For actuator management
#include "PublishData.h" // For publish queue
#include "RestartReasonLogger.h" // For persistent restart reason logging
#include "FsmUtils.h" // For FSM utility functions
#include <map>
#include <queue>
#include <set>
#include <vector>

// Use FsmUtils namespace for cleaner function calls
using namespace FsmUtils;

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


FsmState currentState = CONNECT_WIFI; // Start with WiFi connection - consistent startup sequence
unsigned long stateStartTime = 0;  // For state timeouts

// =============================================================================
// FSM STATE ATTEMPT COUNTERS
// =============================================================================

// WiFi connection attempts
static unsigned int wifiAttempts = 0;

// NTP sync attempts  
static unsigned int ntpAttempts = 0;

// Boot status publishing flag to prevent duplicates/publishes false restarts
static bool bootStatusPublished = false;

// =============================================================================
// EXISTING CONFIGURATION AND SERVICES
// =============================================================================

NtpService ntpService;
// Instantiate MqttService with credentials from auto_gen_config.h
MqttService mqttService(MQTT_CLIENT_ID, MQTT_BROKER_ADDRESS, MQTT_BROKER_PORT, 
                        MQTT_USERNAME, MQTT_PASSWORD);

// Restart reason logger for persistent error logging (ADR-14, ADR-17)
RestartReasonLogger restartLogger;

// How often to attempt NTP update in the loop (milliseconds)
unsigned long lastNtpLoopUpdate = 0;

// How often to print debug queue status (milliseconds)
unsigned long lastDebugPrint = 0;

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
    return WiFi.status() == WL_CONNECTED;
}

bool isMqttConnected() {
    return mqttService.isConnected();
}

void checkPeriodicRepublishing() {
    //note only actuators are checked for periodic republishing, not the whole system
    for (ActuatorControlPoint* actuator : g_actuatorPoints) {
        // Check for no-publish timeout first (ADR-18, P1.C2.7)
        if (actuator->hasNoPublishTimeoutOccurred()) {
            Serial.print("No-publish timeout occurred for actuator: ");
            Serial.println(actuator->getPointName());
            handleRestartWithReason(currentState, NOPUBLISH_TIMEOUT, restartLogger, ntpService);
            return; // Exit immediately - don't continue checking other actuators
        }
        
        // Check for periodic republishing
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

    // Hardware initialization only - connectivity handled by FSM
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
    Serial.println("FSM will handle: WiFi -> NTP -> MQTT -> Boot Status -> Normal Operation");
    lastNtpLoopUpdate = millis(); // Initialize for loop updates
    lastDebugPrint = millis(); // Initialize debug timer
    stateStartTime = millis(); // Initialize state timing for first FSM state
}

void loop() {
    unsigned long currentTime = millis();

    mqttService.loop(); // Process MQTT messages and maintain connection

    // Main FSM Logic
    switch (currentState) {
        case CONNECT_WIFI:
            Serial.println("State: CONNECT_WIFI");
            
            // Check if WiFi is already connected
            if (WiFi.status() == WL_CONNECTED) {
                Serial.println("WiFi connected successfully!");
                Serial.print("IP Address: ");
                Serial.println(WiFi.localIP());
                resetRetries(wifiAttempts, "WiFi");
                transitionToState(currentState, SYNC_NTP, stateStartTime, true); // New operation - reset timer
                break;
            }
            
            // Check if this is a new attempt or timeout
            if (wifiAttempts == 0 || checkTimeout(stateStartTime, WIFI_ATTEMPT_TIMEOUT_MS)) {
                if (checkAndIncrementRetries(wifiAttempts, MAX_WIFI_ATTEMPTS, "WiFi")) {
                    handleRestartWithReason(currentState, WIFI_TIMEOUT, restartLogger, ntpService);
                    break;
                }
                
                // Start new WiFi attempt
                Serial.print(" - Connecting to: ");
                Serial.println(WIFI_SSID);
                
                WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
                stateStartTime = currentTime; // Manual reset for new attempt timer
            } else {
                // Still waiting for current attempt
                Serial.print(".");
            }
            break;

        case SYNC_NTP:
            Serial.println("State: SYNC_NTP");
            
            // Initialize NTP service if this is the first attempt
            if (ntpAttempts == 0) {
                Serial.println("Initializing NTP Service...");
                ntpService.begin();
                ntpAttempts = 1;
                stateStartTime = currentTime;
            }
            
            // Try to update/sync NTP
            ntpService.update();
            
            // Check if NTP is now synchronized
            if (ntpService.isTimeSet()) {
                Serial.println("NTP sync successful!");
                Serial.print("Current UTC Time: ");
                Serial.println(ntpService.getFormattedISO8601Time());
                Serial.print("Current Epoch Time: ");
                Serial.println(ntpService.getEpochTime());
                resetRetries(ntpAttempts, "NTP");
                transitionToState(currentState, CONNECT_MQTT, stateStartTime, true); // New operation - reset timer
                break;
            }
            
            // Check for timeout on current attempt
            if (checkTimeout(stateStartTime, NTP_ATTEMPT_TIMEOUT_MS)) {
                if (checkAndIncrementRetries(ntpAttempts, MAX_NTP_ATTEMPTS, "NTP")) {
                    handleRestartWithReason(currentState, NTP_TIMEOUT, restartLogger, ntpService);
                    break;
                }
                
                // Start new NTP attempt
                Serial.println(" - Retrying...");
                stateStartTime = currentTime; // Manual reset for new attempt timer
            } else {
                // Still waiting for current attempt
                Serial.print("n"); // NTP attempt indicator
            }
            break;

        case CONNECT_MQTT:
            Serial.println("State: CONNECT_MQTT");
            
            if (mqttService.connectBroker()) {
                Serial.println("MQTT connected successfully!");
                setupSubscriptions(); // Subscribe to all actuator WRITE topics
                
                // Only publish boot status if we haven't already
                if (!bootStatusPublished) {
                    transitionToState(currentState, PUBLISH_BOOT_STATUS, stateStartTime);
                } else {
                    transitionToState(currentState, PROCESS_COMMANDS, stateStartTime);
                }
            } else {
                Serial.println("MQTT connection failed, retrying...");
                
                // Check for MQTT timeout (using constant from autogen_config.h)
                if (checkTimeout(stateStartTime, MQTT_CONNECT_TIMEOUT_MS)) {
                    handleRestartWithReason(currentState, MQTT_TIMEOUT, restartLogger, ntpService);
                } else {
                    transitionToState(currentState, CONNECT_MQTT, stateStartTime); // Stay in this state, keep timer
                    delay(MQTT_RETRY_DELAY_MS); // Retry delay from autogen_config.h
                }
            }
            break;

        case PUBLISH_BOOT_STATUS: {
            Serial.println("State: PUBLISH_BOOT_STATUS");
            
            // Always publish a restart reason - default to unknown if none stored
            PublishData bootStatus;
            if (restartLogger.hasStoredRestartReason()) {
                Serial.println("Found stored restart reason, creating publish data...");
                bootStatus = restartLogger.createPublishData(
                    ntpService,
                    TOPIC_C2_LastRestartReason_DATA,
                    UUID_C2_LastRestartReason_DATA
                );
            } else {
                Serial.println("No stored restart reason found, defaulting to unknown_reset");
                // Create PublishData for unknown restart reason
                String timestamp = ntpService.getFormattedISO8601Time();
                String reasonString = RestartReasonLogger::restartReasonToString(UNKNOWN_RESET);
                bootStatus = PublishData(
                    TOPIC_C2_LastRestartReason_DATA,
                    UUID_C2_LastRestartReason_DATA,
                    reasonString,
                    timestamp
                );
            }
            
            g_publishQueue.push(bootStatus);
            Serial.println("Restart reason queued for publishing");
            
            // Mark boot status as published and transition to normal operation
            bootStatusPublished = true;
            transitionToState(currentState, PROCESS_COMMANDS, stateStartTime);
            break;
        }

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
            
            // Check MQTT connection first - if not connected, transition to reconnect
            if (!mqttService.isConnected()) {
                Serial.println("MQTT not connected in PUBLISH_DATA state - transitioning to CONNECT_MQTT");
                transitionToState(currentState, CONNECT_MQTT, stateStartTime);
                break;
            }
            
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
            delay(RESTART_DELAY_MS);
            ESP.restart();
            break;

        default:
            Serial.println("Unknown state! Going to RESTART");
            currentState = RESTART;
            break;
    }

    // Periodically try to update NTP
    if (currentTime - lastNtpLoopUpdate >= NTP_LOOP_UPDATE_INTERVAL_MS) {
        if (ntpService.update()) {
            Serial.println("NTP update successful.");
        }
        lastNtpLoopUpdate = currentTime;
    }

    // Periodically print debug queue status
    if (currentTime - lastDebugPrint >= DEBUG_QUEUE_INTERVAL_MS) {
        printCommandQueueStatus();
        printPublishQueueStatus();
        lastDebugPrint = currentTime;
    }

    delay(MAIN_LOOP_DELAY_MS); 
} 