#ifndef RESTART_REASON_LOGGER_H
#define RESTART_REASON_LOGGER_H

#include <Arduino.h>
#include "PublishData.h"

// Forward declarations
class NtpService;

/**
 * RestartReason Enumeration
 * 
 * Defines all possible reasons why the microcontroller might restart.
 * Based on ADR-17 and microcontroller plan P0.2.
 */
enum RestartReason {
    UNKNOWN_RESET = 0,      // Default/unknown restart (power loss, watchdog, etc.)
    WIFI_TIMEOUT,           // WiFi connection failed after max attempts
    MQTT_TIMEOUT,           // MQTT connection failed after max attempts  
    NTP_TIMEOUT,            // NTP synchronization failed after timeout
    NOPUBLISH_TIMEOUT,      // No successful publish for too long (ADR-18)
    COMMAND_ERROR,          // Critical command processing error
    SENSOR_ERROR,           // Critical sensor error (for sensor controllers)
    SENSOR_INIT_FAILED,     // Sensor initialization failed during setup
    USER_REQUESTED,         // Manual restart requested
    FIRMWARE_UPDATE         // Restart for firmware update
};

/**
 * RestartEvent Structure
 * 
 * Stores a restart reason along with its timestamp.
 * Timestamp is ISO8601 string if NTP was available when stored, empty string if not.
 */
struct RestartEvent {
    RestartReason reason;
    String timestamp;       // ISO8601 string or empty if NTP unavailable
    
    RestartEvent() : reason(UNKNOWN_RESET), timestamp("") {}
    RestartEvent(RestartReason r, const String& ts) : reason(r), timestamp(ts) {}
};

/**
 * RestartReasonLogger Class
 * 
 * Handles persistent storage and retrieval of restart reasons using ESP32 Preferences.
 * Implements the timestamp strategy discussed: store actual time if available,
 * use current time when publishing if stored time is unavailable.
 * 
 * Based on ADR-14 (Persistent Error Logging) and ADR-17 (Restart Reasons).
 */
class RestartReasonLogger {
public:
    RestartReasonLogger();
    
    /**
     * Store a restart reason with timestamp if NTP is available.
     * Call this before transitioning to RESTART state.
     * 
     * @param reason The reason for the restart
     * @param ntp Reference to NtpService to get timestamp if available
     */
    void storeRestartReason(RestartReason reason, NtpService& ntp);
    
    /**
     * Retrieve the stored restart event and immediately clear it from storage.
     * This ensures each restart reason is only published once.
     * 
     * @return RestartEvent with reason and timestamp (may be empty)
     */
    RestartEvent getStoredRestartEvent();
    
    /**
     * Create a PublishData object for the stored restart reason.
     * Uses stored timestamp if available, current time if not.
     * Automatically calls getStoredRestartEvent() which clears storage.
     * 
     * @param ntp Reference to NtpService for current time if needed
     * @param topic MQTT topic to publish to
     * @param uuid UUID for the data point
     * @return PublishData ready to be added to publish queue
     */
    PublishData createPublishData(NtpService& ntp, const char* topic, const char* uuid);
    
    /**
     * Check if there is a stored restart reason waiting to be published.
     * Does not clear the stored data.
     * 
     * @return true if there is a restart reason stored
     */
    bool hasStoredRestartReason();
    
    /**
     * Convert RestartReason enum to human-readable string.
     * 
     * @param reason The restart reason enum value
     * @return String representation for MQTT payload
     */
    static String restartReasonToString(RestartReason reason);

private:
    static const char* PREFERENCES_NAMESPACE;
    static const char* REASON_KEY;
    static const char* TIMESTAMP_KEY;
    
    /**
     * Clear the stored restart reason from persistent storage.
     * Called automatically by getStoredRestartEvent().
     */
    void clearStoredRestartReason();
};

#endif // RESTART_REASON_LOGGER_H 