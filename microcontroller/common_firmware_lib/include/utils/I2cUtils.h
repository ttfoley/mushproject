#ifndef I2C_UTILS_H
#define I2C_UTILS_H

#include <Wire.h>
#include <Arduino.h>

/**
 * @file I2cUtils.h
 * @brief Utility functions for I2C bus operations and debugging
 * 
 * This header provides common I2C utilities that can be used across
 * all microcontrollers for debugging and troubleshooting I2C issues.
 */

namespace I2cUtils {

/**
 * @brief Scan the I2C bus for connected devices
 * 
 * Scans I2C addresses from 0x08 to 0x77 and reports any devices found.
 * Useful for debugging I2C connectivity issues and verifying sensor hardware.
 * Should be called after Wire.begin() has been called.
 */
void scanI2CBus() {
    Serial.println("=== I2C Bus Scanner ===");
    Serial.println("Scanning I2C bus for devices...");
    
    int deviceCount = 0;
    
    for (byte address = 0x08; address <= 0x77; address++) {
        Wire.beginTransmission(address);
        byte error = Wire.endTransmission();
        
        if (error == 0) {
            Serial.print("Device found at address 0x");
            if (address < 16) Serial.print("0");
            Serial.print(address, HEX);
            Serial.print(" (");
            Serial.print(address);
            Serial.println(")");
            deviceCount++;
            
            // Common sensor addresses for reference
            if (address == 0x3C || address == 0x3D) {
                Serial.println("  ^ Likely SSD1306 OLED display");
            } else if (address == 0x44) {
                Serial.println("  ^ Likely SHT85 sensor");
            } else if (address == 0x62) {
                Serial.println("  ^ Likely SCD4x CO2 sensor");
            } else if (address == 0x76 || address == 0x77) {
                Serial.println("  ^ Likely BME280 sensor");
            }
        } else if (error == 4) {
            Serial.print("Unknown error at address 0x");
            if (address < 16) Serial.print("0");
            Serial.println(address, HEX);
        }
    }
    
    if (deviceCount == 0) {
        Serial.println("No I2C devices found!");
        Serial.println("Possible issues:");
        Serial.println("- Hardware not connected");
        Serial.println("- Wrong I2C pins");
        Serial.println("- Power issues");
        Serial.println("- Faulty sensor");
    } else {
        Serial.print("Found ");
        Serial.print(deviceCount);
        Serial.println(" device(s)");
    }
    
    Serial.println("======================");
}

} // namespace I2cUtils

#endif // I2C_UTILS_H 