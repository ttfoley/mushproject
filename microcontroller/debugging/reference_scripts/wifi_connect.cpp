#include "WiFi.h"
#include <secrets.h>

#define WIFI_SSID SECRET_WIFI_SSID
#define WIFI_PASSWORD SECRET_WIFI_PWD

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
  Serial.println("scan start");
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


void initWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("Connecting to WiFi ..");
  while (WiFi.status() != WL_CONNECTED) {
    Serial.print('.');
    delay(1000);
  }
  Serial.println(WiFi.localIP());
}

void connect_WiFi() {
  Serial.print("Connecting to ");
  Serial.println(WIFI_SSID);

  // Connect to the WiFi
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  delay(10000);
  if (WiFi.status() == WL_CONNECTED)
  {
    Serial.println("WiFi connected");
    Serial.print("IP address: ");
    Serial.println(WiFi.localIP());
    Serial.print("\n");
  }

}