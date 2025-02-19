#include <Adafruit_SCD4x.h>

Adafruit_SCD4x scd4x;

void setup() {
  Wire.begin();
  
  if (!scd4x.begin()) {
    Serial.println("Failed to find SCD4x");
    while (1) { delay(10); }
  }

  // Stop periodic measurement (if running)
  scd4x.stopPeriodicMeasurement();
  
  // Disable automatic calibration
  scd4x.setAutomaticSelfCalibrationEnabled(false);
}

void loop() {
  // Start measurement
  scd4x.startSingleShotMeasurement();
  
  // Wait for measurement - Adafruit handles timing
  if (scd4x.getDataReady()) {
    // Read data
    if (scd4x.readData()) {
      Serial.print("CO2: "); Serial.println(scd4x.getCO2());
      Serial.print("Temperature: "); Serial.println(scd4x.getTemperature());
      Serial.print("Humidity: "); Serial.println(scd4x.getHumidity());
    }
  }
  
  delay(5000);  // Wait between measurements
} 