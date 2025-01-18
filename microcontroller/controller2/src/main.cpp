#include <Arduino.h>
#include "WiFi.h"
#include <secrets.h>
#include <OneWire.h>
#include <SPI.h>
#include "PubSubClient.h"
#include <SensirionCore.h>
#include "SparkFun_SCD4x_Arduino_Library.h"
#include <pincontrol.h>

#define WIFI_SSID SECRET_WIFI_SSID
#define WIFI_PASSWORD SECRET_WIFI_PWD


const int ledPin = 4;

// readbacks for the pins. when controller comes on, they start low. Only change if sent from mqtt.
//Floats for now because topic parsing in telegraf sucks.

const int pin_26 = 26;
const int pin_25 = 25;
const int pin_33 = 33;
const int pin_32 = 32;

// Create instances of PinControl
PinControl pinControls[] = {
    PinControl(ledPin, 0.0,-2.0, "led",  "mush/controller2/readback/led1", "mush/controller2/control/led1"),
    PinControl(26, 0.0,-2.0,"pin26", "mush/controller2/readback/pin26", "mush/controller2/control/pin26"),
    PinControl(25, 0.0,-2.0,"pin25", "mush/controller2/readback/pin25", "mush/controller2/control/pin25"),
    PinControl(33, 0.0,-2.0,"pin33", "mush/controller2/readback/pin33", "mush/controller2/control/pin33"),
    PinControl(32, 0.0,-2.0,"pin32", "mush/controller2/readback/pin32", "mush/controller2/control/pin32")
};

// MQTT
const char* mqtt_server = "192.168.1.17";  // IP of the MQTT broker



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
void write_delay(String content, PinControl& pinControl, int delay_time = 10);

enum State {START, WIFI_CONNECT, MQTT_CONNECT, MQTT_PUBLISH, RESTART};
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
  for (const auto& pinControl : pinControls) {
      pinMode(pinControl.pin, OUTPUT);
  }
  delay(2000);

  //MQTT setup
  client.setCallback(mqtt_callback);
}

void loop() {

  client.loop();


  static unsigned long chrono;  // For timing in states (static means only initialized once?)

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
        state = MQTT_CONNECT;
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
     //Note this has a side effect: If publish  succeeds, we'll update readback_last to be current. This is probably not optimal.
      Serial.println("State: MQTT_PUBLISH");
      for (auto& pinControl : pinControls) {
        if (pinControl.rb != pinControl.rb_last) {
          dtostrf(pinControl.rb, 1, 2, tempString);
          if (client.publish(pinControl.readback_topic, tempString)) 
          {
            Serial.println(tempString);
            Serial.println("Sent!");
            pinControl.setLastEqual();
            //If it succeeds, we'll update readback_last to be current. Note that in the meantime a new value could have been sent from mqtt
            //Meaning we'll miss this value by the next loop. PubSubClient doesn't keep a queue of messages, so unsent values are lost.
            //But it's very unlikely we'll receive new value in the meantime if the client is failing to publish.
          }
        }
      }
      
      chrono = millis();
      WIFI_CONNECT;
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
    SuscribeMqtt(); // only called once when connected
    // Subscribe
  } else {
    Serial.print("failed, rc=");
    Serial.print(client.state());
    delay(2000); //delays ok here because we can't possible receive message if client is borken
  }
}


void SuscribeMqtt()
//Ideally we'd keep track of what we're subscribed to and only subscribe when needed, 
{
  for (auto& pinControl : pinControls)
  {  client.subscribe(pinControl.output_topic);
  }
}

void mqtt_callback(char *topic, byte *payload, unsigned int length)
{
    // This takes action! write delay is called if matching topic is found, thereby updating pinControl.readback
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

    bool topic_found = false;
    for (auto& pinControl : pinControls)
    {
        if (str_output_topic == pinControl.output_topic)
        {
            write_delay(content, pinControl);
            topic_found = true;
            break;
        }
    }

    if (!topic_found)
    {
        Serial.println("Invalid topic");
    }
}


void write_delay(String content, PinControl& pinControl, int delay_time)
// This writes to pin (HIGH, LOW) and sets readback to (1, 0) depending on the content.
//The delay time was to give the give relay time to switch before we read back the value,
// but it really doesn't matter since we're not reading a physically manifested value, only a bad proxy.
{
  if (content == "on") 
  {
    digitalWrite(pinControl.pin, HIGH);
    pinControl.updateReadback(1.0);
    delay(delay_time);
  }
  else if (content == "off") 
  {
    digitalWrite(pinControl.pin, LOW);
    pinControl.updateReadback(-1.0);
    delay(delay_time);
  }
  else 
  {
    Serial.println("Invalid content");
  }
}