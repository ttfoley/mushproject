#include <Arduino.h>
#include "WiFi.h"
#include <secrets.h>
#include <OneWire.h>
#include <Adafruit_Sensor.h>
#include <SPI.h>
#include "Adafruit_SHT31.h"
#include "PubSubClient.h"
#include <SensirionCore.h>
#include "SparkFun_SCD4x_Arduino_Library.h"
#include <DHT.h>
#include "calibration.h"
#include "sensor_structs.h"
#include "utils.h"
#include <Preferences.h>

#define WIFI_SSID SECRET_WIFI_SSID
#define WIFI_PASSWORD SECRET_WIFI_PWD

#define SHT_0_ADDR 0x44
#define DHT_0_PIN 27
#define DHT_0_TYPE DHT22
#define DS18B20_0_PIN 32  // First DS18B20 temperature sensor
#define DS18B20_1_PIN 33  // Second DS18B20 temperature sensor

// MQTT
const char* mqtt_server = "192.168.1.17";  // IP of the MQTT broker
const char* mqtt_username = "ttfoley"; // MQTT username
const char* mqtt_password = "password"; // MQTT password
const char* clientID = "controller1"; // MQTT client ID
const long publish_frequency = 15000; // How often to publish sensor data (ms)

// Initialise the WiFi and MQTT Client objects
WiFiClient wifiClient;
PubSubClient client(mqtt_server, 1883, wifiClient);

// After MQTT client setup, before function declarations
enum State {
    START, 
    WIFI_CONNECTING,
    MQTT_CONNECTING,
    READ_AND_PUBLISH_SENSOR,
    MEASURING_SCD,
    PUBLISH_SCD,
    WAIT, 
    RESTART
};

// Global state first
State state;

// Complete function declarations with full signatures
const char* stateToString(State state);
void setState(State newState, unsigned long& chronoRef, bool printTransition = true);

// Other function declarations
bool connect_WiFi();
bool exceedMaxSensorPublishTime();
bool publishSensorData(Sensor* sensor);
bool connect_MQTT();
void tryPublishSensor(Sensor* sensor);
void printWiFiStatus();

//Add near other constants at top of file
#define WIFI_DURATION_POST_INTERVAL 30000
unsigned long wifiConnectedTime = 0;
unsigned long wifiConnectionDuration = 0;
unsigned long lastWifiDurationPostTime = 0;
const char* wifiTopic = "mush/controllers/C1/sensors/status/wifi_uptime";

//Make sensors. The last arg is the sensor instance name for lookup in calibration map
//Should probably have topics in a map like the scaling, and include a name for the sensor instance to make
//it easier to find configurations (wouldn't need to add extra arguments to the sensor constructors)
SHTSensor sht_0_Sensor(SHT_0_ADDR, "mush/controllers/C1/sensors/sht_0/", getCalibrationParams("SHT_0"));
DHTSensor dht_0_Sensor(DHT_0_PIN, DHT_0_TYPE, "mush/controllers/C1/sensors/dht_0/", getCalibrationParams("DHT_0"));
SCDSensor scd_0_Sensor("mush/controllers/C1/sensors/scd_0/", getCalibrationParams("SCD_0"));
DS18B20Sensor ds18b20_0_Sensor(DS18B20_0_PIN, "mush/controllers/C1/sensors/ds18b20_0/", getCalibrationParams("DS18B20_0"));
//DS18B20Sensor ds18b20_1_Sensor(DS18B20_1_PIN, "mush/controllers/C1/sensors/ds18b20_1/", getCalibrationParams("DS18B20_1"));


// Update sensors array to include the working DS18B20
Sensor* sensors[] = { &sht_0_Sensor, &dht_0_Sensor, &ds18b20_0_Sensor, &scd_0_Sensor };

enum RestartReason {
    WIFI_TIMEOUT,
    MQTT_TIMEOUT,
    SENSOR_TIMEOUT,
    UNKNOWN
};

Preferences preferences;
const char* restart_topic = "mush/controllers/C1/sensors/status/last_restart_reason";

// Global pointer to SCD sensor
SCDSensor* scdSensor = nullptr;

// Move these implementations up, before any functions that use them
void setState(State newState, unsigned long& chronoRef, bool printTransition) {
    if (printTransition) {
        Serial.print("State transition: ");
        Serial.print(stateToString(state));
        Serial.print(" -> ");
        Serial.println(stateToString(newState));
    }
    state = newState;
    chronoRef = millis();
}

const char* stateToString(State state) {
    switch(state) {
        case START: return "START";
        case WIFI_CONNECTING: return "WIFI_CONNECTING";
        case MQTT_CONNECTING: return "MQTT_CONNECTING";
        case READ_AND_PUBLISH_SENSOR: return "READ_AND_PUBLISH_SENSOR";
        case MEASURING_SCD: return "MEASURING_SCD";
        case PUBLISH_SCD: return "PUBLISH_SCD";
        case WAIT: return "WAIT";
        case RESTART: return "RESTART";
        default: return "UNKNOWN";
    }
}

// Then the rest of the function implementations
void storeRestartReason(RestartReason reason) {
    preferences.begin("restart", false);
    preferences.putUInt("reason", reason);
    preferences.end();
}

void postStoredRestartReason() {
    if (!client.connected()) return;
    
    preferences.begin("restart", true);
    RestartReason reason = (RestartReason)preferences.getUInt("reason", UNKNOWN);
    preferences.end();
    
    const char* reason_str;
    switch(reason) {
        case WIFI_TIMEOUT: reason_str = "wifi_timeout"; break;
        case MQTT_TIMEOUT: reason_str = "mqtt_timeout"; break;
        case SENSOR_TIMEOUT: reason_str = "sensor_timeout"; break;
        default: reason_str = "unknown";
    }
    
    client.publish(restart_topic, reason_str, true);
}

void setup() {
  Serial.begin(115200);
  Wire.begin();
  //Wire.setClock(50000);  // Try 50kHz instead of default 100kHz
  state = START;  // Initialize here
  delay(2000); //so I don't miss any messages from setup
  Serial.println("Hello from the setup");
  Serial.println("Connected");
  Serial.setTimeout(2000);
  WiFi.mode(WIFI_STA);
  delay(2000);

  // Check for SCD sensors - there must be at most one, and if present it must be last
  bool foundSCD = false;
  for (size_t i = 0; i < sizeof(sensors)/sizeof(sensors[0]); i++) {
    if (sensors[i]->getType() == SensorType::SCD) {
      if (foundSCD) {
        Serial.println("FATAL: Only one SCD sensor allowed");
        while(1) delay(1);
      }
      if (i != sizeof(sensors)/sizeof(sensors[0]) - 1) {
        Serial.println("FATAL: SCD sensor must be last in sensors array");
        while(1) delay(1);
      }
      foundSCD = true;
      scdSensor = static_cast<SCDSensor*>(sensors[i]);
      scdSensor->setPublishFrequency(SCD_PUBLISH_INTERVAL);
    }
  }

  // Initialize all sensors with appropriate error messages
  for (size_t i = 0; i < sizeof(sensors)/sizeof(sensors[0]); i++) {
    if (!sensors[i]->begin()) {
      Serial.print("Couldn't find ");
      Serial.print(sensors[i]->getName());
      Serial.print(" (type: ");
      Serial.print(sensors[i]->getTypeString());
      Serial.println(")");
      while (1) delay(1);
    }
  }
}

void loop() {
  client.loop();

  if (WiFi.status() == WL_CONNECTED) {
    wifiConnectionDuration = millis() - wifiConnectedTime;
    //Serial.print("Current duration: ");
    //Serial.println(wifiConnectionDuration);
  }

  static unsigned long chrono;  // For timing in states (static means only initialized once?)

  static char tempString[16];
  static char printString[16];
  //If you switch states, reset chrono. This is like a transition action in statecharts
  switch (state) {
    case START:
      Serial.println("State: START");
      setState(WAIT, chrono);  // Let WAIT route us
      break;

    case WIFI_CONNECTING:
      static uint8_t wifi_attempts = 0;
      static unsigned long last_wifi_attempt = 0;
      static wl_status_t last_wifi_status = WL_DISCONNECTED;
      
      // Print status changes
      if (WiFi.status() != last_wifi_status) {
          Serial.print("WiFi status changed: ");
          switch(WiFi.status()) {
              case WL_CONNECTED: Serial.println("CONNECTED"); break;
              case WL_DISCONNECTED: Serial.println("DISCONNECTED"); break;
              case WL_IDLE_STATUS: Serial.println("IDLE"); break;
              case WL_NO_SSID_AVAIL: Serial.println("NO SSID"); break;
              case WL_SCAN_COMPLETED: Serial.println("SCAN COMPLETE"); break;
              case WL_CONNECT_FAILED: Serial.println("CONNECT FAILED"); break;
              case WL_CONNECTION_LOST: Serial.println("CONNECTION LOST"); break;
              default: Serial.println("UNKNOWN");
          }
          last_wifi_status = WiFi.status();
      }
      
      if (WiFi.status() == WL_CONNECTED) {
        printWiFiStatus();
        Serial.println("WiFi connected, resetting connection time");
        wifiConnectedTime = millis();
        Serial.print("Set wifiConnectedTime to: ");
        Serial.println(wifiConnectedTime);
        wifi_attempts = 0;
        setState(WAIT, chrono);
      }
      else if (wifi_attempts == 0 || millis() - last_wifi_attempt > WIFI_ATTEMPT_DELAY) {
        if (wifi_attempts < MAX_WIFI_ATTEMPTS) {
            connect_WiFi();
            wifi_attempts++;
            last_wifi_attempt = millis();
        } else {
            wifi_attempts = 0;
            storeRestartReason(WIFI_TIMEOUT);
            setState(RESTART, chrono, true);
        }
      }
      break;

    case MQTT_CONNECTING:
      static uint8_t mqtt_attempts = 0;
      static unsigned long last_mqtt_attempt = 0;
      
      if (client.connected()) {
        mqtt_attempts = 0;
        setState(WAIT, chrono);
      }
      else if (WiFi.status() != WL_CONNECTED) {
        mqtt_attempts = 0;
        setState(WAIT, chrono);  // WAIT will route us to WIFI_CONNECTING
      }
      else if (millis() - last_mqtt_attempt > MQTT_ATTEMPT_DELAY) {
        if (mqtt_attempts < MAX_MQTT_ATTEMPTS) {
          connect_MQTT();
          mqtt_attempts++;
          last_mqtt_attempt = millis();
        } else {
          mqtt_attempts = 0;
          storeRestartReason(MQTT_TIMEOUT);
          setState(RESTART, chrono, true);
        }
      }
      break;

    case WAIT:
        // Check this first to make sure we don't run into some loop with mqtt and wifi
        if (exceedMaxSensorPublishTime()) {
            storeRestartReason(SENSOR_TIMEOUT);
            setState(RESTART, chrono, true);
        }
        else if (WiFi.status() != WL_CONNECTED) {
            setState(WIFI_CONNECTING, chrono, true);
        }
        else if (!client.connected()) {
            setState(MQTT_CONNECTING, chrono, true);
        }
        else if (millis() - chrono > WAIT_WAIT) {
            setState(READ_AND_PUBLISH_SENSOR, chrono, false);
        }
        else if (scdSensor && scdSensor->timeToMeasure()) {
            setState(MEASURING_SCD, chrono, true);
        }
        break;

    case READ_AND_PUBLISH_SENSOR:
      static bool posted_restart_reason = false;
      
      if (!posted_restart_reason) {
          postStoredRestartReason();
          posted_restart_reason = true;
      }

      // Read and publish sensor data if available
      for (size_t i = 0; i < sizeof(sensors) / sizeof(sensors[0]); i++) {
        if (millis() - sensors[i]->getTimeLastPublished() > sensors[i]->getPublishFrequency()) {
            tryPublishSensor(sensors[i]);
        }
      }

      // Check if it's time to post wifiConnectionDuration
      if (millis() - lastWifiDurationPostTime > WIFI_DURATION_POST_INTERVAL) {
        char durationString[16];
        dtostrf(wifiConnectionDuration / 60000.0, 1, 2, durationString);
        if (client.publish(wifiTopic, durationString)) {
            Serial.print("WiFi connection duration: ");
            Serial.println(durationString);
            lastWifiDurationPostTime = millis();
        }
      }

      setState(WAIT, chrono, false);
      break;

    case MEASURING_SCD:
        static unsigned long last_debug_print = 0;
        
        if (!scdSensor->isMeasuring()) {
            if (scdSensor->startMeasurement()) {
                Serial.println("Started SCD measurement");
                last_debug_print = millis();
            } else {
                setState(WAIT, chrono, true);  // Failed to start, go back to WAIT
            }
        }
        else if (scdSensor->isDataReady() && scdSensor->readMeasurement()) {
            scdSensor->printMeasurementTime();
            setState(PUBLISH_SCD, chrono, true);
        }
        else if (millis() - last_debug_print > 10000) {  // Print every 10s
            Serial.print("In MEASURING_SCD state for: ");
            Serial.print((millis() - chrono));
            Serial.println("ms");
            last_debug_print = millis();
        }
        break;

    case PUBLISH_SCD:
        Serial.println("State: PUBLISH_SCD");
        delay(1000); // trying everything to make sure 
        tryPublishSensor(scdSensor);
        setState(WAIT, chrono, true);
        break;

    case RESTART:
      Serial.println("State: RESTART");
      delay(500);
      ESP.restart();
      break;    
  }
}


bool connect_WiFi() {
  if (WiFi.status() == WL_CONNECTED) {
    printWiFiStatus();
    return true;
  }
      // Only disconnect if in a bad state
  if (WiFi.status() != WL_DISCONNECTED) {
        Serial.print("Disconnecting from state: ");
        Serial.println(WiFi.status());
        WiFi.disconnect();
        delay(1000);  // 500ms for safer disconnect
  }
  Serial.println("Connecting to WiFi...");
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  return (WiFi.status() == WL_CONNECTED);
}

bool connect_MQTT() {
    if (client.connected()) {
        return true;
    }
    Serial.print("Attempting MQTT connection...");
    if (client.connect(clientID, mqtt_username, mqtt_password)) {
        Serial.println("connected");
        return true;
    }
    Serial.print("failed, rc=");
    Serial.println(client.state());
    return false;
}

bool exceedMaxSensorPublishTime() {
    for (size_t i = 0; i < sizeof(sensors) / sizeof(sensors[0]); i++) {
        unsigned long timeSinceLastPublish = millis() - sensors[i]->getTimeLastPublished();
        if (timeSinceLastPublish > MAX_TIME_NO_PUBLISH) {
            return true;
        }
    }
    return false;
}

bool publishSensorData(Sensor* sensor) {
    bool success = true;
    static const Sensor::MeasurementType types[] = {
        Sensor::MeasurementType::TEMPERATURE,
        Sensor::MeasurementType::HUMIDITY,
        Sensor::MeasurementType::CO2
    };

    for (const auto& type : types) {
        if (sensor->hasMeasurement(type)) {
            float value = sensor->read(type);
            const char* topic = sensor->getTopic(type);
            if (client.publish(topic, String(value,2).c_str())) {
                Serial.print("Published ");
                Serial.print(Sensor::getMeasurementTypeName(type));
                Serial.print(": ");
                Serial.print(value);
                Serial.print(" to topic: ");
                Serial.println(topic);
            } else {
                success = false;
            }
        }
    }
    return success;
}

void tryPublishSensor(Sensor* sensor) {
    if (publishSensorData(sensor)) {
        sensor->resetTimeLastPublished();
        delay(DELAY_AFTER_SENSOR_POST);//small delay to try to manage power spikes from transmitting
    }
    else {
        Serial.print("Failed to publish sensor at topic root: ");
        Serial.println(sensor->getRootTopic());
    }
}

void printWiFiStatus() {
    Serial.println("WiFi connected");
    Serial.print("MAC address: ");
    Serial.println(WiFi.macAddress());
    Serial.print("IP address: ");
    Serial.println(WiFi.localIP());
    Serial.print("Signal strength: ");
    Serial.print(WiFi.RSSI());
    Serial.println(" dBm");
}