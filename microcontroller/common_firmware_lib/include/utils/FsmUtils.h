// FsmUtils.h
// Header-only FSM utilities for microcontroller firmware
// Provides common patterns to reduce boilerplate and ensure consistency across controllers

#ifndef FSM_UTILS_H
#define FSM_UTILS_H

#include <Arduino.h>
#include "autogen_config.h" // For FsmState enum
#include "../services/RestartReasonLogger.h"
#include "../services/NtpService.h"

namespace FsmUtils {

    /**
     * Convert FSM state enum to string for debug output
     * 
     * @param state The FSM state to convert
     * @return String representation of the state
     */
    inline const char* stateToString(FsmState state) {
        switch (state) {
            case SETUP_HW: return "SETUP_HW";
            case CONNECT_WIFI: return "CONNECT_WIFI";
            case SYNC_NTP: return "SYNC_NTP";
            case CONNECT_MQTT: return "CONNECT_MQTT";
            case PUBLISH_BOOT_STATUS: return "PUBLISH_BOOT_STATUS";
            case PROCESS_COMMANDS: return "PROCESS_COMMANDS";
            case READ_SENSORS: return "READ_SENSORS";
            case PUBLISH_DATA: return "PUBLISH_DATA";
            case OPERATIONAL_PERIODIC_CHECKS: return "OPERATIONAL_PERIODIC_CHECKS";
            case WAIT: return "WAIT";
            case RESTART: return "RESTART";
            default: return "UNKNOWN_STATE";
        }
    }

    /**
     * Transition to a new FSM state with debug logging and optional timer reset
     * Ensures state changes are always logged, timer reset only when explicitly requested
     * Only logs when there's an actual state change to prevent spam
     * 
     * @param currentState Reference to current state variable
     * @param newState The state to transition to
     * @param stateStartTime Reference to state timing variable
     * @param resetTimer Whether to reset the state timer (defaults to false for safety)
     */
    inline void transitionToState(FsmState &currentState, FsmState newState, 
                                 unsigned long &stateStartTime, bool resetTimer = false) {
        // Only log if there's an actual state change
        if (currentState != newState) {
            Serial.print("FSM: ");
            Serial.print(stateToString(currentState));
            Serial.print(" -> ");
            Serial.println(stateToString(newState));
        }
        
        currentState = newState;
        if (resetTimer) {
            stateStartTime = millis();
        }
    }

    /**
     * Check if a timeout has occurred for the current state
     * 
     * @param stateStartTime When the current state was entered
     * @param timeoutMs Timeout duration in milliseconds
     * @return true if timeout has occurred
     */
    inline bool checkTimeout(unsigned long stateStartTime, unsigned long timeoutMs) {
        return (millis() - stateStartTime) > timeoutMs;
    }

    /**
     * Handle restart with reason logging - ensures critical pairing
     * Always pairs restart reason storage with RESTART state transition
     * 
     * @param currentState Reference to current state variable
     * @param reason The restart reason to log
     * @param logger Reference to RestartReasonLogger
     * @param ntp Reference to NtpService for timestamping
     */
    inline void handleRestartWithReason(FsmState &currentState, RestartReason reason, 
                                       RestartReasonLogger &logger, NtpService &ntp) {
        Serial.print("FSM: Restart triggered - Reason: ");
        Serial.println(RestartReasonLogger::restartReasonToString(reason));
        
        logger.storeRestartReason(reason, ntp);
        currentState = RESTART;
    }

    /**
     * Check and increment retry attempts with consistent logging
     * Prevents controller divergence in retry logic patterns
     * 
     * @param attempts Reference to current attempt counter
     * @param maxAttempts Maximum allowed attempts
     * @param operationName Name of operation for logging
     * @return true if max attempts exceeded (should restart/fail)
     */
    inline bool checkAndIncrementRetries(unsigned int &attempts, unsigned int maxAttempts, 
                                        const char* operationName) {
        attempts++;
        
        Serial.print(operationName);
        Serial.print(" attempt ");
        Serial.print(attempts);
        Serial.print(" of ");
        Serial.println(maxAttempts);
        
        if (attempts >= maxAttempts) {
            Serial.print(operationName);
            Serial.print(" failed after ");
            Serial.print(maxAttempts);
            Serial.println(" attempts");
            return true; // Max attempts exceeded
        }
        
        return false; // Continue trying
    }

    /**
     * Reset retry counter (typically called on successful operation)
     * 
     * @param attempts Reference to attempt counter to reset
     * @param operationName Name of operation for logging
     */
    inline void resetRetries(unsigned int &attempts, const char* operationName) {
        if (attempts > 0) {
            Serial.print(operationName);
            Serial.println(" successful - retry counter reset");
            attempts = 0;
        }
    }

} // namespace FsmUtils

#endif // FSM_UTILS_H 