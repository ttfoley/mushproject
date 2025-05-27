#ifndef ACTUATOR_CONTROL_POINT_H
#define ACTUATOR_CONTROL_POINT_H

#include <Arduino.h>

/**
 * ActuatorControlPoint Class
 * 
 * Purpose: Manages a single actuator controlled via MQTT "on"/"off" commands,
 * with a corresponding "on"/"off" readback status. It holds its configuration 
 * and current physical state, but not pending command details.
 * 
 * Based on ADR-22 Section 2.2.1 (Modified for FSM-centric state management)
 */
class ActuatorControlPoint {
private:
    // Configuration members (from autogen_config.h)
    int _pin;
    int _pinMode;                    // Always OUTPUT for actuators
    int _initialState;               // HIGH or LOW
    const char* _writeTopic;
    const char* _readbackTopic;
    const char* _readbackUUID;
    const char* _pointName;
    
    // Timing configuration
    unsigned long _outputRepublishFrequencyMillis;
    unsigned long _maxTimeNoPublishMillis;
    
    // FSM-managed timestamps (no hardware state stored here)
    unsigned long _lastPublishTimeMillis;        // Set by FSM after confirmed publish of readback
    unsigned long _lastRepublishCheckTimeMillis; // Set by FSM after FSM checks for republish necessity
    
public:
    /**
     * Constructor
     * Initializes configuration members, sets timestamps to 0
     */
    ActuatorControlPoint(int pin, 
                        int pinMode, 
                        int initialState,
                        const char* pointName,
                        const char* writeTopic,
                        const char* readbackTopic,
                        const char* readbackUUID,
                        unsigned long outputRepublishFrequencyMillis,
                        unsigned long maxTimeNoPublishMillis);

    /**
     * Called by FSM in SETUP_HW state
     * ONLY sets Arduino pinMode() - does NOT control hardware directly
     * FSM must queue initial state command and process through normal command flow
     * This ensures single point of hardware control via executeDeviceCommand()
     */
    void initialize();

    /**
     * Called by FSM from PROCESS_COMMANDS state
     * Parses commandPayload ("on" -> HIGH, "off" -> LOW)
     * Performs digitalWrite(_pin, newState) if valid
     * Returns true if command was valid and executed, false otherwise
     * FSM handles readback publishing using the commandPayload that succeeded
     */
    bool executeDeviceCommand(const String& commandPayload);

    // Configuration getters
    const char* getReadbackTopic() const;
    const char* getReadbackUUID() const;
    const char* getWriteTopic() const;
    const char* getPointName() const;
    int getInitialState() const;
    
    /**
     * Static utility methods for centralized HIGH/LOW <-> "on"/"off" conversion
     * These ensure DRY principle by having one source of truth for the mapping
     */
    static String hardwareStateToPayload(int hwState);
    static int payloadToHardwareState(const String& payload);
    
    /**
     * Helper method to get the initial command payload based on initial hardware state
     * Uses the centralized conversion utility
     */
    String getInitialCommandPayload() const;
    
    // Timing configuration getters
    unsigned long getOutputRepublishFrequencyMillis() const;
    unsigned long getMaxTimeNoPublishMillis() const;
    
    // FSM-managed timestamp methods
    void setLastPublishTimeMillis(unsigned long time);
    unsigned long getLastPublishTimeMillis() const;
    void setLastRepublishCheckTimeMillis(unsigned long time);
    unsigned long getLastRepublishCheckTimeMillis() const;
    
    /**
     * Simple method for FSM to check if it's time to republish this actuator's readback.
     * Returns true if (millis() - _lastRepublishCheckTimeMillis >= _outputRepublishFrequencyMillis)
     */
    bool isTimeToRepublish() const;
    
    /**
     * Returns (millis() - _lastPublishTimeMillis > _maxTimeNoPublishMillis) 
     * if _maxTimeNoPublishMillis > 0. Called by FSM.
     */
    bool hasNoPublishTimeoutOccurred() const;
};

#endif // ACTUATOR_CONTROL_POINT_H 