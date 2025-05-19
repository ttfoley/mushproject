#include "NtpService.h"
#include <time.h> // Required for time_t, struct tm, gmtime, sprintf
#include <sys/time.h>   // Required for gettimeofday, struct timeval

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
        return String("Time not set"); 
    }

    struct timeval tv;
    gettimeofday(&tv, NULL); // Get current time with microsecond precision

    // tv.tv_sec contains seconds since epoch (like time_t)
    // tv.tv_usec contains microseconds

    struct tm *ptm = gmtime(&tv.tv_sec); // Convert seconds to UTC time structure

    // Buffer for "YYYY-MM-DDTHH:MM:SS.sssZ" + null terminator (24 chars + 1 = 25)
    char buffer[25]; 
    
    // Format to YYYY-MM-DDTHH:MM:SS.sssZ
    // Note: tm_year is years since 1900, tm_mon is 0-11
    // tv.tv_usec / 1000 gives milliseconds
    sprintf(buffer, "%04d-%02d-%02dT%02d:%02d:%02d.%03ldZ",
            ptm->tm_year + 1900, ptm->tm_mon + 1, ptm->tm_mday,
            ptm->tm_hour, ptm->tm_min, ptm->tm_sec, 
            tv.tv_usec / 1000); // Add milliseconds
            
    return String(buffer);
}

bool NtpService::isTimeSet() const {
    return timeSuccessfullySet;
} 