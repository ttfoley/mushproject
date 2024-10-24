#include <Arduino.h>
#include "WiFi.h"
#include <secrets.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <DHT.h>
#include <Adafruit_Sensor.h>
#include <SPI.h>
#include "Adafruit_SHT31.h"
#include "PubSubClient.h"

#define LED_BUILTIN 2

#define WIFI_SSID SECRET_WIFI_SSID
#define WIFI_PASSWORD SECRET_WIFI_PWD

#define DHTPIN 14
#define DHTTYPE DHT11
#define SHT_ADDR 0x44
DHT dht(DHTPIN, DHTTYPE);

bool enableHeater = false;
Adafruit_SHT31 sht = Adafruit_SHT31();

// MQTT
const char* mqtt_server = "192.168.1.17";  // IP of the MQTT broker
const char* humidity_topic = "mush/test/humidity";
const char* temperature_topic = "mush/test/temperature";
const char* mqtt_username = "ttfoley"; // MQTT username
const char* mqtt_password = "password"; // MQTT password
const char* clientID = "esp32"; // MQTT client ID


// Initialise the WiFi and MQTT Client objects
WiFiClient wifiClient;
PubSubClient client(mqtt_server, 1883, wifiClient);
void connect_MQTT();
void connect_WiFi();
float celsiusToFahrenheit(float celsius);

enum State {START, WIFI_CONNECT, MQTT_CONNECT, MQTT_PUBLISH, READ_SENSORS, WAIT, RESTART};
State state = START;
#define DEFAULT_WAIT 1000
#define WAIT_WAIT 5000
#define WIFI_WAIT 10000
#define MQTT_WAIT 10000


void setup() {
  Serial.begin(115200);
  delay(2000); //so I don't miss any messages from setup
  Serial.println("Hello from the setup");
  pinMode(LED_BUILTIN,OUTPUT);
  Serial.println("Connected");
  Serial.setTimeout(2000);
  dht.begin();
  sht.begin(SHT_ADDR);
  delay(5000);
  if (! sht.begin(SHT_ADDR)) 
  {   
  Serial.println("Couldn't find SHT31");
  while (1) delay(1);
  }

}

void loop() {

  client.loop();
  static unsigned long chrono;  // For timing in states (static means only initialized once?)
  static float dht_temperature;
  static float dht_humidity;
  static float sht_temperature;
  static float sht_humidity;
  static char tempString[16];

  switch (state) {
    case START:
      Serial.println("State: START");
      state = WIFI_CONNECT;
      chrono = millis();//This starts timer for wifi connection attempt, it's like a transition actions in statecharts
      break;

    case WIFI_CONNECT:
      Serial.println("State: WIFI_CONNECT");
      connect_WiFi();
      if (WiFi.status() == WL_CONNECTED) 
      {
        state = READ_SENSORS;
        chrono = millis();
      }
      else if (millis() - chrono > WIFI_WAIT) //We've tried too many times, restarted the board
      {
        state = RESTART;
      }
      else // try to connect again
      {
        state = WIFI_CONNECT; //this doesn't do anything but just to be explicit. Note we don't restart timer.
      }
      break;

    case READ_SENSORS: 
    /*
    TODO: Make functions for the different sensors. 
    */
      Serial.println("State: READ_SENSORS");
      dht_humidity = dht.readHumidity();
      dht_temperature = dht.readTemperature(true);
      Serial.print("DHT Humidity: ");
      Serial.print(dht_humidity);
      Serial.print(" %\t");
      Serial.print("DHT Temperature(F): ");
      Serial.print(dht_temperature);
      Serial.print("\n");


      // sht_humidity = sht.readHumidity();
      // sht_temperature = celsiusToFahrenheit(sht.readTemperature());
      // Serial.print("SHT Humidity: ");
      // Serial.print(sht_humidity);
      // Serial.print(" %\t");
      // Serial.print("SHT Temperature(F): ");
      // Serial.print(sht_temperature);
      // Serial.print("\n");


      state = MQTT_CONNECT;
      chrono = millis();
      break;

    case MQTT_CONNECT:
      Serial.println("State: MQTT_CONNECT");
      if (client.connected())
      {
        state = MQTT_PUBLISH;
        chrono = millis();
      }
      else if (WiFi.status() != WL_CONNECTED) //Note we lose track of our data when we do this, restarts whole machine
      {
        state = WIFI_CONNECT;
        chrono = millis();
      }
      else if (millis() - chrono < MQTT_WAIT) // Try again if we haven't run out of time
      {
        connect_MQTT();
        state = MQTT_CONNECT; // just to be explicit
      }
      else  // We're out of time and tried everything, let's give up
      {
        state = RESTART;
      }
      break;

    case MQTT_PUBLISH: 
      /*
      If we made it here we were connected like 0.00001 seconds ago, not checking again
      */
      Serial.println("State: MQTT_PUBLISH");
      char tempString[16];
      dtostrf(dht_temperature, 1, 2, tempString);
      if (client.publish(temperature_topic, tempString)) 
      {
        Serial.println("Temperature sent!");
      }
      dtostrf(dht_humidity, 1, 2, tempString);
      if (client.publish(humidity_topic, tempString)) 
      {
        Serial.println("Humidity sent!");
      }
      chrono = millis();
      state = WAIT;
      break;

    case WAIT:
      //Serial.println("State: WAIT");
      if (millis() - chrono > WAIT_WAIT)
      {
        state = READ_SENSORS;
        chrono = millis();
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
  Serial.print("Connecting to ");
  Serial.println(WIFI_SSID);

  // Connect to the WiFi
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  delay(2000);
  if (WiFi.status() == WL_CONNECTED)
  {
    Serial.println("WiFi connected");
    Serial.print("IP address: ");
    Serial.println(WiFi.localIP());
    Serial.print("\n");
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
    delay(2000); //delays oh here because we can't possible receive message
  }
}

float celsiusToFahrenheit(float celsius) {
    return celsius * 9.0 / 5.0 + 32;
}