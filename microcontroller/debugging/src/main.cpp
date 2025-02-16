#include <Arduino.h>
#include <Wire.h>

void setup() {
  Serial.begin(115200);
  delay(2000);  // Give serial time to stabilize
  Serial.println("\n\nI2C Scanner Starting...");
  
  Wire.begin(21, 22);  // SDA = GPIO21, SCL = GPIO22 (typical ESP32 I2C pins)
  Serial.println("Wire.begin() completed");
  Serial.println("Starting scan loop...");
}

void loop() {
  byte error, address;
  int nDevices = 0;
  
  Serial.println("\n----------------------------------------");
  Serial.println("Scanning I2C bus...");
  
  for (address = 1; address < 127; address++) {
    Wire.beginTransmission(address);
    error = Wire.endTransmission();
    
    if (error == 0) {
      Serial.print("I2C device found at address 0x");
      if (address < 16) Serial.print("0");
      Serial.print(address, HEX);
      Serial.println();
      nDevices++;
    }
    else if (error == 4) {
      Serial.print("Unknown error at address 0x");
      if (address < 16) Serial.print("0");
      Serial.println(address, HEX);
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