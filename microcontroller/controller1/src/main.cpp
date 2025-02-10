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
#define DHT_0_PIN 4
#define DHT_0_TYPE DHT22

// MQTT
const char* mqtt_server = "192.168.1.17";  // IP of the MQTT broker
const char* mqtt_username = "ttfoley"; // MQTT username
const char* mqtt_password = "password"; // MQTT password
const char* clientID = "controller1"; // MQTT client ID
const long publish_frequency = 15000; // How often to publish sensor data (ms)

// Initialise the WiFi and MQTT Client objects
WiFiClient wifiClient;
PubSubClient client(mqtt_server, 1883, wifiClient);

bool connect_WiFi();
bool exceedMaxSensorPublishTime();
bool publishSensorData(Sensor* sensor);
bool connect_MQTT();
void tryPublishSensor(Sensor* sensor);

// Connection attempt configuration
#define MAX_WIFI_ATTEMPTS 12    // Total = attempt*delay
#define WIFI_ATTEMPT_DELAY 15000  // 
#define MAX_MQTT_ATTEMPTS 10      // total = attempt*delay
#define MQTT_ATTEMPT_DELAY 6000  // 

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

Sensor* sensors[] = { &sht_0_Sensor, &dht_0_Sensor, &scd_0_Sensor };

enum State {START, WIFI_CONNECT, WIFI_WAIT, MQTT_CONNECT, MQTT_WAIT, READ_AND_PUBLISH_SENSOR, MEASURING, WAIT, RESTART};
State state = START;
#define DEFAULT_WAIT 1000
#define WAIT_WAIT 10
#define MAX_TIME_NO_PUBLISH 60000 //failsafe in case a sensor breaks or something
#define MEASURE_TIME 5000 //time to measure SCD sensor

enum RestartReason {
    WIFI_TIMEOUT,
    MQTT_TIMEOUT,
    SENSOR_TIMEOUT,
    UNKNOWN
};

Preferences preferences;
const char* restart_topic = "mush/controllers/C1/status/last_restart_reason";

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
  delay(2000); //so I don't miss any messages from setup
  Serial.println("Hello from the setup");
  Serial.println("Connected");
  Serial.setTimeout(2000);
  Wire.begin();
  WiFi.mode(WIFI_STA);
  delay(2000);

  // Verify SCD sensor is last in array. Our publish timing depends on this. bad I know.
  if (sensors[sizeof(sensors)/sizeof(sensors[0]) - 1] != &scd_0_Sensor) {
    Serial.println("FATAL: SCD sensor must be last in sensors array for proper measurement timing");
    while(1) delay(1);
  }

  //more special care for stupid scd sensor
  scd_0_Sensor.setPublishFrequency(30000);

  // Initialize sensors
  if (!sht_0_Sensor.begin()) {
    Serial.println("Couldn't find SHT31 0");
    while (1) delay(1);
  }

  if (!dht_0_Sensor.begin()) {
    Serial.println("Couldn't find DHT22 0");
    while (1) delay(1);
  }

  if (!scd_0_Sensor.begin()) {
    Serial.println("Couldn't find SCD41 0");
    while (1) delay(1);
  }
}

void loop() {
  client.loop();

  if (WiFi.status() == WL_CONNECTED) {
    wifiConnectionDuration = millis() - wifiConnectedTime;
  }

  static unsigned long chrono;  // For timing in states (static means only initialized once?)

  static char tempString[16];
  static char printString[16];
  //If you switch states, reset chrono. This is like a transition action in statecharts
  switch (state) {
    case START:
      Serial.println("State: START");
      state = WIFI_CONNECT;
      chrono = millis();//This starts timer for wifi connection attempt, it's like a transition actions in statecharts
      break;

    case WIFI_CONNECT:
      Serial.println("State: WIFI_CONNECT");
      connect_WiFi();  // Just attempts connection, no delays
      state = WIFI_WAIT;
      chrono = millis();
      break;

    case WIFI_WAIT:
    /*
    This is a failsafe to ensure that the controller doesn't get stuck
    unfortunately, it has extra state via retry attempts.
    */
      static uint8_t wifi_attempts = 0;
      static unsigned long last_wifi_attempt = 0;
      
      if (WiFi.status() == WL_CONNECTED) {
        wifi_attempts = 0;  // Reset for next time
        state = MQTT_CONNECT;
        chrono = millis();
      }
      else if (millis() - last_wifi_attempt > WIFI_ATTEMPT_DELAY) {
        if (wifi_attempts < MAX_WIFI_ATTEMPTS) {
          connect_WiFi();
          wifi_attempts++;
          last_wifi_attempt = millis();
        } else {
          wifi_attempts = 0;
          storeRestartReason(WIFI_TIMEOUT);
          state = RESTART;
        }
      }
      break;

    case MQTT_CONNECT:
      //Serial.println("State: MQTT_CONNECT");
      if (client.connected()) {  
          state = READ_AND_PUBLISH_SENSOR;
          chrono = millis();
      } else {
          state = MQTT_WAIT;
          chrono = millis();
      }
      break;

    case MQTT_WAIT:
    /*
    This is a failsafe to ensure that the controller doesn't get stuck
    unfortunately, it has extra state via retry attempts.
    */
      static uint8_t mqtt_attempts = 0;
      static unsigned long last_mqtt_attempt = 0;
      
      if (client.connected()) {
        mqtt_attempts = 0;  // Reset for next time
        state = READ_AND_PUBLISH_SENSOR;
        chrono = millis();
      }
      else if (WiFi.status() != WL_CONNECTED) {
        mqtt_attempts = 0;  // Reset for next time
        state = WIFI_CONNECT;
        chrono = millis();
      }
      else if (millis() - last_mqtt_attempt > MQTT_ATTEMPT_DELAY) {
        if (mqtt_attempts < MAX_MQTT_ATTEMPTS) {
          connect_MQTT();
          mqtt_attempts++;
          last_mqtt_attempt = millis();
        } else {
          mqtt_attempts = 0;
          storeRestartReason(MQTT_TIMEOUT);
          state = RESTART;
        }
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
        if (sensors[i] == &scd_0_Sensor) {
          unsigned long time_since_publish = millis() - sensors[i]->getTimeLastPublished();
          unsigned long time_to_next_publish = sensors[i]->getPublishFrequency() - time_since_publish;
          
          if (scd_0_Sensor.isMeasuring()) {
            continue;  // Skip if currently measuring
          }
          else if (time_to_next_publish <= 5000) {  // Start measuring 5s before publish time
            state = MEASURING;
            chrono = millis();
            break;
          }
          else if (time_since_publish >= sensors[i]->getPublishFrequency()) {  // Time to publish
            tryPublishSensor(sensors[i]);
          }
        }
        else if (millis() - sensors[i]->getTimeLastPublished() > sensors[i]->getPublishFrequency()) {
          tryPublishSensor(sensors[i]);
        }
      }

      // Check if it's time to post wifiConnectionDuration
      if (millis() - lastWifiDurationPostTime > WIFI_DURATION_POST_INTERVAL) {
        char durationString[16];
        dtostrf(wifiConnectionDuration / 60000.0, 1, 2, durationString); // Convert to minutes
        if (client.publish(wifiTopic, durationString)) {
          Serial.print("WiFi connection duration: ");
          Serial.println(durationString);
          lastWifiDurationPostTime = millis();
        } else {
          Serial.println("Failed to publish WiFi connection duration");
        }
      }

      if (state != MEASURING) {
        state = WAIT;
        chrono = millis();
      }
      break;

    case MEASURING:
      //Serial.println("State: MEASURING");
      if (!scd_0_Sensor.isMeasuring()) {
        scd_0_Sensor.startMeasurement();  // Only start if not already measuring
      }
      if (millis() - chrono >= MEASURE_TIME) {
        scd_0_Sensor.completeMeasurement();
        state = WAIT;  // Go to WAIT like other states
        chrono = millis();
      }
      break;

    case WAIT:
      //Serial.println("State: WAIT");
      //Order is very important here!
      if (WiFi.status() != WL_CONNECTED) {
        state = WIFI_CONNECT;
        chrono = millis();
      } 
      else if (!client.connected()) {
        state = MQTT_CONNECT;
        chrono = millis();
      } 
      else if (millis() - chrono > WAIT_WAIT) {
        state = READ_AND_PUBLISH_SENSOR;
        chrono = millis();
      }
      else if (exceedMaxSensorPublishTime()) {
        storeRestartReason(SENSOR_TIMEOUT);
        state = RESTART;
      }
      else { //stay in this state, don't reset chrono.
        state = WAIT;
      }
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
    Serial.println("WiFi connected");
    Serial.print("IP address: ");
    Serial.println(WiFi.localIP());
    wifiConnectedTime = millis(); // Set timestamp when WiFi connects
    return true;
  }
  WiFi.disconnect();
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
  // Read and publish sensor data if available
  if (sensor->hasHumidity()) {
    float humidity = sensor->readHumidity();
    const char* topic = sensor->getHumidityTopic();
    if (client.publish(topic, String(humidity,2).c_str())) {
      Serial.print("Published humidity: ");
      Serial.print(humidity);
      Serial.print(" to topic: ");
      Serial.println(topic);
    } else {
      success = false;
    }
  }
  if (sensor->hasTemperature()) {
    float temperature = sensor->readTemperature();
    const char* topic = sensor->getTemperatureTopic();
    if (client.publish(topic, String(temperature,2).c_str())) {
      Serial.print("Published temperature: ");
      Serial.print(temperature);
      Serial.print(" to topic: ");
      Serial.println(topic);
    } else {
      success = false;
    }
  }
  if (sensor->hasCO2()) {
    float co2 = sensor->readCO2();
    const char* topic = sensor->getCO2Topic();
    if (client.publish(topic, String(co2,2).c_str())) {
      Serial.print("Published CO2: ");
      Serial.print(co2);
      Serial.print(" to topic: ");
      Serial.println(topic);
    } else {
      success = false;
    }
  }
  return success;
}

void tryPublishSensor(Sensor* sensor) {
    if (publishSensorData(sensor)) {
        sensor->resetTimeLastPublished();
    }
    else {
        Serial.print("Failed to publish sensor at topic root: ");
        Serial.println(sensor->getRootTopic());
    }
}