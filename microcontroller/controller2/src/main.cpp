#include <Arduino.h>
#include "WiFi.h"
#include <secrets.h>
#include <OneWire.h>
#include <SPI.h>
#include "PubSubClient.h"
#include <SensirionCore.h>
#include "SparkFun_SCD4x_Arduino_Library.h"


#define WIFI_SSID SECRET_WIFI_SSID
#define WIFI_PASSWORD SECRET_WIFI_PWD

SCD4x SCD41;

const int ledPin = 4;

// MQTT
const char* mqtt_server = "192.168.1.17";  // IP of the MQTT broker
const char* scd_humidity_topic = "mush/controller2/scd/humidity";
const char* scd_temperature_topic = "mush/controller2/scd/temperature";
const char* scd_co2_topic = "mush/controller2/scd/co2";
const char* led1_output = "mush/controller2/control/led1";
const char* pin26_output = "mush/controller2/control/pin26";
const char* pin25_output = "mush/controller2/control/pin25";
const char* pin33_output = "mush/controller2/control/pin33";
const char* pin32_output = "mush/controller2/control/pin32";

const char* mqtt_username = "ttfoley"; // MQTT username
const char* mqtt_password = "password"; // MQTT password
const char* clientID = "controller2"; // MQTT client ID


// Initialise the WiFi and MQTT Client objects
WiFiClient wifiClient;
PubSubClient client(mqtt_server, 1883, wifiClient);

void connect_MQTT();
void connect_WiFi();
void mqtt_callback(char *topic, byte *payload, unsigned int length);
void SuscribeMqtt();
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
  Serial.println("Connected");
  Serial.setTimeout(2000);
  pinMode(ledPin, OUTPUT);
  pinMode(26, OUTPUT);
  pinMode(25, OUTPUT);
  pinMode(33, OUTPUT);
  pinMode(32, OUTPUT);
  delay(2000);
  Wire.begin();
  if (SCD41.begin() == false)
  {
    Serial.println(F("Sensor not detected. Please check wiring. Freezing..."));
    while (1)
      ;
  }

  //MQTT setup
  client.setCallback(mqtt_callback);
}

void loop() {

  client.loop();


  static unsigned long chrono;  // For timing in states (static means only initialized once?)
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
      if (SCD41.readMeasurement()) // readMeasurement will return true when fresh data is available
      {
        Serial.println("State: READ_SENSORS");
        scd_temperature = celsiusToFahrenheit(SCD41.getTemperature());
        scd_humidity = SCD41.getHumidity();
        scd_co2 = SCD41.getCO2();

        Serial.print(F("CO2(ppm):"));
        dtostrf(scd_co2, 1, 2, printString);
        Serial.print(printString);

        Serial.print(F("\tTemperature(F):"));
        dtostrf(scd_temperature, 1, 2, printString);
        Serial.print(printString);

        Serial.print(F("\tHumidity(%RH):"));
        dtostrf(scd_humidity, 1, 2, printString);
        Serial.print(printString);

        Serial.println();
        state = MQTT_CONNECT;
        chrono = millis();
      }
      else
      {
        Serial.print(F("Measurement not ready\n"));
        state = WAIT; // We'll try again in a bit
        delay(250); //just so we don't cycle wait-read too fast
      }    

      break;

    case MQTT_CONNECT:
      Serial.println("State: MQTT_CONNECT");
      if (client.connected())
      {
        SuscribeMqtt();
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


void SuscribeMqtt()
{
    client.subscribe("mush/controller2/control/led1");
    client.subscribe("mush/controller2/control/pin32");
    client.subscribe("mush/controller2/control/pin33");
    client.subscribe("mush/controller2/control/pin25");
    client.subscribe("mush/controller2/control/pin26");
}

void mqtt_callback(char *topic, byte *payload, unsigned int length)
{
    //TODO: make all this crap functions, check if pin in valid range and writable.
    //TODO: Should probably make a switch statement for the different pins/topics.
    int write_pin = -1;
    Serial.print("Received on ");
    Serial.print(topic);
    Serial.print(": ");

    String content = "";
    for (size_t i = 0; i < length; i++)
    {
        content.concat((char)payload[i]);
    }
    Serial.print(content);
    Serial.println();
    if (String(topic) == led1_output) 
    {
      write_pin = ledPin;
      Serial.print("Changing output to ");
      if (content == "on") {
        Serial.println("on");
        digitalWrite(write_pin, HIGH);
        delay(250);
      }
      else if (content == "off") {
        Serial.println("off");
        digitalWrite(write_pin, LOW);
        delay(250);
      }
    }

    else if (String(topic) == pin26_output) 
    {
      write_pin = 26;
      Serial.print("Changing output to ");
      if (content == "on") {
        Serial.println("on");
        digitalWrite(write_pin, HIGH);
        delay(250);
      }
      else if (content == "off") {
        Serial.println("off");
        digitalWrite(write_pin, LOW);
        delay(250);
      }
    }

    else if (String(topic) == pin25_output) 
    {
      write_pin = 25;
      Serial.print("Changing output to ");
      if (content == "on") {
        Serial.println("on");
        digitalWrite(write_pin, HIGH);
        delay(250);
      }
      else if (content == "off") {
        Serial.println("off");
        digitalWrite(write_pin, LOW);
        delay(250);
      }
    }

    else if (String(topic) == pin33_output) 
    {
      write_pin = 33;
      Serial.print("Changing output to ");
      if (content == "on") {
        Serial.println("on");
        digitalWrite(write_pin, HIGH);
        delay(250);
      }
      else if (content == "off") {
        Serial.println("off");
        digitalWrite(write_pin, LOW);
        delay(250);
      }
    }

    else if (String(topic) == pin32_output) 
    {
      write_pin = 32;
      Serial.print("Changing output to ");
      if (content == "on") {
        Serial.println("on");
        digitalWrite(write_pin, HIGH);
        delay(250);
      }
      else if (content == "off") {
        Serial.println("off");
        digitalWrite(write_pin, LOW);
        delay(250);
      }
    }
}