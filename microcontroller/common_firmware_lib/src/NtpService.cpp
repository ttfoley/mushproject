#include "services/NtpService.h"
#include <time.h> // Required for time_t, struct tm, gmtime, sprintf
#include <sys/time.h>   // Required for gettimeofday, struct timeval

// Default NTP server if not configured otherwise
const char* NTP_SERVER = "pool.ntp.org"; 
// Default to UTC. ADR-10 specifies UTC for timestamp_utc.
const long GMT_OFFSET_SEC = 0; 
// Default update interval for NTPClient, 60 seconds. 
// The FSM will control how often NtpService::update() is actually called.
const unsigned int NTP_UPDATE_INTERVAL_MS = 60000;

// A threshold to consider system time as valid (e.g., after Jan 1, 2000 UTC / 946684800 seconds since epoch)
// Using a more recent threshold like Jan 1, 2020 UTC (1577836800) is also fine.
// For simplicity, any time significantly past epoch (e.g. > 1000000000 which is in 2001) indicates sync.
const unsigned long MIN_VALID_EPOCH_TIME_SEC = 1577836800UL; // Approx Jan 1, 2020 UTC

NtpService::NtpService() 
    // : timeClient(ntpUDP, NTP_SERVER, GMT_OFFSET_SEC, NTP_UPDATE_INTERVAL_MS), // Removed NTPClient initialization
      : timeSuccessfullySet(false) {
}

void NtpService::begin() {
    // Configure the system time settings.
    // GMT_OFFSET_SEC is 0 for UTC.
    // Daylight offset is 0 as we are dealing with UTC.
    // NTP_SERVER is "pool.ntp.org".
    configTime(GMT_OFFSET_SEC, 0, NTP_SERVER); 
    
    // timeClient.begin(); // Removed: No longer using NTPClient directly
}

bool NtpService::update() {
    // This method now checks if the system time (presumably set by system NTP via configTime)
    // is valid. It no longer actively polls with NTPClient.
    struct timeval tv;
    gettimeofday(&tv, NULL);

    if (tv.tv_sec > MIN_VALID_EPOCH_TIME_SEC) { 
        if (!timeSuccessfullySet) {
            timeSuccessfullySet = true;
            // Optionally, log the first successful sync
            // Serial.println("System time appears to be synchronized (post-epoch check).");
        }
    } else {
        // If time is not yet valid, ensure our flag reflects that.
        // This could happen if NTP sync is lost or not yet achieved.
        // timeSuccessfullySet = false; // Optional: decide if we want to reset the flag if sync is lost
                                   // For now, once set, it stays set. The FSM should handle loss of sync.
    }
    return timeSuccessfullySet; 
}

unsigned long NtpService::getEpochTime() const {
    // if (!timeSuccessfullySet) { // Optional check, but gettimeofday will return epoch if not set
    //     return 0; 
    // }
    struct timeval tv;
    gettimeofday(&tv, NULL);
    return tv.tv_sec; // Return system epoch time
}

String NtpService::getFormattedISO8601Time() const {
    if (!timeSuccessfullySet) {
        return String("Time not set"); 
    }

    struct timeval tv;
    gettimeofday(&tv, NULL); // Get current time with microsecond precision

    // --- TEMPORARY DIAGNOSTIC ---
    // Serial.print("[getFormattedISO8601Time] tv.tv_sec before formatting: ");
    // Serial.println(tv.tv_sec);
    // --- END TEMPORARY DIAGNOSTIC ---

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