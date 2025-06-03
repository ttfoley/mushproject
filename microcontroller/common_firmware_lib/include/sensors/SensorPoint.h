#ifndef SENSOR_POINT_H
#define SENSOR_POINT_H

#include <Arduino.h>
#include <vector>

#define SENSOR_PUBLISH_FUDGE_FACTOR 100 
// Structure to hold a single sensor reading with all necessary publish info
struct SensorReading {
    const char* topic;
    String value;
    String timestamp; 
    const char* uuid;
    
    SensorReading(const char* topic, const String& value, const String& timestamp, const char* uuid)
        : topic(topic), value(value), timestamp(timestamp), uuid(uuid) {}
};

// Abstract base class for all sensor types
class SensorPoint {
protected:
    unsigned long _timeNeededReadMs;     // Time required for physical sensor read
    unsigned long _lastReadAttemptMs;    // Last time we attempted to read (success or fail)
    unsigned long _lastPublishTimeMs;    // Last time readings were successfully published
    unsigned long _publishIntervalMs;    // How often to publish this sensor's data
    unsigned long _mainLoopDelayMs;      // Main loop delay to account for in timing
    
public:
    SensorPoint(unsigned long timeNeededReadMs, unsigned long publishIntervalMs, unsigned long mainLoopDelayMs)
        : _timeNeededReadMs(timeNeededReadMs)
        , _lastReadAttemptMs(0)
        , _lastPublishTimeMs(ULONG_MAX - publishIntervalMs)  // Initialize to trigger immediate read
        , _publishIntervalMs(publishIntervalMs)
        , _mainLoopDelayMs(mainLoopDelayMs) {}
    
    virtual ~SensorPoint() = default;
    
    // Initialize sensor hardware - called once during setup
    // Returns true if successful, false on error
    virtual bool initialize() = 0;
    
    // Perform hardware read operation - stores values internally with timestamps
    // Returns true if successful, false on error
    virtual bool read(const String& timestamp) = 0;
    
    // Get all readings from last successful read operation
    virtual std::vector<SensorReading> getAllReadings() = 0;
    
    // Check if this sensor needs to be read (considering both timing constraints)
    bool needToRead(unsigned long currentTimeMs) {
        unsigned long timeSinceLastPublish = currentTimeMs - _lastPublishTimeMs;
        
        // If we're past our publish interval, check if safe to retry read
        if (timeSinceLastPublish >= _publishIntervalMs) {
            return (currentTimeMs - _lastReadAttemptMs >= _timeNeededReadMs);
        }
        
        unsigned long timeUntilNextPublish = _publishIntervalMs - timeSinceLastPublish;
        
        // Start reading when we're getting close to publish time
        // Leave enough time for the sensor read to complete PLUS main loop delay
        //REALLY SHITTY SOLUTION FOR NOW - FUDGE FACTOR because of delays likely caused by mqtt loop and publish.
        bool closeToPublishTime = (timeUntilNextPublish <= (_timeNeededReadMs + _mainLoopDelayMs + SENSOR_PUBLISH_FUDGE_FACTOR));
        
        // Also ensure we haven't tried to read too recently. Note this is just resigning ourselves to waiting for the next publish interval, which seems fine.
        bool safeToRetryRead = (currentTimeMs - _lastReadAttemptMs >= _timeNeededReadMs);
        
        return closeToPublishTime && safeToRetryRead;
    }
    
    // Update timing after successful read attempt (called by FSM)
    void updateLastReadAttempt(unsigned long currentTimeMs) {
        _lastReadAttemptMs = currentTimeMs;
    }
    
    // Update timing after successful publish (called by FSM) 
    void updateLastPublishTime(unsigned long currentTimeMs) {
        _lastPublishTimeMs = currentTimeMs;
    }
    
    // Getters for FSM debugging/monitoring
    unsigned long getLastReadAttemptMs() const { return _lastReadAttemptMs; }
    unsigned long getLastPublishTimeMs() const { return _lastPublishTimeMs; }
    unsigned long getTimeNeededReadMs() const { return _timeNeededReadMs; }
    unsigned long getPublishIntervalMs() const { return _publishIntervalMs; }
};

#endif // SENSOR_POINT_H 