#ifndef TIMING_CONSTANTS_H
#define TIMING_CONSTANTS_H

// Measurement timings
#define MEASURE_TIME 8000            // Time to wait for SCD40 measurement (ms)
#define MEASURE_TIMEOUT 10000        // Maximum time to stay in measuring state (ms)
#define DEFAULT_WAIT 1000           // Default state machine wait time
#define WAIT_WAIT 10               // Wait time in WAIT state
#define READ_DELAY_MS 100          // Delay between sensor reads
#define SCD_PUBLISH_INTERVAL 45000  // How often to publish SCD data (ms)

// Timeout constants
#define MAX_TIME_NO_PUBLISH 300000  // Failsafe timeout
#define WIFI_DURATION_POST_INTERVAL 30000
#define MAX_WIFI_ATTEMPTS 12
#define WIFI_ATTEMPT_DELAY 15000
#define MAX_MQTT_ATTEMPTS 10
#define MQTT_ATTEMPT_DELAY 6000
#define DELAY_AFTER_SENSOR_POST 100

#endif // TIMING_CONSTANTS_H 