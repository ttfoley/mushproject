#include "services/RestartReasonLogger.h"
#include "services/NtpService.h"
#include <Preferences.h>

// Static member definitions
const char* RestartReasonLogger::PREFERENCES_NAMESPACE = "restart";
const char* RestartReasonLogger::REASON_KEY = "reason";
const char* RestartReasonLogger::TIMESTAMP_KEY = "timestamp";

RestartReasonLogger::RestartReasonLogger() {
    // Constructor - no initialization needed
}

void RestartReasonLogger::storeRestartReason(RestartReason reason, NtpService& ntp) {
    Preferences preferences;
    
    if (!preferences.begin(PREFERENCES_NAMESPACE, false)) {
        Serial.println("RestartReasonLogger: Failed to open preferences for writing");
        return;
    }
    
    // Store the restart reason
    preferences.putUInt(REASON_KEY, static_cast<uint32_t>(reason));
    
    // Store timestamp if NTP is available
    String timestamp = "";
    if (ntp.isTimeSet()) {
        timestamp = ntp.getFormattedISO8601Time();
        Serial.print("RestartReasonLogger: Storing restart reason with timestamp: ");
        Serial.println(timestamp);
    } else {
        Serial.println("RestartReasonLogger: Storing restart reason without timestamp (NTP not available)");
    }
    
    preferences.putString(TIMESTAMP_KEY, timestamp);
    preferences.end();
    
    Serial.print("RestartReasonLogger: Stored restart reason: ");
    Serial.println(restartReasonToString(reason));
}

RestartEvent RestartReasonLogger::getStoredRestartEvent() {
    Preferences preferences;
    RestartEvent event;
    
    if (!preferences.begin(PREFERENCES_NAMESPACE, true)) {
        Serial.println("RestartReasonLogger: Failed to open preferences for reading");
        return event; // Returns default UNKNOWN_RESET with empty timestamp
    }
    
    // Read the stored data
    uint32_t storedReason = preferences.getUInt(REASON_KEY, static_cast<uint32_t>(UNKNOWN_RESET));
    String storedTimestamp = preferences.getString(TIMESTAMP_KEY, "");
    
    preferences.end();
    
    // Create the event
    event.reason = static_cast<RestartReason>(storedReason);
    event.timestamp = storedTimestamp;
    
    Serial.print("RestartReasonLogger: Retrieved restart reason: ");
    Serial.print(restartReasonToString(event.reason));
    if (event.timestamp != "") {
        Serial.print(" with timestamp: ");
        Serial.println(event.timestamp);
    } else {
        Serial.println(" (no stored timestamp)");
    }
    
    // Clear the stored data immediately after reading (Option 1 from discussion)
    clearStoredRestartReason();
    
    return event;
}

PublishData RestartReasonLogger::createPublishData(NtpService& ntp, const char* topic, const char* uuid) {
    RestartEvent event = getStoredRestartEvent(); // This also clears storage
    
    // Determine which timestamp to use
    String timestampToUse;
    if (event.timestamp != "") {
        // Use the stored timestamp (actual restart time)
        timestampToUse = event.timestamp;
        Serial.println("RestartReasonLogger: Using stored timestamp for publish");
    } else {
        // Use current time as fallback (publish time)
        timestampToUse = ntp.getFormattedISO8601Time();
        Serial.println("RestartReasonLogger: Using current timestamp for publish (stored timestamp unavailable)");
    }
    
    String reasonString = restartReasonToString(event.reason);
    
    Serial.print("RestartReasonLogger: Creating PublishData - Reason: ");
    Serial.print(reasonString);
    Serial.print(", Timestamp: ");
    Serial.println(timestampToUse);
    
    return PublishData(topic, uuid, reasonString, timestampToUse);
}

bool RestartReasonLogger::hasStoredRestartReason() {
    Preferences preferences;
    
    if (!preferences.begin(PREFERENCES_NAMESPACE, true)) {
        return false;
    }
    
    // Check if there's a stored reason (default value means no stored reason)
    uint32_t storedReason = preferences.getUInt(REASON_KEY, static_cast<uint32_t>(UNKNOWN_RESET));
    bool hasReason = preferences.isKey(REASON_KEY);
    
    preferences.end();
    
    return hasReason;
}

String RestartReasonLogger::restartReasonToString(RestartReason reason) {
    switch (reason) {
        case WIFI_TIMEOUT:      return "wifi_timeout";
        case MQTT_TIMEOUT:      return "mqtt_timeout";
        case NTP_TIMEOUT:       return "ntp_timeout";
        case NOPUBLISH_TIMEOUT: return "nopublish_timeout";
        case COMMAND_ERROR:     return "command_error";
        case SENSOR_ERROR:      return "sensor_error";
        case USER_REQUESTED:    return "user_requested";
        case FIRMWARE_UPDATE:   return "firmware_update";
        case MAINTENANCE_RESTART: return "maintenance_restart";
        case UNKNOWN_RESET:
        default:                return "unknown_reset";
    }
}

void RestartReasonLogger::clearStoredRestartReason() {
    Preferences preferences;
    
    if (!preferences.begin(PREFERENCES_NAMESPACE, false)) {
        Serial.println("RestartReasonLogger: Failed to open preferences for clearing");
        return;
    }
    
    preferences.remove(REASON_KEY);
    preferences.remove(TIMESTAMP_KEY);
    preferences.end();
    
    Serial.println("RestartReasonLogger: Cleared stored restart reason");
} 