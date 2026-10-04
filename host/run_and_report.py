import argparse
import json
import subprocess
import sys

from datetime import datetime, timezone
from pathlib import Path

from report import create_record, save_report


ROOT = Path(__file__).resolve().parents[1]
HOST = ROOT / "host"
REPORTS = ROOT / "reports"

ORCHESTRATOR = HOST / "orchestrator.py"
LIVE = REPORTS / "live.json"
UI_STATE = REPORTS / "ui_state.json"

REPORTS.mkdir(exist_ok=True)


def timestamp():
    return datetime.now(
        timezone.utc
    ).isoformat()


def write_live(
    state,
    running,
    line="",
    report_id=None
):
    data = {
        "state": state,
        "running": running,
        "last_line": line,
        "report_id": report_id,
        "updated_at": timestamp()
    }

    LIVE.write_text(
        json.dumps(
            data,
            indent=2
        ),
        encoding="utf-8"
    )


def update_ui_report(
    report_id
):
    data = {}

    try:
        if UI_STATE.exists():
            data = json.loads(
                UI_STATE.read_text(
                    encoding="utf-8"
                )
            )
    except Exception:
        data = {}

    data["latest_report"] = report_id

    UI_STATE.write_text(
        json.dumps(
            data,
            indent=2
        ),
        encoding="utf-8"
    )


def state_from_line(line):

    if "Healthy IMU telemetry: OK" in line:
        return "HEALTHY"

    if "PHASE 2 - FREE-WILi injecting" in line:
        return "INJECTING"

    if "FAULT,SENSOR: OK" in line:
        return "FAULT"

    if "PHASE 6 - Waiting for recovery" in line:
        return "RECOVERING"

    if "PHASE 7 - Verifying" in line:
        return "VERIFYING"

    if "FINAL VERDICT" in line and "PASS" in line:
        return "PASS"

    if "FINAL VERDICT" in line and "FAIL" in line:
        return "FAIL"

    return None


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--esp-port",
        default="COM9"
    )

    parser.add_argument(
        "--recovery-timeout",
        default="15"
    )

    parser.add_argument(
        "--stable-seconds",
        default="3"
    )

    args = parser.parse_args()

    started_at = timestamp()

    write_live(
        "CHECKING",
        True,
        "CrashTest started."
    )

    command = [
        sys.executable,
        str(ORCHESTRATOR),

        "--esp-port",
        args.esp_port,

        "--recovery-timeout",
        str(args.recovery_timeout),

        "--stable-seconds",
        str(args.stable_seconds)
    ]

    process = subprocess.Popen(
        command,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    console = []
    last_state = "CHECKING"

    for raw in process.stdout:

        line = raw.rstrip()

        console.append(line)

        print(
            line,
            flush=True
        )

        detected_state = state_from_line(
            line
        )

        if detected_state:
            last_state = detected_state

        write_live(
            last_state,
            True,
            line
        )

    return_code = process.wait()

    completed_at = timestamp()

    console_text = "\n".join(
        console
    )

    record = create_record(
        console_text=console_text,
        return_code=return_code,
        started_at=started_at,
        completed_at=completed_at,
        esp_port=args.esp_port
    )

    paths = save_report(
        record
    )

    report_id = record["test_id"]

    update_ui_report(
        report_id
    )

    final_state = record[
        "verdict"
    ]["result"]

    write_live(
        final_state,
        False,
        (
            "CrashTest complete. "
            f"Report {report_id} generated."
        ),
        report_id
    )

    print()
    print("=" * 62)
    print("           CRASHTEST ENGINEERING REPORT")
    print("=" * 62)
    print(f"TEST ID : {report_id}")
    print(f"JSON    : {paths['json']}")
    print(f"HTML    : {paths['html']}")
    print(f"LOG     : {paths['log']}")
    print("=" * 62)

    return return_code


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
