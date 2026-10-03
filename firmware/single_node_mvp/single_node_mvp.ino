#include <Wire.h>
#include "ICM_20948.h"

// ============================================================
// CrashTest - Single Node MVP
// ESP32-32D / NodeMCU-32S
//
// ICM-20948:
//   SDA -> GPIO21
//   SCL -> GPIO22
//   I2C address -> 0x68
//
// Temporary actuator:
//   GPIO17 -> resistor -> LED -> GND
//
// Behavior:
//   Sensor healthy  -> actuator LED ON
//   Sensor lost >500 ms -> SAFE STATE -> actuator LED OFF
// ============================================================

#define SDA_PIN          21
#define SCL_PIN          22
#define ACTUATOR_PIN     17

// ICM-20948 detected at 0x68
#define AD0_VAL          0

#define SENSOR_TIMEOUT_MS 500
#define RETRY_INTERVAL_MS 1000
#define TELEMETRY_MS      100

ICM_20948_I2C imu;

bool sensorHealthy = false;
bool faultReported = false;

unsigned long lastGoodSensorMs = 0;
unsigned long lastRetryMs = 0;
unsigned long lastTelemetryMs = 0;


// ------------------------------------------------------------
// SAFE STATE
// ------------------------------------------------------------
void enterSafeState()
{
    // Temporary actuator = LED.
    // Later this becomes motor / actuator disable.
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


// ------------------------------------------------------------
// INITIALIZE / RECOVER IMU
// ------------------------------------------------------------
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


// ------------------------------------------------------------
// SETUP
// ------------------------------------------------------------
void setup()
{
    Serial.begin(115200);
    delay(1000);

    Serial.println();
    Serial.println("BOOT,CRASHTEST,SINGLE_NODE_MVP");

    pinMode(ACTUATOR_PIN, OUTPUT);

    // Always boot into a safe actuator state.
    digitalWrite(ACTUATOR_PIN, LOW);

    Wire.begin(SDA_PIN, SCL_PIN);
    Wire.setClock(100000);

    // Prevent a deliberately broken I2C bus from hanging forever.
    Wire.setTimeOut(50);

    if (!startIMU())
    {
        enterSafeState();
    }

    Serial.println("READY");
}


// ------------------------------------------------------------
// MAIN LOOP
// ------------------------------------------------------------
void loop()
{
    unsigned long now = millis();

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

                // Healthy system -> temporary actuator active.
                digitalWrite(ACTUATOR_PIN, HIGH);

                // Send telemetry every ~100 ms.
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
        // SENSOR WATCHDOG
        // ====================================================
        if (now - lastGoodSensorMs > SENSOR_TIMEOUT_MS)
        {
            enterSafeState();
        }
    }


    // ========================================================
    // AUTOMATIC RECOVERY
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
