import argparse
import subprocess
import sys
import time
from pathlib import Path

import serial


GPIO = 27
HOST_DIR = Path(__file__).resolve().parent
BRIDGE = HOST_DIR / "freewili_bridge.py"

BASELINE_TIMEOUT = 10.0
FAULT_TIMEOUT = 5.0
SAFE_TIMEOUT = 3.0

# Increased recovery time
RECOVERY_TIMEOUT = 15.0

# PASS requires stable real IMU telemetry after recovery
POST_RECOVERY_STABLE_SECONDS = 3.0
POST_RECOVERY_MIN_SAMPLES = 20


def stamp():
    return time.strftime("%H:%M:%S") + f".{int((time.time() % 1) * 1000):03d}"


def log(msg=""):
    if msg:
        print(f"[{stamp()}] {msg}", flush=True)
    else:
        print(flush=True)


def fw_gpio(level):
    cmd = [
        sys.executable,
        str(BRIDGE),
        "gpio",
        str(GPIO),
        str(level),
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=5,
    )

    for line in result.stdout.splitlines():
        if line.strip():
            print(f"FREE-WILi  > {line}", flush=True)

    for line in result.stderr.splitlines():
        if line.strip():
            print(f"FREE-WILi  ! {line}", flush=True)

    if result.returncode != 0:
        raise RuntimeError(
            f"FREE-WILi GPIO command failed, level={level}"
        )


def read_line(ser):
    raw = ser.readline()

    if not raw:
        return None

    line = raw.decode(
        "utf-8",
        errors="replace"
    ).strip()

    if not line:
        return None

    print(f"ESP32      > {line}", flush=True)
    return line


def wait_for_baseline(ser, timeout):
    """
    Require consecutive real IMU telemetry before allowing a test.
    A DUT that boots already broken is NOT valid.
    """

    deadline = time.monotonic() + timeout

    samples = 0
    healthy_seen = False

    while time.monotonic() < deadline:
        line = read_line(ser)

        if line is None:
            continue

        if line == "STATE,HEALTHY":
            healthy_seen = True

        elif line == "STATUS,SENSOR,OK":
            healthy_seen = True

        elif line.startswith("STATUS,SENSOR,ERROR"):
            samples = 0
            healthy_seen = False

        elif line == "FAULT,SENSOR":
            samples = 0
            healthy_seen = False

        elif line.startswith("IMU,"):
            samples += 1

            # Need multiple real samples, not just STATUS OK.
            if healthy_seen and samples >= 8:
                return True

    return False


def wait_for_injected_fault(ser, timeout):
    deadline = time.monotonic() + timeout

    fault_seen = False
    root_cause = None

    while time.monotonic() < deadline:
        line = read_line(ser)

        if line is None:
            continue

        if line == "FAULT,SENSOR":
            fault_seen = True

        elif line.startswith("ROOT_CAUSE,"):
            root_cause = line.split(",", 1)[1]

        if fault_seen and root_cause is not None:
            return fault_seen, root_cause

    return fault_seen, root_cause


def wait_for_safe(ser, timeout):
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        line = read_line(ser)

        if line is None:
            continue

        if line == "SAFE,OK":
            return True

        if line.startswith("SAFE,") and line != "SAFE,OK":
            return False

    return False


def wait_for_recovery_event(ser, timeout):
    """
    Wait for firmware to explicitly claim recovery.
    Errors during retries are allowed, but recovery must eventually succeed.
    """

    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        line = read_line(ser)

        if line is None:
            continue

        if line == "RECOVERY,SENSOR,OK":
            return True

    return False


def verify_stable_recovery(
    ser,
    stable_seconds,
    min_samples,
    timeout=8.0
):
    """
    Critical additional verification.

    RECOVERY,SENSOR,OK by itself is NOT enough.
    We require sustained, real IMU frames afterward.
    """

    deadline = time.monotonic() + timeout

    stable_start = None
    samples = 0

    while time.monotonic() < deadline:
        line = read_line(ser)

        if line is None:
            continue

        # Any new sensor failure invalidates the stability window.
        if (
            line == "FAULT,SENSOR"
            or line.startswith("STATUS,SENSOR,ERROR")
        ):
            stable_start = None
            samples = 0
            continue

        if line.startswith("IMU,"):
            if stable_start is None:
                stable_start = time.monotonic()

            samples += 1

            elapsed = time.monotonic() - stable_start

            if (
                elapsed >= stable_seconds
                and samples >= min_samples
            ):
                return True, samples, elapsed

    return False, samples, 0.0


def print_result(
    verdict,
    root_cause,
    safe_state,
    recovery,
    latency_ms,
    reason
):
    print()
    print("=" * 56)
    print("                 CRASHTEST RESULT")
    print("=" * 56)
    print("TEST             : SENSOR / I2C FAILURE")
    print("FAILED SUBSYSTEM : SENSOR")
    print(f"ROOT CAUSE       : {root_cause}")
    print(f"SAFE STATE       : {safe_state}")
    print(f"RECOVERY         : {recovery}")

    if latency_ms is None:
        print("DETECTION LATENCY: N/A")
    else:
        print(f"DETECTION LATENCY: {latency_ms:.1f} ms")

    if reason:
        print(f"DETAIL           : {reason}")

    print("-" * 56)
    print(f"FINAL VERDICT    : {verdict}")
    print("=" * 56)
    print()


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--esp-port",
        default="COM9"
    )

    parser.add_argument(
        "--recovery-timeout",
        type=float,
        default=RECOVERY_TIMEOUT
    )

    parser.add_argument(
        "--stable-seconds",
        type=float,
        default=POST_RECOVERY_STABLE_SECONDS
    )

    args = parser.parse_args()

    verdict = "FAIL"
    root_cause = "UNKNOWN"
    safe_state = "FAIL"
    recovery = "FAIL"
    latency_ms = None
    reason = ""

    ser = None

    print()
    print("=" * 60)
    print("         CrashTest Automated SENSOR Test")
    print("=" * 60)
    print()

    try:
        # Always begin with the injected fault physically cleared.
        log("PHASE 0 - Clearing FREE-WILi fault line")
        fw_gpio(0)

        ser = serial.Serial(
            args.esp_port,
            115200,
            timeout=0.10
        )

        time.sleep(1.0)
        ser.reset_input_buffer()

        log()
        log("PHASE 1 - Verifying healthy DUT baseline")

        if not wait_for_baseline(
            ser,
            BASELINE_TIMEOUT
        ):
            reason = (
                "DUT never produced a stable healthy IMU baseline. "
                "Test injection was NOT performed."
            )

            print_result(
                verdict,
                root_cause,
                safe_state,
                recovery,
                latency_ms,
                reason
            )
            return 1

        log("Healthy IMU telemetry: OK")

        log()
        log("PHASE 2 - FREE-WILi injecting SENSOR fault")

        inject_start = time.perf_counter()
        fw_gpio(1)

        log()
        log("PHASE 3 - Waiting for SENSOR fault")

        fault_seen, observed_root = wait_for_injected_fault(
            ser,
            FAULT_TIMEOUT
        )

        if not fault_seen:
            reason = (
                "ESP32 did not detect the FREE-WILi injected fault."
            )

            fw_gpio(0)

            print_result(
                verdict,
                root_cause,
                safe_state,
                recovery,
                latency_ms,
                reason
            )
            return 1

        latency_ms = (
            time.perf_counter() - inject_start
        ) * 1000.0

        log("FAULT,SENSOR: OK")

        if observed_root is None:
            reason = "No root cause was reported."

            fw_gpio(0)

            print_result(
                verdict,
                root_cause,
                safe_state,
                recovery,
                latency_ms,
                reason
            )
            return 1

        root_cause = observed_root

        # Critical: spontaneous I2C failure must not masquerade
        # as our requested injected test.
        if root_cause != "INJECTED_SENSOR_FAULT":
            reason = (
                "Wrong root cause. Expected "
                "INJECTED_SENSOR_FAULT but received "
                f"{root_cause}."
            )

            fw_gpio(0)

            print_result(
                verdict,
                root_cause,
                safe_state,
                recovery,
                latency_ms,
                reason
            )
            return 1

        log()
        log("PHASE 4 - Verify safe state")

        if not wait_for_safe(
            ser,
            SAFE_TIMEOUT
        ):
            reason = "DUT did not confirm SAFE,OK."

            fw_gpio(0)

            print_result(
                verdict,
                root_cause,
                safe_state,
                recovery,
                latency_ms,
                reason
            )
            return 1

        safe_state = "PASS"
        log("Safe-state response: OK")

        # Short visible fault hold.
        time.sleep(0.8)

        log()
        log("PHASE 5 - FREE-WILi clearing SENSOR fault")
        fw_gpio(0)

        log()
        log(
            f"PHASE 6 - Waiting for recovery "
            f"(timeout {args.recovery_timeout:.0f}s)"
        )

        if not wait_for_recovery_event(
            ser,
            args.recovery_timeout
        ):
            reason = (
                "Firmware did not report successful recovery "
                "within the allowed time."
            )

            print_result(
                verdict,
                root_cause,
                safe_state,
                recovery,
                latency_ms,
                reason
            )
            return 1

        log("Recovery event received")

        log()
        log(
            f"PHASE 7 - Verifying {args.stable_seconds:.1f}s "
            "of stable post-recovery IMU telemetry"
        )

        stable, samples, stable_time = verify_stable_recovery(
            ser,
            args.stable_seconds,
            POST_RECOVERY_MIN_SAMPLES,
            timeout=args.stable_seconds + 8.0
        )

        if not stable:
            reason = (
                "Recovery was reported, but stable IMU telemetry "
                "was not sustained afterward."
            )

            print_result(
                verdict,
                root_cause,
                safe_state,
                recovery,
                latency_ms,
                reason
            )
            return 1

        recovery = "PASS"

        log(
            f"Post-recovery IMU stability: OK "
            f"({samples} samples)"
        )

        verdict = "PASS"
        reason = (
            f"Healthy baseline + injected fault + safe state + "
            f"recovery + {args.stable_seconds:.1f}s stable telemetry."
        )

        print_result(
            verdict,
            root_cause,
            safe_state,
            recovery,
            latency_ms,
            reason
        )

        return 0

    except KeyboardInterrupt:
        reason = "Test stopped by operator."

        print_result(
            "STOPPED",
            root_cause,
            safe_state,
            recovery,
            latency_ms,
            reason
        )

        return 130

    except Exception as exc:
        reason = f"{type(exc).__name__}: {exc}"

        print_result(
            "FAIL",
            root_cause,
            safe_state,
            recovery,
            latency_ms,
            reason
        )

        return 1

    finally:
        # Fail-safe: never intentionally leave injected fault HIGH.
        try:
            fw_gpio(0)
        except Exception:
            pass

        if ser is not None:
            try:
                ser.close()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
