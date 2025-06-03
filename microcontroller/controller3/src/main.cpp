#include <Arduino.h>
#include "services/NtpService.h" // NTP service for timestamping
#include <WiFi.h>
#include "autogen_config.h" // For WiFi credentials and MQTT configuration
#include "utils/FsmUtils.h"
#include "sensors/SensorConfigs.h" // Sensor configuration structs
#include "utils/JsonBuilder.h" // For testing ADR-10 JSON payload construction
#include "services/MqttService.h" // For MQTT communication
#include "PublishData.h" // For publish queue
#include "services/RestartReasonLogger.h" // For persistent restart reason logging
#include "utils/FsmUtils.h" // For FSM utility functions
#include "sensors/SensorPoint.h" // Base sensor class
#include "sensors/SCD4xSensorPoint.h" // SCD4x sensor implementation (will handle all the complexity)
#include "utils/UniqueQueue.h" // For duplicate-free queue management
#include "utils/I2cUtils.h" // For I2C debugging utilities
#include "utils/SensorPublishQueue.h" // For sensor publish queue management
#include <Wire.h> // For I2C
#include <map>
#include <queue>
#include <set>
#include <vector>

// Use FsmUtils namespace for cleaner function calls
using namespace FsmUtils;

// =============================================================================
// SENSOR MANAGEMENT STRUCTURES
// =============================================================================

// Global vector to hold all sensor control points for this controller
std::vector<SensorPoint*> g_sensorPoints;

// Queue of sensors that need to be read (prevents duplicates)
UniqueQueue<SensorPoint*> g_sensorsToReadQueue;

// Global publish queue for all outgoing MQTT messages with sensor tracking
SensorPublishQueue g_publishQueue;

// =============================================================================
// FSM STATE MANAGEMENT (ADR-17, ADR-22)
// =============================================================================

FsmState currentState = SETUP_HW; // Start with hardware setup - consistent with controller1
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

// How often to run periodic maintenance checks (milliseconds)
unsigned long lastPeriodicCheck = 0;

void setupSensors() {
    Serial.println("Creating sensor instances...");
    
    // === I2C Sensors ===
    // SCD4x CO2/Temperature/Humidity Sensor (I2C address 0x62)
    // NOTE: This sensor is notoriously difficult and requires special handling
    // All the complexity (I2C resets, blocking measurements, delays) is encapsulated
    // in the SCD4xSensorPoint class implementation
    g_sensorPoints.push_back(new SCD4xSensorPoint(SCD4X_0_CONFIG));
    Serial.println("Created SCD4x sensor (FruitingChamber) - WARNING: This sensor requires special handling!");
    
    Serial.print("Total sensors created: ");
    Serial.println(g_sensorPoints.size());
}

void checkSensorsNeedingRead() {
    
    for (SensorPoint* sensor : g_sensorPoints) {
        // Check if sensor already has data waiting to publish
        if (!g_publishQueue.hasPendingData(sensor) && sensor->needToRead(millis())) {
            if (g_sensorsToReadQueue.tryEnqueue(sensor)) {
                Serial.println("Sensor queued for reading");
            }
            // If tryEnqueue returns false, sensor was already queued - no action needed
        }
    }
}

// =============================================================================
// DEBUG HELPER FUNCTIONS
// =============================================================================

void printPublishQueueStatus() {
    Serial.print("Publish queue size: ");
    Serial.println(g_publishQueue.size());
}

void printSensorStatus() {
    Serial.print("Total sensors: ");
    Serial.println(g_sensorPoints.size());
    Serial.print("Sensors to read queue: ");
    Serial.println(g_sensorsToReadQueue.size());
}

bool isWiFiConnected() {
    return WiFi.status() == WL_CONNECTED;
}

bool isMqttConnected() {
    return mqttService.isConnected();
}

void setup() {
    Serial.begin(115200);
    while (!Serial); // Wait for serial to connect (especially for some boards)
    Serial.println("\n\n--- Controller C3 (SCD4x CO2 Sensor Controller) Starting ---");

    // Hardware initialization only - connectivity handled by FSM
    setupSensors();
    
    Serial.println("Initializing MQTT Service...");
    mqttService.begin();// Sets server and callback, does not connect
    
    // Note: C3 doesn't need command management like C2 since it's sensor-only

    Serial.println("Setup complete. Entering main FSM loop...");
    Serial.println("FSM will handle: SETUP_HW -> WiFi -> NTP -> MQTT -> Boot Status -> Normal Operation");
    lastNtpLoopUpdate = millis(); // Initialize for loop updates
    lastDebugPrint = millis(); // Initialize debug timer
    stateStartTime = millis(); // Initialize state timing for first FSM state
}

void loop() {
    unsigned long currentTime = millis();

    mqttService.loop(); // Process MQTT messages and maintain connection
    // Always check for sensors needing to be read for better timing. Our awareness of when things should be read should not be dependent on the FSM. 
    checkSensorsNeedingRead();
    // Main FSM Logic
    switch (currentState) {
        case SETUP_HW:
            Serial.println("State: SETUP_HW");
            
            // Initialize I2C bus
            Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
            Serial.print("I2C initialized on SDA:");
            Serial.print(I2C_SDA_PIN);
            Serial.print(", SCL:");
            Serial.println(I2C_SCL_PIN);
            
            // Scan I2C bus to check for hardware issues (if enabled in config)
            #if DEBUG_I2C_SCAN_ON_STARTUP
            I2cUtils::scanI2CBus();
            #endif
            
            // Initialize all sensor hardware - fail fast on any failure
            // NOTE: SCD4x sensor initialization includes all the special handling:
            // - I2C communication test
            // - Stop periodic measurement
            // - Disable auto-calibration  
            // - Set single-shot measurement mode
            Serial.println("Initializing sensor hardware...");
            for (SensorPoint* sensor : g_sensorPoints) {
                if (!sensor->initialize()) {
                    Serial.println("CRITICAL: Sensor initialization failed - restarting controller");
                    handleRestartWithReason(currentState, SENSOR_INIT_FAILED, restartLogger, ntpService);
                    return; // Exit immediately, don't continue with loop
                }
            }
            
            Serial.println("All sensors initialized successfully");
            transitionToState(currentState, CONNECT_WIFI, stateStartTime);
            break;

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
                // Note: C3 doesn't need to subscribe to any topics since it's sensor-only
                
                // Only publish boot status if we haven't already
                if (!bootStatusPublished) {
                    transitionToState(currentState, PUBLISH_BOOT_STATUS, stateStartTime);
                } else {
                    transitionToState(currentState, READ_SENSORS, stateStartTime);
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
            // Always publish a restart reason - default to unknown if none stored
            PublishData bootStatus;
            if (restartLogger.hasStoredRestartReason()) {
                Serial.println("Found stored restart reason, creating publish data...");
                bootStatus = restartLogger.createPublishData(
                    ntpService,
                    TOPIC_C3_LastRestartReason_DATA,
                    UUID_C3_LastRestartReason_DATA
                );
            } else {
                Serial.println("No stored restart reason found, defaulting to unknown_reset");
                // Create PublishData for unknown restart reason
                String timestamp = ntpService.getFormattedISO8601Time();
                String reasonString = RestartReasonLogger::restartReasonToString(UNKNOWN_RESET);
                bootStatus = PublishData(
                    TOPIC_C3_LastRestartReason_DATA,
                    UUID_C3_LastRestartReason_DATA,
                    reasonString,
                    timestamp
                );
            }
            
            g_publishQueue.queueForPublish(bootStatus);
            Serial.println("Restart reason queued for publishing");
            
            // Mark boot status as published and transition to normal operation
            bootStatusPublished = true;
            transitionToState(currentState, READ_SENSORS, stateStartTime);
            break;
        }

        case READ_SENSORS:
            if (!g_sensorsToReadQueue.empty()) {
                SensorPoint* sensor = g_sensorsToReadQueue.dequeue();
                
                Serial.println("Reading sensor...");
                sensor->updateLastReadAttempt(currentTime);
                
                // Capture timestamp just before reading sensor
                String readTimestamp = ntpService.getFormattedISO8601Time();
                
                // NOTE: For SCD4x, the read() method will handle:
                // - I2C reset sequence (Wire.end() -> Wire.begin() -> scd4x.begin())
                // - 5-second blocking measureSingleShot() call
                // - Conservative delays and error handling
                // - Temperature conversion (C to F)
                // - All the sensor-specific complexity
                if (sensor->read(readTimestamp)) {  // Pass timestamp for sensor to store
                    Serial.println("Sensor read successful, packaging readings...");
                    auto readings = sensor->getAllReadings();
                    
                    for (const auto& reading : readings) {
                        PublishData pub(reading.topic, reading.uuid, reading.value, reading.timestamp, sensor);
                        g_publishQueue.queueForPublish(pub);
                        Serial.print("Queued: ");
                        Serial.print(reading.topic);
                        Serial.print(" = ");
                        Serial.println(reading.value);
                    }
                    
                    // DON'T update last publish time here - that should happen when MQTT actually publishes!
                } else {
                    Serial.println("Sensor read failed - will retry next cycle");
                }
                
                // Always transition to WAIT to let FSM decide what's next
                transitionToState(currentState, WAIT, stateStartTime);
            } else {
                // No sensors to read, go to publish what we have (if any) or wait
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
                PublishData item = g_publishQueue.dequeueForPublish();
                
                Serial.print("Publishing to ");
                Serial.print(item.topic);
                Serial.print(": ");
                Serial.print(item.serializedValue);
                Serial.print(" at ");
                Serial.println(item.timestampIsoUtc);
                
                // Publish via MQTT using publishJson with the raw value
                if (mqttService.publishJson(item.topic, item.timestampIsoUtc, item.uuid, item.serializedValue)) {
                    Serial.println("Publish successful!");
                    
                    // Update sensor last publish time for the specific sensor that provided this data
                    if (item.sourceSensor != nullptr) {
                        item.sourceSensor->updateLastPublishTime(millis());
                    }
                    g_publishQueue.markPublishComplete(item);
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

        case OPERATIONAL_PERIODIC_CHECKS:
            // Check for maintenance restart interval (millis() overflow prevention)
            if (currentTime >= MAINTENANCE_RESTART_INTERVAL_MS) {
                Serial.println("Maintenance restart interval reached - scheduling restart");
                // Store restart reason for next boot
                restartLogger.storeRestartReason(MAINTENANCE_RESTART, ntpService);
                transitionToState(currentState, RESTART, stateStartTime);
                break;
            }
            
            // TODO: Add other periodic maintenance tasks here:
            // - Memory usage checks
            // - Sensor health diagnostics
            // - WiFi signal strength monitoring
            // - MQTT connection quality checks
            
            Serial.println("Periodic checks complete - returning to normal operation");
            lastPeriodicCheck = currentTime;  // Update timestamp for next periodic check
            transitionToState(currentState, WAIT, stateStartTime);
            break;

        case WAIT:
            // Check connectivity first (highest priority)
            if (!isWiFiConnected()) {
                transitionToState(currentState, CONNECT_WIFI, stateStartTime);
            } else if (!isMqttConnected()) {
                transitionToState(currentState, CONNECT_MQTT, stateStartTime);
            }
            // Check for periodic maintenance tasks
            else if (currentTime - lastPeriodicCheck >= PERIODIC_CHECKS_INTERVAL_MS) {
                transitionToState(currentState, OPERATIONAL_PERIODIC_CHECKS, stateStartTime);
            }
            // Check for work to do
            else if (!g_publishQueue.empty()) {
                transitionToState(currentState, PUBLISH_DATA, stateStartTime);
            } else {
                // Check if any sensors need reading
                checkSensorsNeedingRead();
                if (!g_sensorsToReadQueue.empty()) {
                    transitionToState(currentState, READ_SENSORS, stateStartTime);
                } else {
                    // Nothing to do, explicitly stay in WAIT state
                    transitionToState(currentState, WAIT, stateStartTime);
                }
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
        printPublishQueueStatus();
        printSensorStatus();
        lastDebugPrint = currentTime;
    }

    delay(MAIN_LOOP_DELAY_MS); 
}
