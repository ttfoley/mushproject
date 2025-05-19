#include <Arduino.h>
#include "NtpService.h" // Assuming NtpService.h is in common_firmware_lib/include
                       // and common_firmware_lib is correctly linked.
#include <WiFi.h>
#include "secrets.h" // For WiFi credentials
#include "JsonBuilder.h" // For testing ADR-10 JSON payload construction



NtpService ntpService;

// How often to attempt NTP update in the loop (milliseconds)
const unsigned long NTP_LOOP_UPDATE_INTERVAL = 60000; // Every 60 seconds
unsigned long lastNtpLoopUpdate = 0;

// How often to print the time in the loop (milliseconds)
const unsigned long PRINT_TIME_INTERVAL = 5000; // Every 5 seconds
unsigned long lastTimePrint = 0;

void setupWifi() {
    Serial.print("Connecting to WiFi: ");
    Serial.println(SECRET_WIFI_SSID);
    WiFi.begin(SECRET_WIFI_SSID, SECRET_WIFI_PWD);

    unsigned long startTime = millis();
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
        if (millis() - startTime > 20000) { // 20 second timeout
            Serial.println("\nWiFi connection FAILED. Restarting...");
            // In a real FSM, this would trigger RestartReasonLogger.storeRestartReason(WIFI_TIMEOUT);
            // and then ESP.restart();
            delay(1000);
            ESP.restart(); 
        }
    }
    Serial.println("\nWiFi connected!");
    Serial.print("IP Address: ");
    Serial.println(WiFi.localIP());
}

void setupNtp() {
    Serial.println("Initializing NTP Service...");
    ntpService.begin();

    Serial.println("Attempting initial NTP synchronization...");
    unsigned long startTime = millis();
    bool initialSyncDone = false;
    while(!initialSyncDone) {
        // NtpService.update() internally calls timeClient.update()
        // It's non-blocking in the sense that timeClient.update() is.
        // We need to call it until isTimeSet() is true or we timeout.
        ntpService.update(); 
        if (ntpService.isTimeSet()) {
            Serial.println("\nInitial NTP sync successful!");
            Serial.print("Current UTC Time: ");
            Serial.println(ntpService.getFormattedISO8601Time());
            initialSyncDone = true;
        } else {
            Serial.print("u"); // Update attempt
        }
        
        if (millis() - startTime > 30000 && !initialSyncDone) { // 30 second timeout for initial sync
            Serial.println("\nInitial NTP sync FAILED after timeout.");
            // In a real FSM, this would trigger RestartReasonLogger.storeRestartReason(NTP_TIMEOUT);
            // and potentially lead to a restart or other error handling.
            // For now, we proceed, but time will be unsynchronized.
            break; 
        }
        delay(1000); // Wait a bit between attempts
    }

    // --- Test JsonBuilder --- 
    if (initialSyncDone) { // Only test if we have a valid timestamp
        Serial.println("\n--- Testing JsonBuilder --- ");
        String currentTimestamp = ntpService.getFormattedISO8601Time();

        String json_string = JsonBuilder::buildPayload(currentTimestamp, "hello world");
        Serial.print("Test 1 (const char*): "); Serial.println(json_string);

        String json_int = JsonBuilder::buildPayload(currentTimestamp, 12345);
        Serial.print("Test 2 (int): "); Serial.println(json_int);

        String json_float = JsonBuilder::buildPayload(currentTimestamp, 3.14159f, 3); // 3 decimal places
        Serial.print("Test 3 (float): "); Serial.println(json_float);

        String json_bool_true = JsonBuilder::buildPayload(currentTimestamp, true);
        Serial.print("Test 4 (bool true): "); Serial.println(json_bool_true);

        String json_bool_false = JsonBuilder::buildPayload(currentTimestamp, false);
        Serial.print("Test 5 (bool false): "); Serial.println(json_bool_false);
        Serial.println("--- End JsonBuilder Test ---");
    }
    // --- End Test JsonBuilder ---
}

void setup() {
    Serial.begin(115200);
    while (!Serial); // Wait for serial to connect (especially for some boards)
    Serial.println("\n\n--- Controller C2 (Refactored) NTP Test ---");

    setupWifi();
    setupNtp();

    Serial.println("Setup complete. Entering loop...");
    lastNtpLoopUpdate = millis(); // Initialize for loop updates
    lastTimePrint = millis();
}

void loop() {
    unsigned long currentTime = millis();

    // Periodically try to update NTP
    if (currentTime - lastNtpLoopUpdate >= NTP_LOOP_UPDATE_INTERVAL) {
        Serial.println("Attempting periodic NTP update...");
        if (ntpService.update()) {
            Serial.println("Periodic NTP update successful.");
            // Optional: Log if it *re*-established sync after being lost
        } else {
            Serial.println("Periodic NTP update attempt made (may not have changed time if already set).");
        }
        lastNtpLoopUpdate = currentTime;
    }

    // Periodically print the current time
    if (currentTime - lastTimePrint >= PRINT_TIME_INTERVAL) {
        if (ntpService.isTimeSet()) {
            Serial.print(millis());
            Serial.print(" - Current UTC Time: ");
            Serial.println(ntpService.getFormattedISO8601Time());
        } else {
            Serial.print(millis());
            Serial.println(" - NTP time not set.");
        }
        lastTimePrint = currentTime;
    }

    // Placeholder for future FSM logic
    delay(10); 
} 