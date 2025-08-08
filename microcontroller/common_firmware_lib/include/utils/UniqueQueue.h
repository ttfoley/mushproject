#ifndef UNIQUE_QUEUE_H
#define UNIQUE_QUEUE_H

#include <queue>
#include <set>

/**
 * @brief A queue that prevents duplicate entries using a tracking set
 * 
 * This utility manages the common pattern of:
 * - std::queue<T> for FIFO processing
 * - std::set<T> for O(log N) duplicate checking
 * 
 * Used for preventing duplicate sensor/actuator queuing in FSM states.
 * 
 * @tparam T The type of items to queue (e.g., SensorPoint*, ActuatorControlPoint*)
 */
template<typename T>
class UniqueQueue {
private:
    std::queue<T> _queue;
    std::set<T> _tracking;

public:
    /**
     * @brief Attempt to enqueue an item if not already present
     * @param item The item to enqueue
     * @return true if item was enqueued, false if already present
     */
    bool tryEnqueue(T item) {
        if (contains(item)) {
            return false; // Already queued
        }
        
        // Add to both queue and tracking set
        _queue.push(item);
        _tracking.insert(item);
        return true;
    }
    
    /**
     * @brief Dequeue the front item and remove from tracking
     * @return The front item
     * @note Caller must check empty() before calling
     */
    T dequeue() {
        T item = _queue.front();
        _queue.pop();
        _tracking.erase(item);
        return item;
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
     * @brief Check if item is already queued
     * @param item The item to check
     * @return true if item is in tracking set
     */
    bool contains(T item) const {
        return _tracking.find(item) != _tracking.end();
    }
    
    /**
     * @brief Clear all items from queue and tracking set
     */
    void clear() {
        while (!_queue.empty()) {
            _queue.pop();
        }
        _tracking.clear();
    }
};

#endif // UNIQUE_QUEUE_H 