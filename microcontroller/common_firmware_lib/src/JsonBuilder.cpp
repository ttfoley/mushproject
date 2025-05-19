#include "JsonBuilder.h"
// ArduinoJson.h is already included via JsonBuilder.h

namespace JsonBuilder {

// Base function that handles const char* for value. Other overloads will call this.
String buildPayload(const String& timestamp_utc, const char* value_str) {
    if (timestamp_utc.length() == 0) {
        // According to header: "Returns an empty string or error JSON on failure."
        // Returning an error JSON is more informative.
        return String("{\"error\":\"Timestamp missing\"}"); 
    }

    // Estimate JSON document size. This should be sufficient for typical cases.
    // Structure: {"timestamp_utc":"<ts>","value":"<val>"}
    // Keys (13+5=18) + Quotes&Colons&Braces (~6) + Timestamp (20-24) + Value length.
    // StaticJsonDocument<192> allows for timestamp + ~140 chars for value string, which is generous.
    // If very long values are expected, DynamicJsonDocument might be needed, or increase this size.
    StaticJsonDocument<192> doc; 

    doc["timestamp_utc"] = timestamp_utc;
    doc["value"] = value_str; // ArduinoJson handles stringifying this if it's not already a string literal

    String output;
    if (serializeJson(doc, output) == 0) {
        // Serialization failed
        return String("{\"error\":\"JSON serialization failed\"}");
    }
    return output;
}

String buildPayload(const String& timestamp_utc, String value) {
    return buildPayload(timestamp_utc, value.c_str());
}

String buildPayload(const String& timestamp_utc, int value) {
    // Convert int to string
    char buffer[12]; // Enough for a 32-bit integer string + null terminator
    sprintf(buffer, "%d", value);
    return buildPayload(timestamp_utc, buffer);
}

String buildPayload(const String& timestamp_utc, float value, int decimalPlaces) {
    // Convert float to string
    char buffer[32]; // Generous buffer for float string
    // dtostrf(value, min_width_including_sign_and_point, num_digits_after_decimal, char_buffer);
    // Using 0 for min_width means minimal representation.
    dtostrf(value, 0, decimalPlaces, buffer);
    return buildPayload(timestamp_utc, buffer);
}

String buildPayload(const String& timestamp_utc, double value, int decimalPlaces) {
    // On ESP32, double is typically the same as float (32-bit)
    return buildPayload(timestamp_utc, static_cast<float>(value), decimalPlaces);
}

String buildPayload(const String& timestamp_utc, bool value) {
    return buildPayload(timestamp_utc, value ? "true" : "false");
}

} // namespace JsonBuilder 