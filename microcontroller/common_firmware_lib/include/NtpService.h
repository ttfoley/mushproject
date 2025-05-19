#ifndef NTPSERVICE_H
#define NTPSERVICE_H

#include <Arduino.h>
// #include <NTPClient.h> // No longer using NTPClient directly
// #include <WiFiUdp.h>   // No longer using WiFiUDP directly here

// Forward declaration if RestartReasonLogger is in a different header and needed here
// enum RestartReason : int; 
// class RestartReasonLogger;

class NtpService {
public:
    NtpService();
    void begin(); // Method to initialize NTP (will call configTime)
    bool update(); // Method to check system time sync status
    String getFormattedISO8601Time() const; // Method to get current UTC time as an ISO 8601 string
    unsigned long getEpochTime()     const; // Method to get current epoch time from system
    bool isTimeSet() const; // Check if time has been successfully set at least once

private:
    // WiFiUDP ntpUDP; // Removed
    // NTPClient timeClient; // Removed
    bool timeSuccessfullySet;
    // unsigned long lastSyncAttempt;
    // unsigned long syncInterval; // How often to try to sync if not set
    // RestartReasonLogger* restartLogger; // Optional: for logging NTP_TIMEOUT

    // Configuration for NTP
    // const char* ntpServer = "pool.ntp.org"; // Default, can be configurable
    // long gmtOffset_sec = 0; // Default to UTC
    // unsigned int updateInterval_ms = 60000; // Default update interval
};

#endif // NTPSERVICE_H 