#include "NtpService.h"
#include <time.h> // Required for time_t, struct tm, gmtime, sprintf

// Default NTP server if not configured otherwise
const char* NTP_SERVER = "pool.ntp.org"; 
// Default to UTC. ADR-10 specifies UTC for timestamp_utc.
const long GMT_OFFSET_SEC = 0; 
// Default update interval for NTPClient, 60 seconds. 
// The FSM will control how often NtpService::update() is actually called.
const unsigned int NTP_UPDATE_INTERVAL_MS = 60000;

NtpService::NtpService() 
    : timeClient(ntpUDP, NTP_SERVER, GMT_OFFSET_SEC, NTP_UPDATE_INTERVAL_MS), 
      timeSuccessfullySet(false) {
}

void NtpService::begin() {
    timeClient.begin();
}

bool NtpService::update() {
    bool updated = timeClient.update();
    if (updated) {
        if (!timeSuccessfullySet) {
            timeSuccessfullySet = true;
            // Optionally, log the first successful sync
            // Serial.println("NTP time synchronized for the first time.");
        }
    }
    return updated;
}

unsigned long NtpService::getEpochTime() const {
    if (!timeSuccessfullySet) {
        // Return 0 or a specific error code if time is not set,
        // or rely on NTPClient to return its default (often 0 if not set).
    }
    return timeClient.getEpochTime();
}

String NtpService::getFormattedISO8601Time() const {
    if (!timeSuccessfullySet) {
        // Consider returning an empty string or an error indicator if time is not set
        // For now, matches NTPClient behavior which might return 1970-01-01T00:00:00Z if not synced
        // Updated to return a more explicit message or an empty string for un-set time:
        return String("Time not set"); 
    }
    time_t epoch = timeClient.getEpochTime();
    struct tm *ptm = gmtime(&epoch); // Convert to UTC time structure

    char buffer[21]; // Buffer for "YYYY-MM-DDTHH:MM:SSZ" + null terminator (20 chars + 1)
    // Format to YYYY-MM-DDTHH:MM:SSZ
    // Note: tm_year is years since 1900, tm_mon is 0-11
    sprintf(buffer, "%04d-%02d-%02dT%02d:%02d:%02dZ",
            ptm->tm_year + 1900, ptm->tm_mon + 1, ptm->tm_mday,
            ptm->tm_hour, ptm->tm_min, ptm->tm_sec);
    return String(buffer);
}

bool NtpService::isTimeSet() const {
    return timeSuccessfullySet;
} 