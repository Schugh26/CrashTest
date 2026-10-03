# CrashTest Protocol

All runtime messages are newline-terminated ASCII text at 115200 baud.

## ESP32 Single-Node MVP

### Boot
BOOT,CRASHTEST,SINGLE_NODE_MVP

### Ready
READY

### Healthy sensor
STATUS,SENSOR,OK

### Healthy state
STATE,HEALTHY

### IMU telemetry
IMU,<ax>,<ay>,<az>

Example:
IMU,-24.5,18.3,1001.2

### Sensor fault
FAULT,SENSOR

### Root cause
ROOT_CAUSE,IMU_COMMUNICATION_LOST

### Safe-state result
SAFE,OK
SAFE,FAIL

### Fault state
STATE,FAULT

### Recovery
RECOVERY,SENSOR,TRY
RECOVERY,SENSOR,OK

## Planned Two-Node Protocol

Node A -> Node B:

HB,<seq>,<ms>
IMU,<ax>,<ay>,<az>

Node B status:

SAFE,OK
SAFE,FAIL
