#include <Arduino.h>
#include <Wire.h>

void setup() {
  Serial.begin(115200);
  delay(2000);  // Give serial time to stabilize
  Serial.println("\n\nI2C Scanner Starting...");
  
  Wire.begin();  // Use default pins (21, 22 on ESP32)
  Serial.println("Wire.begin() completed");
  Serial.println("Starting scan loop...");
}

void loop() {
  byte error, address;
  int nDevices = 0;
  
  Serial.println("\n----------------------------------------");
  Serial.println("Scanning I2C bus...");
  
  for (address = 1; address < 127; address++) {
    // Try multiple times to verify it's a real device
    bool deviceConfirmed = true;
    for(int tries = 0; tries < 3; tries++) {
      Wire.beginTransmission(address);
      error = Wire.endTransmission();
      if (error != 0) {
        deviceConfirmed = false;
        break;
      }
      delay(10);  // Small delay between tries
    }
    
    if (deviceConfirmed) {
      Serial.print("Verified I2C device at address 0x");
      if (address < 16) Serial.print("0");
      Serial.print(address, HEX);
      Serial.println();
      nDevices++;
    }
  }
  
  if (nDevices == 0) {
    Serial.println("No I2C devices found");
  } else {
    Serial.print("Found ");
    Serial.print(nDevices);
    Serial.println(" device(s)");
  }
  Serial.println("----------------------------------------\n");
  
  delay(5000);
}