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

#define WIFI_SSID SECRET_WIFI_SSID
#define WIFI_PASSWORD SECRET_WIFI_PWD

#define SHT_ADDR 0x44
SCD4x SCD41;

bool enableHeater = false;
Adafruit_SHT31 sht = Adafruit_SHT31();

#define DHTPIN 35
#define DHTTYPE DHT22
DHT dht(DHTPIN, DHTTYPE);

// MQTT
const char* mqtt_server = "192.168.1.17";  // IP of the MQTT broker
const char* sht_humidity_topic = "mush/controller1/sht/humidity";
const char* sht_temperature_topic = "mush/controller1/sht/temperature";
const char* scd_humidity_topic = "mush/controller1/scd/humidity";
const char* scd_temperature_topic = "mush/controller1/scd/temperature";
const char* scd_co2_topic = "mush/controller1/scd/co2";
const char* dht_humidity_topic = "mush/controller1/dht/humidity";
const char* dht_temperature_topic = "mush/controller1/dht/temperature";
const char* mqtt_username = "ttfoley"; // MQTT username
const char* mqtt_password = "password"; // MQTT password
const char* clientID = "controller1"; // MQTT client ID


// Initialise the WiFi and MQTT Client objects
WiFiClient wifiClient;
PubSubClient client(mqtt_server, 1883, wifiClient);
void connect_MQTT();
void connect_WiFi();
float celsiusToFahrenheit(float celsius);

enum State {START, WIFI_CONNECT, MQTT_CONNECT, MQTT_PUBLISH, READ_SENSORS, WAIT, RESTART};
State state = START;
#define DEFAULT_WAIT 1000
#define WAIT_WAIT 10000
#define WIFI_WAIT 120000
#define MQTT_WAIT 10000


void setup() {
  Serial.begin(115200);
  delay(2000); //so I don't miss any messages from setup
  Serial.println("Hello from the setup");
  Serial.println("Connected");
  Serial.setTimeout(2000);
  Wire.begin();
  WiFi.mode(WIFI_STA);
  sht.begin(SHT_ADDR);
  dht.begin();
  delay(2000);
  if (! sht.begin(SHT_ADDR)) 
  {   
  Serial.println("Couldn't find SHT31");
  while (1) delay(1);
  }
  
  if (SCD41.begin(true,false) == false) //sets autocalibration false
  {
    Serial.println(F("SCD41 not detected. Please check wiring. Freezing..."));
    while (1);
  }

}

void loop() {

  client.loop();
  static unsigned long chrono;  // For timing in states (static means only initialized once?)
  static float sht_temperature;
  static float sht_humidity;
  static float dht_temperature;
  static float dht_humidity;
  static float scd_temperature;
  static float scd_humidity;
  static float scd_co2;
  static char tempString[16];
  static char printString[16];

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

      sht_humidity = sht.readHumidity();
      sht_temperature = celsiusToFahrenheit(sht.readTemperature());
      Serial.print("SHT Humidity: ");
      dtostrf(sht_humidity, 1, 2, printString);
      Serial.print(printString);
      Serial.print("\tSHT Temperature(F): ");
      dtostrf(sht_temperature, 1, 2, printString);
      Serial.print(printString);
      Serial.print("\n");
      
      //For DHT22
      dht_humidity = dht.readHumidity();
      dht_temperature = celsiusToFahrenheit(sht.readTemperature());
      Serial.print("DHT Humidity: ");
      dtostrf(dht_humidity, 1, 2, printString);
      Serial.print(printString);
      Serial.print("\tDHT Temperature(F): ");
      dtostrf(dht_temperature, 1, 2, printString);
      Serial.print(printString);
      Serial.print("\n");

      if (SCD41.readMeasurement()) // readMeasurement will return true when fresh data is available
      {
        scd_temperature = celsiusToFahrenheit(SCD41.getTemperature());
        scd_humidity = SCD41.getHumidity();
        scd_co2 = SCD41.getCO2();

        Serial.print(F("SCD CO2(ppm):"));
        dtostrf(scd_co2, 1, 2, printString);
        Serial.print(printString);

        Serial.print(F("\tSCD Temperature(F):"));
        dtostrf(scd_temperature, 1, 2, printString);
        Serial.print(printString);

        Serial.print(F("\tSCD Humidity(%RH):"));
        dtostrf(scd_humidity, 1, 2, printString);
        Serial.print(printString);

        Serial.println();
        state = MQTT_CONNECT;
        chrono = millis();
      }


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


      dtostrf(sht_temperature, 1, 2, tempString);
      if (client.publish(sht_temperature_topic, tempString)) 
      {
        Serial.println("SHT Temperature sent!");
      }
      dtostrf(sht_humidity, 1, 2, tempString);
      if (client.publish(sht_humidity_topic, tempString)) 
      {
        Serial.println("SHT Humidity sent!");
      }

      dtostrf(dht_temperature, 1, 2, tempString);
      if (client.publish(dht_temperature_topic, tempString)) 
      {
        Serial.println("DHT Temperature sent!");
      }
      dtostrf(dht_humidity, 1, 2, tempString);
      if (client.publish(dht_humidity_topic, tempString)) 
      {
        Serial.println("DHT Humidity sent!");
      }

      dtostrf(scd_humidity, 1, 2, tempString);
      if (client.publish(scd_humidity_topic, tempString)) 
      {
        Serial.println("SCD Humidity sent!");
      }
      
      dtostrf(scd_temperature, 1, 2, tempString);
      if (client.publish(scd_temperature_topic, tempString)) 
      {
        Serial.println("SCD Temperature sent!");
      }



      dtostrf(scd_co2, 1, 2, tempString);
      if (client.publish(scd_co2_topic, tempString)) 
      {
        Serial.println("SCD CO2 sent!");
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
  delay(10000);
  Serial.print("WiFi status: ");
  Serial.println(WiFi.status());
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