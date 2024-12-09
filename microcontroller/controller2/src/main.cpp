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

// readbacks for the pins. when controller comes on, they start low. Only change if sent from mqtt.
//Floats for now because topic parsing in telegraf sucks.
float ledPin_rb = 0;
float pin26_rb = 0;
float pin25_rb = 0;
float pin33_rb = 0;
float pin32_rb = 0; 

// MQTT
const char* mqtt_server = "192.168.1.17";  // IP of the MQTT broker
const char* scd_humidity_topic = "mush/controller2/scd/humidity";
const char* scd_temperature_topic = "mush/controller2/scd/temperature";
const char* scd_co2_topic = "mush/controller2/scd/co2";
const char* led1_output_topic = "mush/controller2/control/led1";
const char* pin26_output_topic = "mush/controller2/control/pin26";
const char* pin25_output_topic = "mush/controller2/control/pin25";
const char* pin33_output_topic = "mush/controller2/control/pin33";
const char* pin32_output_topic = "mush/controller2/control/pin32";
const char* led1_readback_topic = "mush/controller2/readback/led1";
const char* pin26_readback_topic = "mush/controller2/readback/pin26";
const char* pin25_readback_topic = "mush/controller2/readback/pin25";
const char* pin33_readback_topic = "mush/controller2/readback/pin33";
const char* pin32_readback_topic = "mush/controller2/readback/pin32";


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
void write_delay(String content, int write_pin, float readback, int delay_time=250);

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

      dtostrf(ledPin_rb, 1, 2, tempString);
      if (client.publish(led1_readback_topic, tempString)) 
      {
        Serial.println("LED RB sent!");
      }

      dtostrf(pin25_rb, 1, 2, tempString);
      if (client.publish(pin25_readback_topic, tempString)) 
      {
        Serial.println("Pin25 RB sent!");
      }

      dtostrf(pin26_rb, 1, 2, tempString);
      if (client.publish(pin26_readback_topic, tempString)) 
      {
        Serial.println("Pin26 RB sent!");
      }
      dtostrf(pin33_rb, 1, 2, tempString);  
      if (client.publish(pin33_readback_topic, tempString)) 
      {
        Serial.println("Pin33 RB sent!");
      }
      dtostrf(pin32_rb, 1, 2, tempString);
      if (client.publish(pin32_readback_topic, tempString)) 
      {
        Serial.println("Pin32 RB sent!");
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
    Serial.print("Received on ");
    Serial.print(topic);
    Serial.print(": ");

    String content = "";
    String str_output_topic = String(topic);

    for (size_t i = 0; i < length; i++)
    {
        content.concat((char)payload[i]);
    }

    Serial.print(content);
    Serial.println();

    if (str_output_topic == led1_output_topic) 
    {
      write_delay(content, ledPin, ledPin_rb); 
    }

    else if (str_output_topic == pin25_output_topic) 
    {
      write_delay(content, 25, pin25_rb); 
    }
    else if (str_output_topic == pin26_output_topic) 
    {
      write_delay(content, 26, pin26_rb); 
    }
    else if (str_output_topic == pin33_output_topic) 
    {
      write_delay(content, 33, pin33_rb); 
    }
    else if (str_output_topic == pin32_output_topic) 
    {
      write_delay(content, 32, pin32_rb); 
    }
    else 
    {
      Serial.println("Invalid topic");
    }

}


void write_delay(String content, int write_pin, float readback, int delay_time)
//This writes to pin (HIGH,LOW) and sets readback to (1,0) depending on the content.
{
  if (content == "on") 
  {
    digitalWrite(write_pin, HIGH);
    readback = 1;
    delay(delay_time);
  }
  else if (content == "off") 
  {
    digitalWrite(write_pin, LOW);
    readback = 0;
    delay(delay_time);
  }
  else 
  {
    Serial.println("Invalid command");
  }
}