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
bool connect_MQTT();
bool connect_WiFi();
bool exceedMaxSensorPublishTime();
bool publishSensorData(Sensor* sensor);

//Make sensors. The last arg is the sensor instance name for lookup in calibration map
//Should probably have topics in a map like the scaling, and include a name for the sensor instance to make
//it easier to find configurations (wouldn't need to add extra arguments to the sensor constructors)
SHTSensor sht_0_Sensor(SHT_0_ADDR, "mush/controllers/C1/sensors/sht_0/humidity", "mush/controllers/C1/sensors/sht_0/temperature", getCalibrationParams("SHT_0"));
DHTSensor dht_0_Sensor(DHT_0_PIN, DHT_0_TYPE, "mush/controllers/C1/sensors/dht_0/humidity", "mush/controllers/C1/sensors/dht_0/temperature", getCalibrationParams("DHT_0"));
SCDSensor scd_0_Sensor("mush/controllers/C1/sensors/scd_0/humidity", "mush/controllers/C1/sensors/scd_0/temperature", "mush/controllers/C1/sensors/scd_0/co2", getCalibrationParams("SCD_0"));

Sensor* sensors[] = { &sht_0_Sensor, &dht_0_Sensor, &scd_0_Sensor };

enum State {START, WIFI_CONNECT, MQTT_CONNECT, READ_AND_PUBLISH_SENSOR, WAIT, RESTART};
State state = START;
#define DEFAULT_WAIT 1000
#define WAIT_WAIT 10
#define WIFI_WAIT 120000
#define MQTT_WAIT 10000
#define MQTT_CONNECT_WAIT 1000
#define WIFI_CONNECT_WAIT 5000
#define MAX_TIME_NO_PUBLISH 60000 //failsafe in case a sensor breaks or something


void setup() {
  Serial.begin(115200);
  delay(2000); //so I don't miss any messages from setup
  Serial.println("Hello from the setup");
  Serial.println("Connected");
  Serial.setTimeout(2000);
  Wire.begin();
  WiFi.mode(WIFI_STA);
  delay(2000);
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
        state = RESTART;
      }
      else { //stay in this state, don't reset chrono.
        state = WAIT;
      }
      break;

    case WIFI_CONNECT:
      Serial.println("State: WIFI_CONNECT");
      if (WiFi.status() == WL_CONNECTED) {
        state = MQTT_CONNECT;
        chrono = millis();
      } 
      else if (millis() - chrono < WIFI_WAIT) {
        /**This tries to connect to wifi in the background, but doesn't wait for it to connect, so it will always return false.
        On the next loop, if it's connected, it will be caught in the first if statement.
        */
        Serial.print("Last WiFi attempt failed, current status:");
        Serial.println(WiFi.status());
        connect_WiFi();
        delay(WIFI_CONNECT_WAIT); //give it time to try to connect
        if (WiFi.status() == WL_CONNECTED) {
          connect_WiFi(); //Will just print IP address
          /*Hack so we can see the IP address, still go back to WiFi_CONNECT state to not break the pattern.
          I could put the transition to MQTT_CONNECT here, but then it would be inside two if statements, breaking the pattern.
          */
        } 
        state = WIFI_CONNECT;

      } 
      else {
        state = RESTART;
      }
      break;


    case MQTT_CONNECT:
      Serial.println("State: MQTT_CONNECT");
      if (client.connected()) {
        state = READ_AND_PUBLISH_SENSOR;
        chrono = millis();
      } 

      else if (WiFi.status() != WL_CONNECTED) {
        //if we're not connected to wifi, we can't connect to MQTT
        state = WIFI_CONNECT;
        chrono = millis();
      } 

      else if (millis() - chrono < MQTT_WAIT) {
        /**  Try to connect to the MQTT broker. Even if this returns false (likely, not giving it any time to connect),
        it's trying to connect in the background.
        On next loop to MQTT_CONNECT, if it's connected it's caught in the first if statement.
        */
        Serial.print("Last attemp failed with code rc=");
        Serial.print(client.state());
        Serial.print("Attempting MQTT connection...");
        connect_MQTT();
        //give it time to try to connect
        delay(MQTT_CONNECT_WAIT);
        state = MQTT_CONNECT;
      } 

      else {
        //We've tried for too long, restart the board.
        state = RESTART;
      }

      break;


    case READ_AND_PUBLISH_SENSOR:
    /*Only reads and posts if time to update.
    Only resets publish time if successfuly published.
    */
      //Serial.println("State: READ_AND_PUBLISH_SENSOR");
      for (size_t i = 0; i < sizeof(sensors) / sizeof(sensors[0]); i++) {
        if (millis() - sensors[i]->getTimeLastPublished() > publish_frequency) {
          if (publishSensorData(sensors[i])) {
            sensors[i]->resetTimeLastPublished();
          } 
          else {
            Serial.println("Failed to publish sensor data");
          }
        }
      }
      state = WAIT;
      chrono = millis();
      break;



    case RESTART:
      Serial.println("State: RESTART");
      delay(500);
      ESP.restart();
      break;    
  }
}


bool connect_WiFi() {
  //With current construction, we never get to see IP address..
  // Connect to the WiFi

  //First check if we're already connected
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("WiFi connected");
    Serial.print("IP address: ");
    Serial.println(WiFi.localIP());
    return true;
  }
  else {
    WiFi.disconnect(); //advised to disconnect first.
    Serial.println("Connecting to WiFi...");
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    return (WiFi.status() == WL_CONNECTED); // This should always be false, since we're not giving it any time to connect.
  }
}

bool connect_MQTT() {
  if (client.connected()) {
    return true;
  }

  else {
    // Attempt to connect
    client.connect(clientID, mqtt_username, mqtt_password);
    return client.connected();//Since we're giving it no delay, this will basically never return true.
  }
}

bool exceedMaxSensorPublishTime() {
  for (size_t i = 0; i < sizeof(sensors) / sizeof(sensors[0]); i++) {
    if (millis() - sensors[i]->getTimeLastPublished() > MAX_TIME_NO_PUBLISH) {
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