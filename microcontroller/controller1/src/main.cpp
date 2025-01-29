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
const long publish_frequency = 10000; // How often to publish sensor data (ms)

// Initialise the WiFi and MQTT Client objects
WiFiClient wifiClient;
PubSubClient client(mqtt_server, 1883, wifiClient);
void connect_MQTT();
void connect_WiFi();

//Make sensors. The last arg is the sensor instance name for lookup in calibration map
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
      } else if (!client.connected()) {
        state = MQTT_CONNECT;
        chrono = millis();
      } else if (millis() - chrono > WAIT_WAIT) {
        state = READ_AND_PUBLISH_SENSOR;
        chrono = millis();
      }
        else { //stay in this state, don't reset chrono.
        state = WAIT;
        }
      break;

    case WIFI_CONNECT:
      Serial.println("State: WIFI_CONNECT");
      if (WiFi.status() == WL_CONNECTED) 
      {
        state = WAIT;
        chrono = millis();
      }
      else if (millis() - chrono > WIFI_WAIT) //We've tried too many times, restart the board
      {
        state = RESTART;
      }
      else // try to connect again
      {
        connect_WiFi();
        //Give it time to connect
        delay(WIFI_CONNECT_WAIT);
        state = WIFI_CONNECT; //this doesn't do anything but just to be explicit. Note we don't restart timer.
        //don't reset chrono because we're going back to the same state
      }
      break;

    case READ_AND_PUBLISH_SENSOR:
      Serial.println("State: READ_AND_PUBLISH_SENSOR");
      for (size_t i = 0; i < sizeof(sensors) / sizeof(sensors[0]); i++) {
        if (millis() - sensors[i]->getTimeLastPublished() > publish_frequency) {
          // Read and publish sensor data if available
          if (sensors[i]->hasHumidity()) {
            float humidity = sensors[i]->readHumidity();
            client.publish(sensors[i]->getHumidityTopic(), String(humidity).c_str());
          }
          if (sensors[i]->hasTemperature()) {
            float temperature = sensors[i]->readTemperature();
            client.publish(sensors[i]->getTemperatureTopic(), String(temperature).c_str());
          }
          if (sensors[i]->hasCO2()) {
            float co2 = sensors[i]->readCO2();
            client.publish(sensors[i]->getCO2Topic(), String(co2).c_str());
          }

          // Update time_last_published
          sensors[i]->resetTimeLastPublished();
        }
      }
      state = WAIT;
      chrono = millis();
      break;

    case MQTT_CONNECT:
      Serial.println("State: MQTT_CONNECT");
      if (client.connected())
      {
        state = WAIT;
        chrono = millis();
      }
      else if (WiFi.status() != WL_CONNECTED) //Note we lose track of our data when we do this, restarts whole machine
      {
        //I don't know why I do this instead of going back to WAIT, I think it's more direct I guess.
        state = WIFI_CONNECT;
        chrono = millis();
      }
      else if (millis() - chrono < MQTT_WAIT) // Try again if we haven't run out of time
      {
        connect_MQTT();
        //Give it time to try to connect
        delay(MQTT_CONNECT_WAIT);
        //Should we add delay here, to give MQTT time to respond?
        state = MQTT_CONNECT; // just to be explicit
        //don't reset chrono because we're going back to same state
      }
      else  // We're out of time and tried everything, let's give up
      {
        state = RESTART;
      }
      break;



    case RESTART:
      Serial.println("State: RESTART");
      delay(500);
      ESP.restart();
      break;    
  }
}


void connect_WiFi() {

  if (WiFi.status() == WL_CONNECTED)
  {
    return;
  }
  else {
    WiFi.disconnect(); //advised to disconnect first.
    // Connect to the WiFi
    Serial.println("Connecting to WiFi...");
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    delay(5000);
    Serial.print("WiFi status: ");
    Serial.println(WiFi.status());
    if (WiFi.status() == WL_CONNECTED){
      Serial.println("WiFi connected");
      Serial.print("IP address: ");
      Serial.println(WiFi.localIP());
      Serial.print("\n");
    }
  }

}

void connect_MQTT() {
  Serial.print("Attempting MQTT connection...");
  // Attempt to connect
  if (client.connect(clientID, mqtt_username, mqtt_password)) {
    Serial.println("connected");
    // Subscribe
  } else {
    Serial.print("failed, rc=");
    Serial.print(client.state());
  }
}
