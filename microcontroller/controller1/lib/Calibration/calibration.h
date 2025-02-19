#ifndef CALIBRATION_H
#define CALIBRATION_H

#include <unordered_map>
#include <string>
// Define calibration parameters for each sensor instance
struct CalibrationParams {
    float humidity_slope;
    float humidity_offset;
    float temperature_slope;
    float temperature_offset;
    float co2_slope;
    float co2_offset;
};

// Calibration parameters for specific sensor instances
const CalibrationParams SHT_SENSOR_0_PARAMS = {1.0, 0.0, 1.0, 0.0, 1.0, 0.0};
const CalibrationParams DHT_SENSOR_0_PARAMS = {1.0, 0.0, 1.0, 0.0, 1.0, 0.0};
const CalibrationParams SCD_SENSOR_0_PARAMS = {1.0, 0.0, 1.0, 0.0, 1.0, 0.0};

// Add new calibration parameter constants
const CalibrationParams DS18B20_SENSOR_0_PARAMS = {1.0, 0.0, 1.0, 0.0, 1.0, 0.0};
const CalibrationParams DS18B20_SENSOR_1_PARAMS = {1.0, 0.0, 1.0, 0.0, 1.0, 0.0};

// Map sensor instance names to their calibration parameters
std::unordered_map<std::string, CalibrationParams> calibration_map = {
    {"SHT_0", SHT_SENSOR_0_PARAMS},
    {"DHT_0", DHT_SENSOR_0_PARAMS},
    {"SCD_0", SCD_SENSOR_0_PARAMS},
    {"DS18B20_0", DS18B20_SENSOR_0_PARAMS},
    {"DS18B20_1", DS18B20_SENSOR_1_PARAMS}
};

// Function to retrieve calibration parameters for a given sensor instance
CalibrationParams getCalibrationParams(const std::string& sensor_instance) {
    return calibration_map[sensor_instance];
}


#endif // CALIBRATION_H