@"
# CrashTest

Crash testing for embedded firmware using the FREE-WILi OG.

## Core idea

Cars are crash-tested before we trust them. Firmware should be too.

FREE-WILi injects controlled hardware faults into an embedded system.
CrashTest observes the response, identifies the failed subsystem,
checks whether the firmware enters a safe state, and produces an
inspection report.

## Target Hardware

- FREE-WILi OG
- ESP32
- ICM-20948 IMU
- Fault-injection switching hardware
- Laptop orchestrator

## Planned Faults

1. Sensor / I2C fault
2. UART communication fault
3. Actuator fault
"@ | Set-Content README.md