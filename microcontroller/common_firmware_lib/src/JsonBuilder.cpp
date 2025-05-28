#include "JsonBuilder.h"
// ArduinoJson.h is already included via JsonBuilder.h

namespace JsonBuilder {

// Base function that handles const char* for value. Other overloads will call this.
String buildPayload(const String& timestamp_utc, const String& uuid, const char* value_str) {
    if (timestamp_utc.length() == 0) {
        // According to header: "Returns an empty string or error JSON on failure."
        // Returning an error JSON is more informative.
        return String("{\"error\":\"Timestamp missing\"}"); 
    }

    if (uuid.length() == 0) {
        return String("{\"error\":\"UUID missing\"}"); 
    }

    // Estimate JSON document size. Updated for new structure with UUID.
    // Structure: {"timestamp_utc":"<ts>","value":"<val>","uuid":"<uuid>"}
    // Keys (13+5+4=22) + Quotes&Colons&Braces (~8) + Timestamp (20-24) + UUID (36) + Value length.
    // StaticJsonDocument<512> allows for timestamp + UUID + ~160 chars for value string. Add some more for good measure
    StaticJsonDocument<512> doc; 

    doc["timestamp_utc"] = timestamp_utc;
    doc["value"] = value_str; // ArduinoJson handles stringifying this if it's not already a string literal
    doc["uuid"] = uuid;

    String output;
    if (serializeJson(doc, output) == 0) {
        // Serialization failed
        return String("{\"error\":\"JSON serialization failed\"}");
    }
    return output;
}

String buildPayload(const String& timestamp_utc, const String& uuid, String value) {
    return buildPayload(timestamp_utc, uuid, value.c_str());
}

String buildPayload(const String& timestamp_utc, const String& uuid, int value) {
    // Convert int to string
    char buffer[12]; // Enough for a 32-bit integer string + null terminator
    sprintf(buffer, "%d", value);
    return buildPayload(timestamp_utc, uuid, buffer);
}

String buildPayload(const String& timestamp_utc, const String& uuid, float value, int decimalPlaces) {
    // Convert float to string
    char buffer[32]; // Generous buffer for float string
    // dtostrf(value, min_width_including_sign_and_point, num_digits_after_decimal, char_buffer);
    // Using 0 for min_width means minimal representation.
    dtostrf(value, 0, decimalPlaces, buffer);
    return buildPayload(timestamp_utc, uuid, buffer);
}

String buildPayload(const String& timestamp_utc, const String& uuid, double value, int decimalPlaces) {
    // On ESP32, double is typically the same as float (32-bit)
    return buildPayload(timestamp_utc, uuid, static_cast<float>(value), decimalPlaces);
}

String buildPayload(const String& timestamp_utc, const String& uuid, bool value) {
    return buildPayload(timestamp_utc, uuid, value ? "true" : "false");
}

} // namespace JsonBuilder 