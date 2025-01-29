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
SCD4x scd_0;

bool enableHeater = false;
Adafruit_SHT31 sht_0 = Adafruit_SHT31();

#define DHT_0_PIN 4
#define DHT_0_TYPE DHT22
DHT dht_0(DHT_0_PIN, DHT_0_TYPE);

// MQTT
const char* mqtt_server = "192.168.1.17";  // IP of the MQTT broker
const char* mqtt_username = "ttfoley"; // MQTT username
const char* mqtt_password = "password"; // MQTT password
const char* clientID = "controller1"; // MQTT client ID


// Initialise the WiFi and MQTT Client objects
WiFiClient wifiClient;
PubSubClient client(mqtt_server, 1883, wifiClient);
void connect_MQTT();
void connect_WiFi();
float celsiusToFahrenheit(float celsius);

SHTSensor sht_0_Sensor(SHT_0_ADDR, "mush/controllers/C1/sensors/sht_0/humidity", "mush/controllers/C1/sensors/sht_0/temperature", "SHT_0");
DHTSensor dht_0_Sensor(DHT_0_PIN, DHT_0_TYPE, "mush/controllers/C1/sensors/dht_0/humidity", "mush/controllers/C1/sensors/dht_0/temperature", "DHT_0");
SCDSensor scd_0_Sensor("mush/controllers/C1/sensors/scd_0/humidity", "mush/controllers/C1/sensors/scd_0/temperature", "mush/controllers/C1/sensors/scd_0/co2", "SCD_0");

Sensor* sensors[] = { &sht_0_Sensor, &dht_0_Sensor, &scd_0_Sensor };

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
  sht_0.begin(SHT0_ADDR);
  dht_0.begin();
  delay(2000);
  if (! sht_0.begin(SHT0_ADDR)) 
  {   
  Serial.println("Couldn't find SHT31");
  while (1) delay(1);
  }
  
  if (scd_0.begin(true,false) == false) //sets autocalibration false
  {
    Serial.println(F("scd_0 not detected. Please check wiring. Freezing..."));
    while (1);
  }

}

void loop() {

  client.loop();
  static unsigned long chrono;  // For timing in states (static means only initialized once?)
  static float sht_0_temperature;
  static float sht_0_humidity;
  static float dht_0_temperature;
  static float dht_0_humidity;
  static float scd_0_temperature;
  static float scd_0_humidity;
  static float scd_0_co2;
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
      delay(10000);
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

      sht_0_humidity = sht_0.readHumidity();
      sht_0_temperature = celsiusToFahrenheit(sht_0.readTemperature());
      Serial.print("SHT Humidity: ");
      dtostrf(sht_0_humidity, 1, 2, printString);
      Serial.print(printString);
      Serial.print("\tSHT Temperature(F): ");
      dtostrf(sht_0_temperature, 1, 2, printString);
      Serial.print(printString);
      Serial.print("\n");
      
      //For DHT0
      dht_0_humidity = dht_0.readHumidity() + DHT_HUMIDITY_OFFSET;
      dht_0_temperature = celsiusToFahrenheit(dht_0.readTemperature()) + DHT_TEMPERATURE_OFFSET;
      Serial.print("dht_0 Humidity: ");
      dtostrf(dht_0_humidity, 1, 2, printString);
      Serial.print(printString);
      Serial.print("\tdht_0 Temperature(F): ");
      dtostrf(dht_0_temperature, 1, 2, printString);
      Serial.print(printString);
      Serial.print("\n");

      if (scd_0.readMeasurement()) // readMeasurement will return true when fresh data is available
      {
        scd_0_temperature = celsiusToFahrenheit(scd_0.getTemperature());
        scd_0_humidity = scd_0.getHumidity();
        scd_0_co2 = scd_0.getCO2();

        Serial.print(F("SCD CO2(ppm):"));
        dtostrf(scd_0_co2, 1, 2, printString);
        Serial.print(printString);

        Serial.print(F("\tSCD Temperature(F):"));
        dtostrf(scd_0_temperature, 1, 2, printString);
        Serial.print(printString);

        Serial.print(F("\tSCD Humidity(%RH):"));
        dtostrf(scd_0_humidity, 1, 2, printString);
        Serial.print(printString);

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


      dtostrf(sht_0_temperature, 1, 2, tempString);
      if (client.publish(sht_0_temperature_topic, tempString)) 
      {
        Serial.println("SHT Temperature sent!");
      }
      dtostrf(sht_0_humidity, 1, 2, tempString);
      if (client.publish(sht_0_humidity_topic, tempString)) 
      {
        Serial.println("SHT Humidity sent!");
      }

      dtostrf(dht_0_temperature, 1, 2, tempString);
      if (client.publish(dht_0_temperature_topic, tempString)) 
      {
        Serial.println("dht_0 Temperature sent!");
      }
      dtostrf(dht_0_humidity, 1, 2, tempString);
      if (client.publish(dht_0_humidity_topic, tempString)) 
      {
        Serial.println("dht_0 Humidity sent!");
      }

      dtostrf(scd_0_humidity, 1, 2, tempString);
      if (client.publish(scd_0_humidity_topic, tempString)) 
      {
        Serial.println("SCD Humidity sent!");
      }
      
      dtostrf(scd_0_temperature, 1, 2, tempString);
      if (client.publish(scd_0_temperature_topic, tempString)) 
      {
        Serial.println("SCD Temperature sent!");
      }



      dtostrf(scd_0_co2, 1, 2, tempString);
      if (client.publish(scd_0_co2_topic, tempString)) 
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