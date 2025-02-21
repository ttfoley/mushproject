#include <Arduino.h>
#include <Wire.h>
#include "WiFi.h"
#include <PubSubClient.h>
#include <SensirionI2CScd4x.h>
#include "secrets.h"

// WiFi credentials from secrets.h
#define WIFI_SSID SECRET_WIFI_SSID
#define WIFI_PASSWORD SECRET_WIFI_PWD

// MQTT Configuration
const char* mqtt_server = "192.168.1.17";
const char* mqtt_username = "ttfoley";
const char* mqtt_password = "password";
const char* clientID = "controller3";

// Add MQTT topics near other constants
const char* mqtt_co2_topic = "mush/controllers/C3/sensors/scd_0/co2";
const char* mqtt_temp_topic = "mush/controllers/C3/sensors/scd_0/temperature";
const char* mqtt_humidity_topic = "mush/controllers/C3/sensors/scd_0/humidity";

// Timing constants
const unsigned long WIFI_RETRY_DELAY = 5000;      // 5 seconds between retries
const unsigned long MQTT_RETRY_DELAY = 5000;      // 5 seconds between MQTT connection attempts
const unsigned long MAX_TIME_NO_PUBLISH = 300000; // Restart if no publish for 5 minutes
const unsigned long MAX_WIFI_ATTEMPTS = 20;       // Maximum WiFi connection attempts before restart
const unsigned long MEASURE_TIME = 5000;  // Time to wait for measurement (5s)
const unsigned long MEASUREMENT_INTERVAL = 30000; // Time between measurements (30s)

// Initialize objects
SensirionI2CScd4x scd4x;
WiFiClient wifiClient;
PubSubClient mqttClient(mqtt_server, 1883, wifiClient);

// State machine definition
enum State {
    START,
    WIFI_CONNECTING,
    MQTT_CONNECTING,
    INIT_SENSOR,
    MEASURING,
    PUBLISH,
    WAIT,
    RESTART
};

State currentState = START;

// Function declarations
void setState(State newState);
const char* stateToString(State state);
bool initializeSCD4x();
bool connectWiFi();
float celsiusToFahrenheit(float celsius);
bool connectMQTT();

// Add to global variables
unsigned long lastPublishTime = 0;
uint8_t wifiAttempts = 0;
uint16_t co2;
float temperature;
float humidity;

void setup() {
    Serial.begin(115200);
    Wire.begin(21, 22);  // SDA = 21, SCL = 22
    Wire.setClock(100000);  // Set to 100kHz
    // Actually we DO want the internal pullups
    pinMode(21, INPUT_PULLUP);  // SDA
    pinMode(22, INPUT_PULLUP);  // SCL
    delay(2000);
    
    Serial.println("Controller3 starting up - SCD41 dedicated controller");
    currentState = START;
}

void loop() {
    mqttClient.loop();  // Add this at the start of loop
    static unsigned long stateTimer = 0;
    
    // Check for publish timeout
    if (millis() - lastPublishTime > MAX_TIME_NO_PUBLISH) {
        Serial.println("No successful publish for too long, restarting...");
        setState(RESTART);
    }
    
    switch(currentState) {
        case START:
            Serial.println("State: START");
            setState(INIT_SENSOR);
            break;
            
        case INIT_SENSOR:
            if (initializeSCD4x()) {
                Serial.println("SCD4x initialized successfully");
                setState(WIFI_CONNECTING);
            } else {
                Serial.println("Failed to initialize SCD4x, retrying...");
                delay(1000);
            }
            break;
            
        case WIFI_CONNECTING:
            if (WiFi.status() == WL_CONNECTED) {
                Serial.println("WiFi connected!");
                Serial.print("MAC address: ");
                Serial.println(WiFi.macAddress());
                Serial.print("IP address: ");
                Serial.println(WiFi.localIP());
                Serial.print("Signal strength: ");
                Serial.print(WiFi.RSSI());
                Serial.println(" dBm");
                wifiAttempts = 0;  // Reset counter on success
                setState(MQTT_CONNECTING);
            } else {
                static unsigned long lastAttempt = 0;
                if (millis() - lastAttempt >= WIFI_RETRY_DELAY) {
                    lastAttempt = millis();
                    wifiAttempts++;
                    if (wifiAttempts >= MAX_WIFI_ATTEMPTS) {
                        Serial.println("Max WiFi attempts reached, restarting...");
                        setState(RESTART);
                        break;
                    }
                    Serial.print("WiFi attempt ");
                    Serial.print(wifiAttempts);
                    Serial.print(" of ");
                    Serial.println(MAX_WIFI_ATTEMPTS);
                    connectWiFi();
                }
            }
            break;
            
        case MQTT_CONNECTING:
            if (WiFi.status() != WL_CONNECTED) {
                setState(WIFI_CONNECTING);
            } else {
                static unsigned long lastMqttAttempt = 0;
                if (millis() - lastMqttAttempt >= MQTT_RETRY_DELAY) {
                    lastMqttAttempt = millis();
                    Serial.println("Attempting MQTT connection...");
                    if (connectMQTT()) {
                        setState(WAIT);
                    }
                }
            }
            break;
            
        case MEASURING:
            {
                uint16_t error;
                
                // Reset I2C before trying
                Wire.end();
                delay(100);
                Wire.begin(21, 22);
                Wire.setClock(100000);
                delay(100);
                scd4x.begin(Wire);
                delay(1000);
                
                // Start the measurement
                error = scd4x.measureSingleShot();
                if (error) {
                    Serial.println("Failed to start measurement");
                    delay(2000);  // Add delay before returning to WAIT
                    setState(WAIT);
                    break;
                }
                
                // Conservative wait for measurement
                delay(2000);
                
                // Try reading once
                error = scd4x.readMeasurement(co2, temperature, humidity);
                if (!error && co2 != 0) {
                    temperature = celsiusToFahrenheit(temperature);
                    
                    Serial.print("Co2: ");
                    Serial.print(co2);
                    Serial.print(" ppm, Temp: ");
                    Serial.print(temperature);
                    Serial.print(" F, Humidity: ");
                    Serial.print(humidity);
                    Serial.println(" %");
                    
                    setState(PUBLISH);
                } else {
                    Serial.println("Failed to read measurement, returning to WAIT");
                    delay(2000);  // Add delay here too
                    setState(WAIT);
                }
            }
            break;
            
        case PUBLISH:
            if (!mqttClient.connected()) {
                setState(MQTT_CONNECTING);
                break;
            }
            
            // Publish all values
            mqttClient.publish(mqtt_co2_topic, String(co2).c_str());
            mqttClient.publish(mqtt_temp_topic, String(temperature).c_str());
            mqttClient.publish(mqtt_humidity_topic, String(humidity).c_str());
            
            lastPublishTime = millis();
            setState(WAIT);
            break;
            
        case WAIT:
            // Check connections first
            if (WiFi.status() != WL_CONNECTED) {
                setState(WIFI_CONNECTING);
                break;
            }
            if (!mqttClient.connected()) {
                setState(MQTT_CONNECTING);
                break;
            }
            
            // In periodic mode, just wait for MEASUREMENT_INTERVAL
            if (millis() - lastPublishTime >= MEASUREMENT_INTERVAL) {
                setState(MEASURING);
                break;
            }
            break;
            
        case RESTART:
            Serial.println("Restarting device...");
            delay(1000);
            ESP.restart();
            break;
        
        default:
            Serial.println("Unknown state!");
            delay(1000);
            break;
    }
}

void setState(State newState) {
    Serial.print("State transition: ");
    Serial.print(stateToString(currentState));
    Serial.print(" -> ");
    Serial.println(stateToString(newState));
    currentState = newState;
}

const char* stateToString(State state) {
    switch(state) {
        case START: return "START";
        case WIFI_CONNECTING: return "WIFI_CONNECTING";
        case MQTT_CONNECTING: return "MQTT_CONNECTING";
        case INIT_SENSOR: return "INIT_SENSOR";
        case MEASURING: return "MEASURING";
        case PUBLISH: return "PUBLISH";
        case WAIT: return "WAIT";
        case RESTART: return "RESTART";
        default: return "UNKNOWN";
    }
}

bool initializeSCD4x() {
    Serial.println("Attempting to begin SCD4x...");
    
    scd4x.begin(Wire);
    delay(1000);
    
    // Stop periodic measurement if it was running
    uint16_t error = scd4x.stopPeriodicMeasurement();
    delay(500);
    
    error = scd4x.setAutomaticSelfCalibration(0);
    if (error) {
        Serial.println("Failed to disable ASC");
        return false;
    }
    delay(500);
    
    return true;
}

bool connectWiFi() {
    if (WiFi.status() == WL_CONNECTED) return true;
    
    // Only disconnect if not already disconnected
    if (WiFi.status() != WL_DISCONNECTED) {
        WiFi.disconnect();
        delay(100);
    }
    
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    return WiFi.status() == WL_CONNECTED;
}

float celsiusToFahrenheit(float celsius) {
    return celsius * 9.0 / 5.0 + 32.0;
}

bool connectMQTT() {
    if (mqttClient.connected()) return true;
    
    Serial.print("Attempting MQTT connection...");
    if (mqttClient.connect(clientID, mqtt_username, mqtt_password)) {
        Serial.println("connected");
        return true;
    }
    Serial.print("failed, rc=");
    Serial.println(mqttClient.state());
    return false;
} 