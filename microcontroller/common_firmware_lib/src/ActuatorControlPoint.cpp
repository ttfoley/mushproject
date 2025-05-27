#include "ActuatorControlPoint.h"

ActuatorControlPoint::ActuatorControlPoint(int pin, 
                                         int pinMode, 
                                         int initialState,
                                         const char* pointName,
                                         const char* writeTopic,
                                         const char* readbackTopic,
                                         const char* readbackUUID,
                                         unsigned long outputRepublishFrequencyMillis,
                                         unsigned long maxTimeNoPublishMillis)
    : _pin(pin),
      _pinMode(pinMode),
      _initialState(initialState),
      _pointName(pointName),
      _writeTopic(writeTopic),
      _readbackTopic(readbackTopic),
      _readbackUUID(readbackUUID),
      _outputRepublishFrequencyMillis(outputRepublishFrequencyMillis),
      _maxTimeNoPublishMillis(maxTimeNoPublishMillis),
      _lastPublishTimeMillis(0),                  // Initialize to 0
      _lastRepublishCheckTimeMillis(0)            // Initialize to 0
{
    // Constructor initialization complete via member initializer list
}

void ActuatorControlPoint::initialize() {
    // Called by FSM in SETUP_HW state
    // ONLY sets up pin mode - does NOT control hardware directly
    // FSM will queue initial command and process it through normal command flow
    pinMode(_pin, _pinMode);
    
    // DO NOT call digitalWrite() here - that's the FSM's job through executeDeviceCommand()
    // FSM should queue the initial state command and process it normally
}

bool ActuatorControlPoint::executeDeviceCommand(const String& commandPayload) {
    // Called by FSM from PROCESS_COMMANDS state
    // Parses commandPayload using centralized conversion utility
    // Performs digitalWrite(_pin, newState) if valid
    // Returns true if successful, false if invalid command
    // FSM handles readback publishing using the commandPayload that succeeded
    
    int newState = payloadToHardwareState(commandPayload);
    
    // Check if payload was valid (payloadToHardwareState returns LOW for invalid)
    // We need to distinguish between valid "off" and invalid payload
    if (commandPayload.equalsIgnoreCase("on") || commandPayload.equalsIgnoreCase("off")) {
        // Valid command - control hardware and return success
        digitalWrite(_pin, newState);
        return true;
    } else {
        // Invalid command payload - return failure
        return false;
    }
}

// Configuration getters
const char* ActuatorControlPoint::getReadbackTopic() const {
    return _readbackTopic;
}

const char* ActuatorControlPoint::getReadbackUUID() const {
    return _readbackUUID;
}

const char* ActuatorControlPoint::getWriteTopic() const {
    return _writeTopic;
}

const char* ActuatorControlPoint::getPointName() const {
    return _pointName;
}

int ActuatorControlPoint::getInitialState() const {
    return _initialState;
}

// Static utility methods for centralized conversion
String ActuatorControlPoint::hardwareStateToPayload(int hwState) {
    // Centralized HIGH/LOW -> "on"/"off" conversion
    // This is the single source of truth for this mapping
    return (hwState == HIGH) ? "on" : "off";
}

int ActuatorControlPoint::payloadToHardwareState(const String& payload) {
    // Centralized "on"/"off" -> HIGH/LOW conversion
    // This is the single source of truth for this mapping
    if (payload.equalsIgnoreCase("on")) {
        return HIGH;
    } else if (payload.equalsIgnoreCase("off")) {
        return LOW;
    } else {
        // Invalid payload - return a safe default
        return LOW;
    }
}

String ActuatorControlPoint::getInitialCommandPayload() const {
    // Helper method using centralized conversion utility
    return hardwareStateToPayload(_initialState);
}

// Timing configuration getters
unsigned long ActuatorControlPoint::getOutputRepublishFrequencyMillis() const {
    return _outputRepublishFrequencyMillis;
}

unsigned long ActuatorControlPoint::getMaxTimeNoPublishMillis() const {
    return _maxTimeNoPublishMillis;
}

// FSM-managed timestamp methods
void ActuatorControlPoint::setLastPublishTimeMillis(unsigned long time) {
    _lastPublishTimeMillis = time;
}

unsigned long ActuatorControlPoint::getLastPublishTimeMillis() const {
    return _lastPublishTimeMillis;
}

void ActuatorControlPoint::setLastRepublishCheckTimeMillis(unsigned long time) {
    _lastRepublishCheckTimeMillis = time;
}

unsigned long ActuatorControlPoint::getLastRepublishCheckTimeMillis() const {
    return _lastRepublishCheckTimeMillis;
}

bool ActuatorControlPoint::isTimeToRepublish() const {
    // Simple method for FSM to check if it's time to republish this actuator's readback
    // Returns true if (millis() - _lastRepublishCheckTimeMillis >= _outputRepublishFrequencyMillis)
    
    unsigned long currentTime = millis();
    unsigned long timeSinceLastCheck = currentTime - _lastRepublishCheckTimeMillis;
    
    return timeSinceLastCheck >= _outputRepublishFrequencyMillis;
}

bool ActuatorControlPoint::hasNoPublishTimeoutOccurred() const {
    // Returns (millis() - _lastPublishTimeMillis > _maxTimeNoPublishMillis) 
    // if _maxTimeNoPublishMillis > 0. Called by FSM.
    
    if (_maxTimeNoPublishMillis == 0) {
        // Timeout monitoring disabled
        return false;
    }
    
    unsigned long currentTime = millis();
    unsigned long timeSinceLastPublish = currentTime - _lastPublishTimeMillis;
    
    return timeSinceLastPublish > _maxTimeNoPublishMillis;
} 