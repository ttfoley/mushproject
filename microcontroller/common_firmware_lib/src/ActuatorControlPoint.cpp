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
      _lastRepublishCheckTimeMillis(0),           // Initialize to 0
      _lastExecutedCommand("")                    // Initialize to empty - will be set by executeDeviceCommand()
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

void ActuatorControlPoint::executeDeviceCommand(const String& commandPayload) {
    // Called by FSM from PROCESS_COMMANDS state
    // Parses commandPayload ("on" -> HIGH, "off" -> LOW)
    // Performs digitalWrite(_pin, newState)
    // Updates _lastExecutedCommand for readback publishing
    // FSM handles state tracking and readback publishing
    
    int newState;
    if (commandPayload.equalsIgnoreCase("on")) {
        newState = HIGH;
    } else if (commandPayload.equalsIgnoreCase("off")) {
        newState = LOW;
    } else {
        // Invalid command payload - could log error here in future
        // For now, ignore invalid commands and don't update _lastExecutedCommand
        return;
    }
    
    // Control hardware and update readback state
    digitalWrite(_pin, newState);
    _lastExecutedCommand = commandPayload;  // Store for readback publishing only
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

String ActuatorControlPoint::getLastExecutedCommand() const {
    // Read-only getter for readback publishing
    // Returns the last successfully executed command ("on" or "off")
    // This is purely for FSM to use when publishing readback data
    return _lastExecutedCommand;
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