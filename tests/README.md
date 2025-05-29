# Test Suite

Comprehensive testing for the mushroom automation system.

## Structure

- **`microcontroller/`** - Tests for individual controller firmware (C1, C2, C3)
- **`control/`** - Tests for Python control system components  
- **`mqtt/`** - MQTT protocol and message flow tests
- **`system/`** - End-to-end integration and performance tests

## Running Tests

### Controller C2 (Actuator Controller)
```bash
./tests/microcontroller/test_controller2.sh
```

Tests:
- ✅ Latest Command Wins logic
- ✅ All actuators (humidifier, heating pad, light, vent fan)
- ✅ Invalid command handling
- ✅ Periodic readback republishing
- System status monitoring

**Prerequisites:** C2 firmware running, MQTT broker accessible

## Test Results

Controller C2: ✅ **PASSED** - Core FSM functionality validated

## Future Tests

- Controller C1 (sensor tests)
- Controller C3 (CO2 sensor tests) 
- Cross-controller integration
- Performance and stress testing 