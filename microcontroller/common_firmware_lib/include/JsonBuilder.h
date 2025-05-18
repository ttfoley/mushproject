#ifndef JSONBUILDER_H
#define JSONBUILDER_H

#include <Arduino.h>
#include <ArduinoJson.h> // We will use ArduinoJson for implementation

// Forward declaration for NtpService if its methods are directly used here
// class NtpService; 
// However, the plan states JsonBuilder is given a timestamp string, 
// so direct NtpService dependency might not be needed in JsonBuilder itself.

namespace JsonBuilder {

    /**
     * @brief Constructs the standard ADR-10 JSON payload.
     * 
     * The payload format is: {"timestamp_utc": "YYYY-MM-DDTHH:MM:SS.sssZ", "value": "<value_as_string>"}
     * This function is overloaded for various primitive types for the value.
     * 
     * @param timestamp_utc The UTC timestamp string (e.g., from NtpService).
     * @param value The value to include in the payload.
     * @return String The JSON payload. Returns an empty string or error JSON on failure.
     */
    String buildPayload(const String& timestamp_utc, const char* value);
    String buildPayload(const String& timestamp_utc, String value); // Allow String object as well
    String buildPayload(const String& timestamp_utc, int value);
    String buildPayload(const String& timestamp_utc, float value, int decimalPlaces = 2);
    String buildPayload(const String& timestamp_utc, double value, int decimalPlaces = 2); // Often same as float on ESP32
    String buildPayload(const String& timestamp_utc, bool value);

} // namespace JsonBuilder

#endif // JSONBUILDER_H 