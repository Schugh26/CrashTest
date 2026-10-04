#include <Wire.h>
#include "ICM_20948.h"

// ============================================================
// CrashTest - Single Node MVP
// ESP32-32D / NodeMCU-32S
//
// ICM-20948:
//   SDA -> GPIO21
//   SCL -> GPIO22
//   VCC -> 3.3V
//   GND -> GND
//
// Temporary actuator:
//   GPIO17 -> resistor -> LED -> GND
//
// FREE-WILi fault control:
//   Maestro GPIO27 -> ESP32 GPIO18
//   Maestro GND    -> ESP32 GND
//
// Logic:
//   GPIO18 LOW  = normal operation
//   GPIO18 HIGH = injected SENSOR fault
// ============================================================

#define SDA_PIN              21
#define SCL_PIN              22
#define ACTUATOR_PIN         17
#define FAULT_IN_PIN         18

#define AD0_VAL              0

#define SENSOR_TIMEOUT_MS    500
#define RETRY_INTERVAL_MS    1000
#define TELEMETRY_MS         100

ICM_20948_I2C imu;

bool sensorHealthy = false;
bool faultReported = false;

unsigned long lastGoodSensorMs = 0;
unsigned long lastRetryMs = 0;
unsigned long lastTelemetryMs = 0;


// ============================================================
// SAFE STATE - REAL SENSOR FAILURE
// ============================================================
void enterSensorSafeState()
{
    digitalWrite(ACTUATOR_PIN, LOW);

    sensorHealthy = false;

    if (!faultReported)
    {
        Serial.println("FAULT,SENSOR");
        Serial.println("ROOT_CAUSE,IMU_COMMUNICATION_LOST");
        Serial.println("SAFE,OK");
        Serial.println("STATE,FAULT");

        faultReported = true;
    }
}


// ============================================================
// SAFE STATE - FREE-WILI INJECTED FAULT
// ============================================================
void enterInjectedSafeState()
{
    digitalWrite(ACTUATOR_PIN, LOW);

    sensorHealthy = false;

    if (!faultReported)
    {
        Serial.println("FAULT,SENSOR");
        Serial.println("ROOT_CAUSE,INJECTED_SENSOR_FAULT");
        Serial.println("SAFE,OK");
        Serial.println("STATE,FAULT");

        faultReported = true;
    }
}


// ============================================================
// INITIALIZE / RECOVER IMU
// ============================================================
bool startIMU()
{
    imu.begin(Wire, AD0_VAL);

    if (imu.status == ICM_20948_Stat_Ok)
    {
        sensorHealthy = true;
        faultReported = false;

        lastGoodSensorMs = millis();

        digitalWrite(ACTUATOR_PIN, HIGH);

        Serial.println("STATUS,SENSOR,OK");
        Serial.println("STATE,HEALTHY");

        return true;
    }

    Serial.print("STATUS,SENSOR,ERROR,");
    Serial.println(imu.statusString());

    sensorHealthy = false;

    return false;
}


// ============================================================
// SETUP
// ============================================================
void setup()
{
    Serial.begin(115200);
    delay(1000);

    Serial.println();
    Serial.println("BOOT,CRASHTEST,SINGLE_NODE_MVP");

    // Temporary actuator
    pinMode(ACTUATOR_PIN, OUTPUT);
    digitalWrite(ACTUATOR_PIN, LOW);

    // FREE-WILi fault input
    pinMode(FAULT_IN_PIN, INPUT_PULLDOWN);

    // I2C
    Wire.begin(SDA_PIN, SCL_PIN);
    Wire.setClock(100000);
    Wire.setTimeOut(50);

    if (!startIMU())
    {
        enterSensorSafeState();
    }

    Serial.println("READY");
}


// ============================================================
// MAIN LOOP
// ============================================================
void loop()
{
    unsigned long now = millis();

    // ========================================================
    // FREE-WILI HARDWARE COMMAND INPUT
    // ========================================================
    bool injectedFault =
        digitalRead(FAULT_IN_PIN) == HIGH;

    if (injectedFault)
    {
        enterInjectedSafeState();

        // Do not attempt recovery while FREE-WILi
        // is intentionally holding the fault HIGH.
        delay(20);
        return;
    }


    // ========================================================
    // NORMAL SENSOR OPERATION
    // ========================================================
    if (sensorHealthy)
    {
        if (imu.dataReady())
        {
            imu.getAGMT();

            if (imu.status == ICM_20948_Stat_Ok)
            {
                lastGoodSensorMs = now;

                // Healthy DUT -> actuator enabled
                digitalWrite(ACTUATOR_PIN, HIGH);

                if (now - lastTelemetryMs >= TELEMETRY_MS)
                {
                    lastTelemetryMs = now;

                    Serial.print("IMU,");
                    Serial.print(imu.accX(), 1);
                    Serial.print(",");
                    Serial.print(imu.accY(), 1);
                    Serial.print(",");
                    Serial.println(imu.accZ(), 1);
                }
            }
        }

        // ====================================================
        // REAL SENSOR WATCHDOG
        // ====================================================
        if (now - lastGoodSensorMs > SENSOR_TIMEOUT_MS)
        {
            enterSensorSafeState();
        }
    }


    // ========================================================
    // RECOVERY
    //
    // Reached when:
    // - a real sensor fault clears, OR
    // - FREE-WILi GPIO27 goes back LOW
    // ========================================================
    if (!sensorHealthy &&
        now - lastRetryMs >= RETRY_INTERVAL_MS)
    {
        lastRetryMs = now;

        Serial.println("RECOVERY,SENSOR,TRY");

        if (startIMU())
        {
            Serial.println("RECOVERY,SENSOR,OK");
        }
    }

    delay(20);
}
