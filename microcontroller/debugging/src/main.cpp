#include <Arduino.h>
#include <Wire.h>

// Define I2C pins - using common ESP32 defaults
#define I2C_SDA 21
#define I2C_SCL 22

void setup() {
    Serial.begin(115200);
    delay(2000);
    
    Serial.println("Starting I2C scan...");
    
    Wire.setPins(I2C_SDA, I2C_SCL);
    Wire.begin();
    Wire.setClock(100000);
    
    delay(1000);
    
    // Basic I2C scan
    byte found = 0;
    for(byte address = 1; address < 127; address++) {
        Wire.beginTransmission(address);
        byte error = Wire.endTransmission();
        if (error == 0) {
            Serial.print("Device found at address 0x");
            if (address < 16) Serial.print("0");
            Serial.println(address, HEX);
            found++;
        }
    }
    
    if (found == 0) {
        Serial.println("No I2C devices found");
    } else {
        Serial.print("Scan complete. Found ");
        Serial.print(found);
        Serial.println(" device(s)");
    }
}

void loop() {
    delay(5000);  // Scan every 5 seconds
    Serial.println("\nRescanning I2C bus...");
    
    byte found = 0;
    for(byte address = 1; address < 127; address++) {
        Wire.beginTransmission(address);
        byte error = Wire.endTransmission();
        if (error == 0) {
            Serial.print("Device found at address 0x");
            if (address < 16) Serial.print("0");
            Serial.println(address, HEX);
            found++;
        }
    }
    
    if (found == 0) {
        Serial.println("No I2C devices found");
    } else {
        Serial.print("Scan complete. Found ");
        Serial.print(found);
        Serial.println(" device(s)");
    }
}

