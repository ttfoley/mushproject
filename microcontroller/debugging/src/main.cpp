#include "WiFi.h"
#include <secrets.h>
#include <Wire.h>
#include <SPI.h>

#define WIFI_SSID SECRET_WIFI_SSID
#define WIFI_PASSWORD SECRET_WIFI_PWD


void connect_WiFi();


void setup() {
  Serial.begin(115200);

  // Set WiFi to station mode and disconnect from an AP if it was previously connected
  WiFi.mode(WIFI_STA);
  WiFi.disconnect();//I'm not sure either of these actually do anything
  delay(100);

  Serial.println("Setup done");
  connect_WiFi();
}


void loop() {

  if (WiFi.status() == WL_CONNECTED)
  {
    Serial.println("Still Connected");
  }
  else
  {
    Serial.println("Disconnected, trying to reconnect");
    WiFi.disconnect();//Really not sure this does anything.
    connect_WiFi();

  }
  delay(5000);
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