#include <Arduino.h>
#include "services/NtpService.h" // NTP service for timestamping
#include <WiFi.h>
#include "autogen_config.h" // For WiFi credentials and MQTT configuration
#include "utils/JsonBuilder.h" // For testing ADR-10 JSON payload construction
#include "services/MqttService.h" // For MQTT communication
#include "actuators/ActuatorControlPoint.h" // For actuator management (updated path)
#include "PublishData.h" // For publish queue
#include "services/RestartReasonLogger.h" // For persistent restart reason logging
#include "utils/FsmUtils.h" // For FSM utility functions
#include <map>
#include <queue>
#include <set>
#include <vector>

// Use FsmUtils namespace for cleaner function calls
using namespace FsmUtils;

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

FsmState currentState = CONNECT_WIFI; // Start with WiFi connection - actuator setup is simple and done in setup()
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
    
    // Create ActuatorControlPoint instances using struct-based configuration (ADR-25)
    ActuatorControlPoint* humidifier = new ActuatorControlPoint(HUMIDIFIER_CONFIG);
    g_actuatorPoints.push_back(humidifier);
    g_topicToActuatorMap[String(HUMIDIFIER_CONFIG.write_topic)] = humidifier;
    Serial.println("Created humidifier actuator");
    
    ActuatorControlPoint* heatingpad = new ActuatorControlPoint(HEATINGPAD_CONFIG);
    g_actuatorPoints.push_back(heatingpad);
    g_topicToActuatorMap[String(HEATINGPAD_CONFIG.write_topic)] = heatingpad;
    Serial.println("Created heating pad actuator");
    
    ActuatorControlPoint* light = new ActuatorControlPoint(LIGHT_CONFIG);
    g_actuatorPoints.push_back(light);
    g_topicToActuatorMap[String(LIGHT_CONFIG.write_topic)] = light;
    Serial.println("Created light actuator");
    
    ActuatorControlPoint* ventfan = new ActuatorControlPoint(VENTFAN_CONFIG);
    g_actuatorPoints.push_back(ventfan);
    g_topicToActuatorMap[String(VENTFAN_CONFIG.write_topic)] = ventfan;
    Serial.println("Created vent fan actuator");
    
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
        // This respects the initial_state values from the struct configs
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
    
    // Subscribe to all actuator WRITE topics using struct configs
    for (ActuatorControlPoint* actuator : g_actuatorPoints) {
        const char* writeTopic = actuator->getWriteTopic();
        if (mqttService.subscribe(writeTopic)) {
            Serial.print("Subscribed to: "); Serial.println(writeTopic);
        } else {
            Serial.print("Failed to subscribe to: "); Serial.println(writeTopic);
        }
    }
    
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
                    // Stay in this state, keep timer - don't spam transitions  
                    transitionToState(currentState, CONNECT_MQTT, stateStartTime); // Stay in this state, keep timer
                    delay(MQTT_RETRY_DELAY_MS); // Retry delay from autogen_config.h
                }
            }
            break;

        case PUBLISH_BOOT_STATUS: {
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
                transitionToState(currentState, PUBLISH_DATA, stateStartTime);
            } else {
                // No commands to process, go to wait state
                transitionToState(currentState, WAIT, stateStartTime);
            }
            break;

        case PUBLISH_DATA:
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
                
                // Always transition to WAIT to let FSM decide what's next
                transitionToState(currentState, WAIT, stateStartTime);
            } else {
                // Nothing to publish, go to wait
                transitionToState(currentState, WAIT, stateStartTime);
            }
            break;

        case WAIT:
            // Check connectivity first (highest priority)
            if (!isWiFiConnected()) {
                transitionToState(currentState, CONNECT_WIFI, stateStartTime);
            } else if (!isMqttConnected()) {
                transitionToState(currentState, CONNECT_MQTT, stateStartTime);
            }
            // Check for work to do
            else if (!g_actuatorsToProcessQueue.empty()) {
                transitionToState(currentState, PROCESS_COMMANDS, stateStartTime);
            } else if (!g_publishQueue.empty()) {
                transitionToState(currentState, PUBLISH_DATA, stateStartTime);
            } else {
                // Check for periodic republishing (lowest priority)
                checkPeriodicRepublishing();
                // Explicitly stay in WAIT state
                transitionToState(currentState, WAIT, stateStartTime);
            }
            break;

        case RESTART:
            Serial.println("State: RESTART - Restarting controller...");
            delay(RESTART_DELAY_MS);
            ESP.restart();
            break;

        default:
            Serial.println("Unknown state! Going to RESTART");
            transitionToState(currentState, RESTART, stateStartTime);
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