"""
CrashTest deterministic diagnosis engine.

AI will later explain the evidence, but it will NOT decide PASS/FAIL.
"""

from dataclasses import dataclass, asdict
import argparse
import json
import time

import serial


@dataclass
class TestResult:
    status: str = "HEALTHY"
    subsystem: str = "NONE"
    root_cause: str = "NONE"

    safe_state: str = "UNKNOWN"
    recovery: str = "UNKNOWN"

    imu_samples: int = 0
    malformed_lines: int = 0


class DiagnosisEngine:

    def __init__(self):
        self.result = TestResult()
        self.evidence = []

    def process_line(self, line: str):
        line = line.strip()

        if not line:
            return

        self.evidence.append(line)

        # ----------------------------
        # IMU TELEMETRY
        # ----------------------------
        if line.startswith("IMU,"):
            parts = line.split(",")

            if len(parts) == 4:
                try:
                    float(parts[1])
                    float(parts[2])
                    float(parts[3])

                    self.result.imu_samples += 1
                except ValueError:
                    self.result.malformed_lines += 1
            else:
                self.result.malformed_lines += 1

            return

        # ----------------------------
        # SENSOR FAULT
        # ----------------------------
        if line == "FAULT,SENSOR":
            self.result.status = "FAULT"
            self.result.subsystem = "SENSOR"
            return

        # ----------------------------
        # ROOT CAUSE
        # ----------------------------
        if line.startswith("ROOT_CAUSE,"):
            self.result.root_cause = line.split(",", 1)[1]
            return

        # ----------------------------
        # SAFE STATE
        # ----------------------------
        if line == "SAFE,OK":
            self.result.safe_state = "PASS"
            return

        if line == "SAFE,FAIL":
            self.result.safe_state = "FAIL"
            return

        # ----------------------------
        # RECOVERY
        # ----------------------------
        if line == "RECOVERY,SENSOR,OK":
            self.result.recovery = "PASS"
            return

        # System recovered to healthy state
        if line == "STATE,HEALTHY":
            if self.result.status == "FAULT":
                self.result.recovery = "PASS"

            return

    def verdict(self):
        """
        Overall test verdict.

        A crash test passes when:
        - a fault was actually detected
        - safe state was successfully entered
        """

        if (
            self.result.status == "FAULT"
            and self.result.safe_state == "PASS"
        ):
            return "PASS"

        if (
            self.result.status == "FAULT"
            and self.result.safe_state == "FAIL"
        ):
            return "FAIL"

        return "INCOMPLETE"

    def summary(self):
        data = asdict(self.result)
        data["verdict"] = self.verdict()
        data["evidence"] = self.evidence.copy()

        return data


def print_summary(engine: DiagnosisEngine):

    result = engine.summary()

    print()
    print("=" * 40)
    print("       CRASHTEST DIAGNOSIS")
    print("=" * 40)

    print(f"STATUS      : {result['status']}")
    print(f"SUBSYSTEM   : {result['subsystem']}")
    print(f"ROOT CAUSE  : {result['root_cause']}")
    print(f"SAFE STATE  : {result['safe_state']}")
    print(f"RECOVERY    : {result['recovery']}")
    print(f"IMU SAMPLES : {result['imu_samples']}")

    print("-" * 40)
    print(f"VERDICT     : {result['verdict']}")
    print("=" * 40)


def run_demo():

    demo_lines = [
        "BOOT,CRASHTEST,SINGLE_NODE_MVP",
        "STATUS,SENSOR,OK",
        "STATE,HEALTHY",
        "READY",
        "IMU,-20.2,15.1,999.3",
        "IMU,-22.1,16.0,1001.0",

        "FAULT,SENSOR",
        "ROOT_CAUSE,IMU_COMMUNICATION_LOST",
        "SAFE,OK",
        "STATE,FAULT",

        "RECOVERY,SENSOR,TRY",
        "STATUS,SENSOR,OK",
        "STATE,HEALTHY",
        "RECOVERY,SENSOR,OK",
    ]

    engine = DiagnosisEngine()

    print("CrashTest diagnosis demo")
    print()

    for line in demo_lines:
        print("ESP32:", line)
        engine.process_line(line)

    print_summary(engine)


def monitor_serial(port, seconds):

    engine = DiagnosisEngine()

    print(f"Monitoring ESP32 on {port}")
    print(f"Duration: {seconds} seconds")
    print()
    print("Create a sensor fault during this window.")
    print()

    try:
        with serial.Serial(
            port=port,
            baudrate=115200,
            timeout=0.1,
        ) as ser:

            # Allow ESP32 serial connection to settle
            time.sleep(0.5)

            start = time.time()

            while time.time() - start < seconds:

                raw = ser.readline()

                if not raw:
                    continue

                line = raw.decode(
                    "utf-8",
                    errors="replace"
                ).strip()

                if not line:
                    continue

                print("ESP32:", line)

                engine.process_line(line)

    except serial.SerialException as exc:

        print(f"Serial error: {exc}")
        return 1

    print_summary(engine)

    print()
    print("JSON:")
    print(
        json.dumps(
            engine.summary(),
            indent=2
        )
    )

    return 0


def main():

    parser = argparse.ArgumentParser(
        description="CrashTest deterministic diagnosis engine"
    )

    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run without hardware using recorded sample data"
    )

    parser.add_argument(
        "--port",
        help="ESP32 serial port, for example COM9"
    )

    parser.add_argument(
        "--seconds",
        type=int,
        default=15,
        help="Monitoring duration"
    )

    args = parser.parse_args()

    if args.demo:
        run_demo()
        return

    if not args.port:
        parser.error(
            "Use --demo or specify ESP32 port with --port COMx"
        )

    raise SystemExit(
        monitor_serial(
            args.port,
            args.seconds
        )
    )


if __name__ == "__main__":
    main()
