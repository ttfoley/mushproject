#ifndef SENSOR_PUBLISH_QUEUE_H
#define SENSOR_PUBLISH_QUEUE_H

#include <queue>
#include <set>
#include "PublishData.h"

/**
 * @brief Manages a publish queue with sensor tracking to prevent duplicate reads
 * 
 * This utility manages the common pattern of:
 * - std::queue<PublishData> for FIFO publishing
 * - std::set<SensorPoint*> for O(log N) duplicate checking
 * 
 * Ensures sensors aren't re-queued for reading when they already have data pending.
 */
class SensorPublishQueue {
private:
    std::queue<PublishData> _queue;
    std::set<SensorPoint*> _sensorsWithPendingData;

public:
    /**
     * @brief Add data to publish queue and track source sensor
     * @param data The publish data to queue
     */
    void queueForPublish(const PublishData& data) {
        _queue.push(data);
        if (data.sourceSensor != nullptr) {
            _sensorsWithPendingData.insert(data.sourceSensor);
        }
    }

    /**
     * @brief Remove and return front item from queue
     * @return The front PublishData item
     * @note Caller must check empty() before calling
     */
    PublishData dequeueForPublish() {
        PublishData item = _queue.front();
        _queue.pop();
        return item;
    }

    /**
     * @brief Mark publish as complete and remove sensor from tracking
     * @param item The published item
     */
    void markPublishComplete(const PublishData& item) {
        if (item.sourceSensor != nullptr) {
            _sensorsWithPendingData.erase(item.sourceSensor);
        }
    }

    /**
     * @brief Check if sensor has pending data in queue
     * @param sensor The sensor to check
     * @return true if sensor has data pending
     */
    bool hasPendingData(SensorPoint* sensor) const {
        return _sensorsWithPendingData.find(sensor) != _sensorsWithPendingData.end();
    }

    /**
     * @brief Check if queue is empty
     * @return true if queue is empty
     */
    bool empty() const {
        return _queue.empty();
    }

    /**
     * @brief Get number of items in queue
     * @return Queue size
     */
    size_t size() const {
        return _queue.size();
    }

    /**
     * @brief Clear all items from queue and tracking set
     */
    void clear() {
        while (!_queue.empty()) {
            _queue.pop();
        }
        _sensorsWithPendingData.clear();
    }
};

#endif // SENSOR_PUBLISH_QUEUE_H 