#include <Arduino.h>
#include "WiFi.h"
#include <secrets.h>
#include <OneWire.h>
#include <SPI.h>
#include "PubSubClient.h"
#include "pincontrol.h"

#define WIFI_SSID SECRET_WIFI_SSID
#define WIFI_PASSWORD SECRET_WIFI_PWD

//output pin definitions
const int pin_4 = 4; //I've been using this for LED on the board
const int pin_26 = 26;
const int pin_25 = 25;
const int pin_33 = 33;
const int pin_32 = 32;

// Create instances of PinControl
unsigned long initial_time = millis();
PinControl pinControls[] = {
    PinControl(pin_4, 0.0,0.0, "led",  "mush/controllers/C2/control_points/led1/readback", "mush/controllers/C2/control_points/led1/write",initial_time),
    PinControl(pin_26, 0.0, 0.0, "pin26", "mush/controllers/C2/control_points/CP_26/readback", "mush/controllers/C2/control_points/CP_26/write", initial_time),
    PinControl(pin_25, 0.0, 0.0, "pin25", "mush/controllers/C2/control_points/CP_25/readback", "mush/controllers/C2/control_points/CP_25/write", initial_time),
    PinControl(pin_33, 0.0, 0.0, "pin33", "mush/controllers/C2/control_points/CP_33/readback", "mush/controllers/C2/control_points/CP_33/write", initial_time),
    PinControl(pin_32, 0.0, 0.0, "pin32", "mush/controllers/C2/control_points/CP_32/readback", "mush/controllers/C2/control_points/CP_32/write", initial_time)
};
// readbacks for the pins. when controller comes on, they start low. Only change if sent from mqtt.
//Floats for now because topic parsing in telegraf sucks.
//I wish I passed pinControls to things like subscribeMQTT, but it looks like I need to add a whole new library to do that to get sizeof pinControls.

const size_t numPins = sizeof(pinControls) / sizeof(pinControls[0]);

// MQTT
const char* mqttServer = "192.168.1.17";  // IP of the MQTT broker
const char* mqttUsername = "ttfoley"; // MQTT username
const char* mqttPassword = "password"; // MQTT password
const char* clientID = "controller2"; // MQTT client ID


// Initialise the WiFi and MQTT Client objects
WiFiClient wifiClient;
PubSubClient client(mqttServer, 1883, wifiClient);

void connectWifi();
void connectMQTT(PinControl pinControls[], size_t numPins);
void mqttCallback(char *topic, byte *payload, unsigned int length);
void SubscribeMQTT(PinControl pinControls[], size_t numPins);
void writeDelay(String content, PinControl& pinControl, int delayTime = 10);
bool publishReadback(PinControl& pinControl);

//State machine states
enum State {START, WAIT, WIFI_CONNECT, MQTT_CONNECT, MQTT_PUBLISH, RESTART};
State state = START;

#define WAIT_WAIT 10
#define WIFI_WAIT 60000
#define MQTT_WAIT 10000
#define FORCE_REPUBLISH_FREQ 30000
#define WIFI_DURATION_POST_INTERVAL 60000
//Keep track of how long wifi has been connected
unsigned long wifiConnectedTime = 0;
unsigned long wifiConnectionDuration = 0;
unsigned long lastWifiDurationPostTime = 0;
const char* wifiTopic = "mush/controllers/C2/sensors/status/wifi_uptime";

String INITIAL_VALUE = "off"; //On startup, set all outputs off

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
  client.setCallback(mqttCallback);
}

/* 
  * It seems like the way arduino does things is via globals, so lots of globals are flying around here.
  * client.loop() starts the mqtt loops. The rest of the code is a state machine that basically keeps wifi and mqtt connecte, AND
  * Importantly, it also writes to controls points and posts that it's done so to mqtt.
*/
void loop() {

  client.loop();


  static unsigned long chrono;  // For timing in states (static means only initialized once?)
  static bool timesUp = false;

  if (WiFi.status() == WL_CONNECTED) {
    wifiConnectionDuration = millis() - wifiConnectedTime; // Calculate the duration of the WiFi connection
  }


  switch (state) {
    // This is the initial state, it sets all the pins to the initial value
    case START:
      Serial.println("State: START");
      for (auto& pinControl : pinControls)
      {
        writeDelay(INITIAL_VALUE, pinControl);
      }
      state = WIFI_CONNECT;
      chrono = millis();//This starts timer for wifi connection attempt, it's like a transition actions in statecharts
      break;

    //A convenience state, to decide where to go next based on the current state of the system with a little bit of time delay
    // It adds a state that's not really necessary, but it simplifies some other states
    case WAIT:
      //Serial.println("State: WAIT");
      if (WiFi.status() != WL_CONNECTED) 
      {
        state = WIFI_CONNECT;
      }
      else if (!client.connected()) 
      {
        state = MQTT_CONNECT;
      }
      else 
      {
        state = MQTT_PUBLISH;
      }
      break;

    case WIFI_CONNECT:
      Serial.println("State: WIFI_CONNECT");
      connectWifi();
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
        connectMQTT(pinControls, numPins);
        state = MQTT_CONNECT; // just to be explicit
      }
      else  // We're out of time and tried everything, let's give up
      {
        state = RESTART;
      }
      break;

    /*
     *Checks if changed value or republish time up, publishes if so
     *If we made it here we were connected like 0.00001 seconds ago, not checking again.
     *Note this has a side effect: If publish  succeeds, we'll update readback_last to be current. This just seems to be the way things are done in MQTT land.
    */
    case MQTT_PUBLISH: 
      //Serial.println("State: MQTT_PUBLISH");
      for (auto& pinControl : pinControls) {
          // Check if it's time to republish
          pinControl.checkTimeToRepublish(FORCE_REPUBLISH_FREQ);
          
          if (pinControl.needs_publish) {
              if (publishReadback(pinControl)) {
                  pinControl.publishComplete();
              }
          }
      }
      // Check if it's time to post wifiConnectionDuration
      if (millis() - lastWifiDurationPostTime > WIFI_DURATION_POST_INTERVAL) {
        char durationString[16];
        dtostrf(wifiConnectionDuration / 60000.0, 1, 2, durationString); // Convert to minutes
        if (client.publish(wifiTopic, durationString)) {
          Serial.print("WiFi connection duration: ");
          Serial.println(durationString);
          lastWifiDurationPostTime = millis(); // Update the last post time
        } else {
          Serial.println("Failed to publish WiFi connection duration");
        }
      }

      chrono = millis();
      state = WAIT;
      break;


    case RESTART:
      Serial.println("State: RESTART");
      delay(500);
      ESP.restart();
      break;    
  }
}


void connectWifi() {
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
    wifiConnectedTime = millis(); // Set the timestamp when WiFi is connected
  }

}

void connectMQTT(PinControl pinControls[], size_t numPins) {
  Serial.print("Attempting MQTT connection...");
  // Attempt to connect
  if (client.connect(clientID, mqttUsername, mqttPassword)) {
    Serial.println("connected");
    SubscribeMQTT(pinControls, numPins); // only called once when connected
  } else {
    Serial.print("failed, rc=");
    Serial.print(client.state());
    delay(2000); //delay's ok here because we can't possible receive message if client is borken
  }
}

//Subscribes to all of the topics in pinControls
void SubscribeMQTT(PinControl pinControls[], size_t numPins){
  for (size_t i = 0; i < numPins; ++i) {
    client.subscribe(pinControls[i].output_topic);
  }
}


/*
 * This takes action! write delay is called if matching topic is found, it writeDelay is called, writing to the point and updating readback.
 */ 
void mqttCallback(char *topic, byte *payload, unsigned int length)
{
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
            writeDelay(content, pinControl);
            topic_found = true;
            break;
        }
    }

    if (!topic_found)
    {
        Serial.println("Invalid topic");
    }
}

/*
 * This writes to pin (HIGH, LOW) and sets readback to (1.0, -1.0) depending on the content. Nothing else can change the outputs.
 * The delay time was to give the relay time to switch before we read back the value,
 * but it really doesn't matter since we're not reading a physically manifested value, only a bad proxy.
 */
void writeDelay(String content, PinControl& pinControl, int delayTime)
{
  if (content == "on") 
  {
    digitalWrite(pinControl.pin, HIGH);
    pinControl.updateReadback(1.0);
    delay(delayTime);
  }
  else if (content == "off") 
  {
    digitalWrite(pinControl.pin, LOW);
    pinControl.updateReadback(-1.0);
    delay(delayTime);
  }
  else 
  {
    Serial.println("Invalid content");
  }
}

/*
  * This publishes the readback value to the readback topic. If successful, it updates the last readback value to be current.
  * This is the only way to update the readback value.
  * 
*/
bool publishReadback(PinControl& pinControl) {
    char tempString[16];
    dtostrf(pinControl.rb, 1, 2, tempString);
    if (client.publish(pinControl.readback_topic, tempString)) {
        Serial.println(tempString);
        Serial.println("Sent!");
        return true;
    }
    return false;
}
/* If it succeeds, we'll update readback_last to be current. Note that in the meantime a new value could have been sent from MQTT,
* meaning we'll miss this value by the next loop. PubSubClient doesn't keep a queue of messages, so unsent values are lost.
* But it's very unlikely we'll receive a new value in the meantime if the client is failing to publish.
*/