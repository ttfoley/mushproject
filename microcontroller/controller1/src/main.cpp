#include <Arduino.h>
#include "NtpService.h" // Assuming NtpService.h is in common_firmware_lib/include
                       // and common_firmware_lib is correctly linked.
#include <WiFi.h>
#include "autogen_config.h" // For WiFi credentials and MQTT configuration
#include "JsonBuilder.h" // For testing ADR-10 JSON payload construction
#include "MqttService.h" // For MQTT communication
#include "PublishData.h" // For publish queue
#include "RestartReasonLogger.h" // For persistent restart reason logging
#include "FsmUtils.h" // For FSM utility functions
#include "SensorPoint.h" // Base sensor class
#include "SHT85SensorPoint.h" // SHT85 sensor implementation
#include "SensorMacros.h" // Sensor creation macros
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

// Queue of sensors that need to be read
std::queue<SensorPoint*> g_sensorsToReadQueue;

// Global publish queue for all outgoing MQTT messages
std::queue<PublishData> g_publishQueue;

// =============================================================================
// FSM STATE MANAGEMENT (ADR-17, ADR-22)
// =============================================================================

FsmState currentState = SETUP_HW; // Start with hardware setup - consistent with controller2
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

void setupSensors() {
    Serial.println("Creating Sensor Point instances...");
    
    // Create I2C sensor instances using X-Macro pattern
    // Based on I2C_SENSOR_LIST from autogen_config.h
    #define X(name) CREATE_AND_ADD_I2C_SENSOR(name);
    I2C_SENSOR_LIST
    #undef X
    
    // TODO: Create DHT sensors using DHT_SENSOR_LIST
    // TODO: Create OneWire sensors using ONEWIRE_SENSOR_LIST
    
    Serial.print("Total sensors created: ");
    Serial.println(g_sensorPoints.size());
    Serial.println("Sensor creation complete. Hardware initialization will happen in SETUP_HW state.");
}

void checkSensorsNeedingRead() {
    unsigned long currentTime = millis();
    
    for (SensorPoint* sensor : g_sensorPoints) {
        if (sensor->needToRead(currentTime)) {
            g_sensorsToReadQueue.push(sensor);
            Serial.println("Sensor queued for reading");
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
    Serial.println("\n\n--- Controller C1 (Sensor Controller) Starting ---");

    // Hardware initialization only - connectivity handled by FSM
    setupSensors();
    
    Serial.println("Initializing MQTT Service...");
    mqttService.begin();// Sets server and callback, does not connect
    
    // Note: C1 doesn't need command management like C2 since it's sensor-only

    Serial.println("Setup complete. Entering main FSM loop...");
    Serial.println("FSM will handle: SETUP_HW -> WiFi -> NTP -> MQTT -> Boot Status -> Normal Operation");
    lastNtpLoopUpdate = millis(); // Initialize for loop updates
    lastDebugPrint = millis(); // Initialize debug timer
    stateStartTime = millis(); // Initialize state timing for first FSM state
}

void loop() {
    unsigned long currentTime = millis();

    mqttService.loop(); // Process MQTT messages and maintain connection

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
            
            // Initialize all sensor hardware - fail fast on any failure
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
                // Note: C1 doesn't need to subscribe to any topics since it's sensor-only
                
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
            Serial.println("State: PUBLISH_BOOT_STATUS");
            
            // Always publish a restart reason - default to unknown if none stored
            PublishData bootStatus;
            if (restartLogger.hasStoredRestartReason()) {
                Serial.println("Found stored restart reason, creating publish data...");
                bootStatus = restartLogger.createPublishData(
                    ntpService,
                    TOPIC_C1_LastRestartReason_DATA,
                    UUID_C1_LastRestartReason_DATA
                );
            } else {
                Serial.println("No stored restart reason found, defaulting to unknown_reset");
                // Create PublishData for unknown restart reason
                String timestamp = ntpService.getFormattedISO8601Time();
                String reasonString = RestartReasonLogger::restartReasonToString(UNKNOWN_RESET);
                bootStatus = PublishData(
                    TOPIC_C1_LastRestartReason_DATA,
                    UUID_C1_LastRestartReason_DATA,
                    reasonString,
                    timestamp
                );
            }
            
            g_publishQueue.push(bootStatus);
            Serial.println("Restart reason queued for publishing");
            
            // Mark boot status as published and transition to normal operation
            bootStatusPublished = true;
            transitionToState(currentState, READ_SENSORS, stateStartTime);
            break;
        }

        case READ_SENSORS:
            Serial.println("State: READ_SENSORS");
            
            if (!g_sensorsToReadQueue.empty()) {
                SensorPoint* sensor = g_sensorsToReadQueue.front();
                g_sensorsToReadQueue.pop();
                
                Serial.println("Reading sensor...");
                sensor->updateLastReadAttempt(currentTime);
                
                // Capture timestamp just before reading sensor
                String readTimestamp = ntpService.getFormattedISO8601Time();
                
                if (sensor->read(readTimestamp)) {  // Pass timestamp for sensor to store
                    Serial.println("Sensor read successful, packaging readings...");
                    auto readings = sensor->getAllReadings();
                    
                    for (const auto& reading : readings) {
                        PublishData pub(reading.topic, reading.uuid, reading.value, reading.timestamp);
                        g_publishQueue.push(pub);
                        Serial.print("Queued: ");
                        Serial.print(reading.topic);
                        Serial.print(" = ");
                        Serial.println(reading.value);
                    }
                    
                    sensor->updateLastPublishTime(currentTime);
                } else {
                    Serial.println("Sensor read failed - will retry next cycle");
                }
                
                // Check if there are more sensors to read
                if (!g_sensorsToReadQueue.empty()) {
                    currentState = READ_SENSORS; // Stay in this state
                } else {
                    currentState = PUBLISH_DATA; // Move to publish
                }
            } else {
                // No sensors to read, go to publish what we have (if any)
                currentState = PUBLISH_DATA;
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
                    
                    // TODO: Update sensor last publish time if needed
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
            else if (!g_publishQueue.empty()) {
                currentState = PUBLISH_DATA;
            } else {
                // Check if any sensors need reading
                checkSensorsNeedingRead();
                if (!g_sensorsToReadQueue.empty()) {
                    currentState = READ_SENSORS;
                } else {
                    // Nothing to do, stay in WAIT state
                    currentState = WAIT;
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
        printPublishQueueStatus();
        printSensorStatus();
        lastDebugPrint = currentTime;
    }

    delay(MAIN_LOOP_DELAY_MS); 
} 