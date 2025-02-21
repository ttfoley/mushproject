#include <Arduino.h>
#include <Wire.h>
#include <SensirionI2CScd4x.h>

SensirionI2CScd4x scd4x;

void setup() {
    Serial.begin(115200);
    delay(2000);
    
    Serial.println("Initializing...");
    
    Wire.setPins(SDA, SCL);
    Wire.begin();
    Wire.setClock(10000);
    
    delay(1000);
    Serial.println("I2C initialized");
    
    // Basic I2C scan
    Serial.println("Scanning I2C bus...");
    for(byte address = 1; address < 127; address++) {
        Wire.beginTransmission(address);
        byte error = Wire.endTransmission();
        if (error == 0) {
            Serial.print("Device found at address 0x");
            Serial.println(address, HEX);
        }
    }
    
    // Now try sensor init with longer delays
    Serial.println("Starting sensor init...");
    scd4x.begin(Wire);
    delay(2000);  // Longer delay after begin
    
    Serial.println("Attempting first command...");
    uint16_t error = scd4x.stopPeriodicMeasurement();
    if (error) {
        Serial.println("Warning: Could not stop measurement - continuing anyway");
    }
    delay(2000);
    
    Serial.println("Init complete - starting measurements");
}

void resetI2C() {
    Wire.end();
    delay(100);
    Wire.setPins(SDA, SCL);
    Wire.begin();
    Wire.setClock(10000);
    delay(100);
}

void loop() {
    uint16_t error;
    uint16_t co2;
    float temperature;
    float humidity;
    
    Serial.println("\nStarting new measurement...");
    
    resetI2C();
    delay(500);
    scd4x.begin(Wire);
    delay(1000);
    
    error = scd4x.measureSingleShot();
    if (error) {
        Serial.println("Failed to start measurement");
        delay(5000);
        return;
    }
    Serial.println("Measurement started");
    
    delay(2000);
    
    // Keep trying until we get a valid reading
    while(true) {
        error = scd4x.readMeasurement(co2, temperature, humidity);
        if (!error && co2 != 0) {
            Serial.print("Success - Co2: ");
            Serial.print(co2);
            Serial.print(" ppm\t");
            Serial.print("Temperature: ");
            Serial.print(temperature);
            Serial.print(" C\t");
            Serial.print("Humidity: ");
            Serial.print(humidity);
            Serial.println(" %");
            break;  // Got valid reading, exit loop
        }
        delay(1000);  // Wait before retry
    }
    
    delay(15000);
}

