import argparse
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import serial


ROOT = Path(__file__).resolve().parents[1]
HOST = ROOT / "host"

ORCHESTRATOR = HOST / "run_and_report.py"
BRIDGE = HOST / "freewili_bridge.py"

panel = None
panel_lock = threading.Lock()

process_lock = threading.Lock()
current_process = None

state_lock = threading.Lock()
controller_state = "HOME"

stop_requested = threading.Event()


def set_controller_state(new_state):
    global controller_state

    with state_lock:
        controller_state = new_state


def get_controller_state():
    with state_lock:
        return controller_state



UI_STATE_PATH = ROOT / "reports" / "ui_state.json"


def write_dashboard_state(
    state=None,
    button=None
):
    """
    Mirrors FREE-WILi state/buttons into the Flask dashboard.
    This does NOT control or modify the hardware.
    """

    UI_STATE_PATH.parent.mkdir(
        exist_ok=True
    )

    data = {
        "state": "HOME",
        "last_button": None,
        "last_button_time": 0
    }

    try:

        if UI_STATE_PATH.exists():

            data.update(
                json.loads(
                    UI_STATE_PATH.read_text(
                        encoding="utf-8"
                    )
                )
            )

    except Exception:
        pass


    if state is not None:
        data["state"] = state


    if button is not None:

        import time

        data["last_button"] = button

        data["last_button_time"] = (
            time.time()
        )


    UI_STATE_PATH.write_text(
        json.dumps(
            data,
            indent=2
        ),
        encoding="utf-8"
    )


def send_ui(state):
    write_dashboard_state(state=state)
    global panel

    if panel is None:
        return

    msg = f"UI,{state}\n"

    with panel_lock:
        try:
            panel.write(
                msg.encode("ascii")
            )

            panel.flush()

        except Exception as exc:
            print(
                f"Panel write error: {exc}",
                flush=True
            )

    print(
        f"FREE-WILi UI > {state}",
        flush=True
    )


def force_fault_clear():
    try:
        subprocess.run(
            [
                sys.executable,
                str(BRIDGE),
                "gpio",
                "27",
                "0",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=5,
        )

    except Exception:
        pass


def stop_running_test():
    global current_process

    stop_requested.set()

    with process_lock:
        proc = current_process

    if proc is not None:
        try:
            if proc.poll() is None:
                proc.terminate()
        except Exception:
            pass

    # Hardware fail-safe
    force_fault_clear()


def run_test():
    global current_process

    stop_requested.clear()

    set_controller_state("RUNNING")
    send_ui("CHECKING")

    cmd = [
        sys.executable,
        str(ORCHESTRATOR),
        "--esp-port",
        ARGS.esp_port,

        # Increased recovery window
        "--recovery-timeout",
        "15",

        # Require sustained recovery
        "--stable-seconds",
        "3",
    ]

    proc = subprocess.Popen(
        cmd,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    with process_lock:
        current_process = proc


    final_result = None


    try:

        for raw in proc.stdout:

            if stop_requested.is_set():
                break

            line = raw.rstrip()

            if line:
                print(line, flush=True)


            if (
                "Healthy IMU telemetry: OK"
                in line
            ):
                send_ui("HEALTHY")


            elif (
                "PHASE 2 - FREE-WILi injecting"
                in line
            ):
                send_ui("INJECTING")


            elif (
                "FAULT,SENSOR: OK"
                in line
            ):
                send_ui("FAULT")


            elif (
                "PHASE 6 - Waiting for recovery"
                in line
            ):
                send_ui("RECOVERING")


            elif (
                "PHASE 7 - Verifying"
                in line
            ):
                send_ui("RECOVERING")


            elif (
                "FINAL VERDICT"
                in line
                and "PASS" in line
            ):
                final_result = "PASS"


            elif (
                "FINAL VERDICT"
                in line
                and "FAIL" in line
            ):
                final_result = "FAIL"


        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.terminate()


        if stop_requested.is_set():

            force_fault_clear()

            set_controller_state("HOME")

            # RED button already puts the device home,
            # but this also guarantees synchronization.
            send_ui("HOME")

            print()
            print("TEST STOPPED BY OPERATOR")
            print()

            return


        if final_result == "PASS":

            set_controller_state("PASS")
            send_ui("PASS")

            print()
            print(
                "FREE-WILi RESULT SCREEN: PASS"
            )
            print()


        else:

            set_controller_state("FAIL")
            send_ui("FAIL")

            print()
            print(
                "FREE-WILi RESULT SCREEN: FAIL"
            )
            print()


    finally:

        force_fault_clear()

        with process_lock:
            current_process = None


def handle_start():
    state = get_controller_state()

    if state == "RUNNING":
        return

    set_controller_state("ARMED")

    send_ui("ARMED")

    print()
    print("SYSTEM ARMED")
    print("GREEN = INJECT")
    print("RED   = STOP")
    print()


def handle_inject():
    state = get_controller_state()

    if state != "ARMED":
        return

    print()
    print("INJECT REQUEST ACCEPTED")
    print("Starting validated CrashTest...")
    print()

    worker = threading.Thread(
        target=run_test,
        daemon=True
    )

    worker.start()


def handle_stop():

    print()
    print("RED STOP PRESSED")
    print("Clearing fault and returning HOME.")
    print()

    stop_running_test()

    set_controller_state("HOME")
    send_ui("HOME")


def main():
    global panel
    global ARGS

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--esp-port",
        default="COM9"
    )

    parser.add_argument(
        "--panel-port",
        default="COM6"
    )

    ARGS = parser.parse_args()


    print("=" * 60)
    print("       CRASHTEST FREE-WILI CONTROL PANEL")
    print("=" * 60)
    print(
        f"FREE-WILi display : {ARGS.panel_port}"
    )
    print(
        f"ESP32             : {ARGS.esp_port}"
    )
    print()
    print("YELLOW = START")
    print("GREEN  = INJECT")
    print("RED    = STOP / HOME")
    print()


    force_fault_clear()


    panel = serial.Serial(
        ARGS.panel_port,
        115200,
        timeout=0.10
    )

    time.sleep(0.5)

    panel.reset_input_buffer()

    set_controller_state("HOME")
    send_ui("HOME")


    try:

        while True:

            raw = panel.readline()

            if not raw:
                continue


            line = raw.decode(
                "utf-8",
                errors="replace"
            ).strip()


            if not line:
                continue


            print(
                f"FREE-WILi > {line}",
                flush=True
            )


            if (
                "CRASHTEST,START"
                in line
            ):
                handle_start()


            elif (
                "CRASHTEST,INJECT"
                in line
            ):
                handle_inject()


            elif (
                "CRASHTEST,STOP"
                in line
            ):
                handle_stop()


    except KeyboardInterrupt:

        print()
        print(
            "Controller stopped from keyboard."
        )


    finally:

        stop_running_test()

        try:
            send_ui("HOME")
        except Exception:
            pass

        try:
            panel.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()

