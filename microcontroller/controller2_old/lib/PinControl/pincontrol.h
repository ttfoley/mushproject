#ifndef PINCONTROL_H
#define PINCONTROL_H

#include <Arduino.h>

struct PinControl {
    const int pin;  // Pin number
    float rb;  // Readback value
    float rb_last;  // Previous readback value
    const char* pin_name;  // Pin name
    const char* readback_topic;  // Readback topic
    const char* output_topic;  // Output topic
    unsigned long time_last_published; // Time last successfuly published.
    bool needs_publish;  // New flag

    PinControl(int pin, float rb_initial, float rb_last_initial, const char* pin_name, const char* readback_topic, const char* output_topic, unsigned long initial_time)
        : pin(pin), rb(rb_initial), rb_last(rb_last_initial), pin_name(pin_name), readback_topic(readback_topic), output_topic(output_topic), time_last_published(initial_time), needs_publish(true) {}

    void checkTimeToRepublish(unsigned long force_republish_freq) {
        if ((millis() - time_last_published) > force_republish_freq) {
            needs_publish = true;
        }
    }

    void updateReadback(float new_rb) {
        if (rb != new_rb) {
            rb_last = rb;
        }
        rb = new_rb;
        needs_publish = true;  // Set on write
    }

    void publishComplete() {
        needs_publish = false;
        time_last_published = millis();
    }
};

#endif