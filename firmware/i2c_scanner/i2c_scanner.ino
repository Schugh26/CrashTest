#include <Wire.h>

#define SDA_PIN 21
#define SCL_PIN 22

void setup()
{
    Serial.begin(115200);
    delay(1000);

    Wire.begin(SDA_PIN, SCL_PIN);
    Wire.setClock(100000);

    Serial.println();
    Serial.println("I2C SCANNER START");
}

void loop()
{
    int devices = 0;

    for (uint8_t address = 1; address < 127; address++)
    {
        Wire.beginTransmission(address);
        uint8_t error = Wire.endTransmission();

        if (error == 0)
        {
            Serial.print("FOUND: 0x");

            if (address < 16)
                Serial.print("0");

            Serial.println(address, HEX);
            devices++;
        }
    }

    if (devices == 0)
        Serial.println("NO I2C DEVICES FOUND");

    Serial.println("---");

    delay(2000);
}
