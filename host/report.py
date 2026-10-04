import hashlib
import html
import json
import re
import uuid

from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"

REPORTS.mkdir(exist_ok=True)


def field(pattern, text, default="UNKNOWN"):
    match = re.search(
        pattern,
        text,
        re.MULTILINE
    )

    if not match:
        return default

    return match.group(1).strip()


def build_timeline(text):
    timeline = []

    important = (
        "PHASE ",
        "Healthy IMU telemetry",
        "FAULT,SENSOR",
        "ROOT_CAUSE",
        "Safe-state response",
        "Recovery event",
        "Sensor recovery",
        "Post-recovery IMU stability",
        "FINAL VERDICT",
    )

    for line in text.splitlines():

        if not any(
            token in line
            for token in important
        ):
            continue

        timestamp = ""

        match = re.match(
            r"\[(\d\d:\d\d:\d\d\.\d+)\]\s*(.*)",
            line
        )

        if match:
            timestamp = match.group(1)
            message = match.group(2)
        else:
            message = line.strip()

        timeline.append({
            "timestamp": timestamp,
            "message": message
        })

    return timeline


def extract_evidence(text):
    evidence = []

    interesting = (
        "ESP32",
        "FREE-WILi",
        "STATE,",
        "STATUS,SENSOR",
        "FAULT,SENSOR",
        "ROOT_CAUSE",
        "SAFE,",
        "RECOVERY,SENSOR",
        "Healthy IMU",
        "Post-recovery",
    )

    for line in text.splitlines():

        if any(
            token in line
            for token in interesting
        ):
            evidence.append(
                line.strip()
            )

    return evidence[-120:]


def recommendations(record):

    verdict = record[
        "verdict"
    ]["result"]

    root = record[
        "fault"
    ]["root_cause"]

    output = []

    if verdict == "PASS":

        output.extend([
            "Repeat the fault injection for at least 10 consecutive cycles and characterize detection-latency variance.",
            "Add additional independent fault classes so firmware resilience is not demonstrated against only one sensor-failure mechanism.",
            "Record long-duration post-recovery telemetry to detect intermittent degradation after recovery.",
            "Compare nominal and stressed conditions to establish a repeatable validation envelope."
        ])

    else:

        output.extend([
            "Do not treat the tested firmware configuration as validated until the failing acceptance criterion is resolved.",
            "Inspect the evidence timeline to determine whether failure occurred during baseline validation, detection, safe-state entry, or recovery.",
            "Repeat the test after correcting the failure and compare both runs.",
            "Preserve the failing report as regression evidence."
        ])

    if root not in (
        "INJECTED_SENSOR_FAULT",
        "UNKNOWN"
    ):

        output.insert(
            0,
            f"Investigate the unexpected root cause '{root}' before repeating the requested injected-fault test."
        )

    return output


def deterministic_analysis(record):

    verdict = record[
        "verdict"
    ]["result"]

    latency = record[
        "measurements"
    ]["detection_latency_ms"]

    safe = record[
        "measurements"
    ]["safe_state"]

    recovery = record[
        "measurements"
    ]["recovery"]

    root = record[
        "fault"
    ]["root_cause"]

    if verdict == "PASS":

        summary = (
            "The DUT satisfied the deterministic CrashTest acceptance "
            "criteria for this sensor-fault scenario. A healthy baseline "
            "was established before injection, the requested fault was "
            f"classified as {root}, the safe-state requirement evaluated "
            f"as {safe}, and recovery evaluated as {recovery}."
        )

        risk = (
            "This result validates the tested scenario only. It does not "
            "prove resilience against unrelated hardware faults, electrical "
            "I2C bus faults, timing faults, power faults, or software "
            "corruption."
        )

    else:

        summary = (
            "The DUT did not satisfy all deterministic CrashTest "
            "acceptance criteria. The report should be treated as a "
            "failed validation run and retained for regression testing."
        )

        risk = (
            "A failed validation indicates that at least one required "
            "behavior was not demonstrated. Deployment decisions should "
            "not rely on this fault scenario until the failing criterion "
            "has been corrected and retested."
        )

    if latency is None:
        latency_sentence = (
            "No valid fault-detection latency was produced."
        )
    else:
        latency_sentence = (
            f"Measured detection latency was {latency:.1f} ms."
        )

    return {
        "executive_summary":
            summary + " " + latency_sentence,

        "engineering_interpretation":
            (
                "CrashTest uses deterministic rules for PASS/FAIL. "
                "FREE-WILi controls the dedicated fault-injection input, "
                "while the ESP32 firmware reports state transitions and "
                "recovery evidence. AI analysis, when enabled, is advisory "
                "and cannot modify the deterministic verdict."
            ),

        "risk_assessment":
            risk
    }


def create_record(
    console_text,
    return_code,
    started_at,
    completed_at,
    esp_port="COM9"
):

    verdict = field(
        r"FINAL VERDICT\s*:\s*([A-Z]+)",
        console_text,
        "FAIL"
    )

    root_cause = field(
        r"ROOT CAUSE\s*:\s*([^\r\n]+)",
        console_text,
        "UNKNOWN"
    )

    safe_state = field(
        r"SAFE STATE\s*:\s*([A-Z]+)",
        console_text,
        "FAIL"
    )

    recovery = field(
        r"RECOVERY\s*:\s*([A-Z]+)",
        console_text,
        "FAIL"
    )

    detail = field(
        r"DETAIL\s*:\s*([^\r\n]+)",
        console_text,
        ""
    )

    latency_raw = field(
        r"DETECTION LATENCY\s*:\s*([\d.]+)\s*ms",
        console_text,
        ""
    )

    latency = None

    if latency_raw:
        try:
            latency = float(
                latency_raw
            )
        except ValueError:
            pass

    samples_raw = field(
        r"Post-recovery IMU stability:\s*OK\s*\((\d+)\s+samples\)",
        console_text,
        "0"
    )

    try:
        samples = int(
            samples_raw
        )
    except ValueError:
        samples = 0

    test_id = (
        "CT-"
        + datetime.now().strftime(
            "%Y%m%d-%H%M%S"
        )
        + "-"
        + uuid.uuid4().hex[:4].upper()
    )

    record = {

        "schema_version":
            "2.0",

        "test_id":
            test_id,

        "project": {
            "name":
                "CrashTest",

            "description":
                "Embedded firmware resilience and deterministic fault-injection validation platform."
        },

        "timestamps": {
            "started_at":
                started_at,

            "completed_at":
                completed_at
        },

        "system": {

            "fault_injector":
                "FREE-WILi OG",

            "dut":
                "ESP32 NodeMCU-32S / ESP-WROOM-32D",

            "dut_port":
                esp_port,

            "sensor":
                "ICM-20948",

            "interface":
                "I2C",

            "freewili_main_port":
                "COM5",

            "freewili_display_port":
                "COM6",

            "injection_gpio":
                "FREE-WILi GPIO27",

            "dut_fault_input":
                "ESP32 GPIO18"
        },

        "test": {

            "name":
                "Sensor Fault Injection",

            "category":
                "Embedded Firmware Resilience",

            "requested_fault":
                "INJECTED_SENSOR_FAULT",

            "injection_path":
                "FREE-WILi GPIO27 -> ESP32 GPIO18",

            "implementation_note":
                (
                    "The current MVP asserts a dedicated hardware "
                    "fault-injection input on the DUT. The DUT firmware "
                    "then enters its sensor-failure path. This is not "
                    "represented as a direct electrical short of the "
                    "physical I2C bus."
                ),

            "acceptance_criteria": [

                "DUT must establish stable healthy IMU telemetry before injection.",

                "FREE-WILi must assert the requested sensor-fault injection.",

                "DUT must detect the sensor failure.",

                "Reported root cause must match INJECTED_SENSOR_FAULT.",

                "DUT must confirm SAFE,OK.",

                "Injected fault must be cleared.",

                "DUT must recover within the configured timeout.",

                "Post-recovery IMU telemetry must remain stable for the verification window."
            ]
        },

        "fault": {

            "requested":
                "INJECTED_SENSOR_FAULT",

            "root_cause":
                root_cause
        },

        "measurements": {

            "detection_latency_ms":
                latency,

            "safe_state":
                safe_state,

            "recovery":
                recovery,

            "post_recovery_samples":
                samples
        },

        "verdict": {

            "result":
                verdict,

            "deterministic":
                True,

            "return_code":
                return_code,

            "detail":
                detail
        },

        "timeline":
            build_timeline(
                console_text
            ),

        "evidence":
            extract_evidence(
                console_text
            ),

        "raw_console_log":
            console_text,

        "ai": {

            "provider":
                "Fetch.ai",

            "status":
                "PENDING",

            "advisory_only":
                True,

            "executive_summary":
                "",

            "risk_assessment":
                "",

            "recommendations":
                []
        }
    }

    record[
        "deterministic_analysis"
    ] = deterministic_analysis(
        record
    )

    record[
        "recommendations"
    ] = recommendations(
        record
    )

    digest_source = json.dumps(
        {
            "test_id":
                record["test_id"],

            "verdict":
                record["verdict"],

            "measurements":
                record["measurements"],

            "timeline":
                record["timeline"]
        },
        sort_keys=True
    )

    record[
        "evidence_digest_sha256"
    ] = hashlib.sha256(
        digest_source.encode(
            "utf-8"
        )
    ).hexdigest()

    return record


def report_html(record):

    e = html.escape

    verdict = record[
        "verdict"
    ]["result"]

    verdict_class = (
        "pass"
        if verdict == "PASS"
        else "fail"
    )

    latency = record[
        "measurements"
    ]["detection_latency_ms"]

    latency_text = (
        f"{latency:.1f} ms"
        if latency is not None
        else "N/A"
    )

    timeline_html = ""

    for event in record[
        "timeline"
    ]:

        timeline_html += f"""
        <div class="timeline-row">
            <div class="timeline-dot"></div>
            <div class="timeline-time">
                {e(event["timestamp"])}
            </div>
            <div class="timeline-msg">
                {e(event["message"])}
            </div>
        </div>
        """

    if not timeline_html:
        timeline_html = (
            '<div class="muted">'
            'No timeline events captured.'
            '</div>'
        )

    criteria_html = ""

    for criterion in record[
        "test"
    ]["acceptance_criteria"]:

        criteria_html += f"""
        <div class="criterion">
            <span class="check">✓</span>
            <span>{e(criterion)}</span>
        </div>
        """

    recommendations_html = ""

    for recommendation in record[
        "recommendations"
    ]:

        recommendations_html += (
            "<li>"
            + e(recommendation)
            + "</li>"
        )

    evidence_text = "\n".join(
        record["evidence"]
    )

    analysis = record[
        "deterministic_analysis"
    ]

    return f"""
<!doctype html>
<html>

<head>

<meta charset="utf-8">

<title>
CrashTest Report - {e(record["test_id"])}
</title>

<style>

* {{
    box-sizing: border-box;
}}

body {{
    margin: 0;
    background: #070b11;
    color: #edf3fb;
    font-family:
        Inter,
        "Segoe UI",
        Arial,
        sans-serif;
}}

.page {{
    max-width: 1180px;
    margin: auto;
    padding: 42px 30px 70px;
}}

.top {{
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 28px;
}}

.logo {{
    font-size: 34px;
    font-weight: 900;
}}

.logo span {{
    color: #46ead6;
}}

.subtitle {{
    color: #8090a3;
    margin-top: 6px;
}}

.verdict {{
    font-size: 24px;
    font-weight: 900;
    padding: 12px 20px;
    border-radius: 999px;
}}

.verdict.pass {{
    color: #37f17c;
    background: rgba(55,241,124,.10);
    border: 1px solid rgba(55,241,124,.28);
}}

.verdict.fail {{
    color: #ff4d59;
    background: rgba(255,77,89,.10);
    border: 1px solid rgba(255,77,89,.28);
}}

.card {{
    background: #0f161f;
    border: 1px solid #263546;
    border-radius: 16px;
    padding: 22px;
    margin-top: 16px;
}}

.hero {{
    background:
        linear-gradient(
            135deg,
            rgba(70,234,214,.08),
            transparent 45%
        ),
        #0f161f;
}}

.eyebrow {{
    color: #8090a3;
    font-size: 11px;
    letter-spacing: 1px;
    font-weight: 800;
    text-transform: uppercase;
}}

.hero h1 {{
    margin: 9px 0 5px;
    font-size: 27px;
}}

.muted {{
    color: #8090a3;
}}

.metrics {{
    display: grid;
    grid-template-columns:
        repeat(4,1fr);
    gap: 12px;
}}

.metric {{
    background: #101923;
    border: 1px solid #263546;
    border-radius: 14px;
    padding: 18px;
}}

.metric-value {{
    font-size: 23px;
    font-weight: 900;
    margin-top: 9px;
}}

.two {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
}}

h2 {{
    margin: 0 0 15px;
    font-size: 18px;
}}

p {{
    line-height: 1.65;
    color: #bdc8d5;
}}

.timeline-row {{
    display: grid;
    grid-template-columns:
        12px 90px 1fr;
    gap: 10px;
    padding: 8px 0;
}}

.timeline-dot {{
    width: 8px;
    height: 8px;
    background: #449aff;
    border-radius: 50%;
    margin-top: 5px;
}}

.timeline-time {{
    color: #6e8094;
    font-size: 12px;
}}

.timeline-msg {{
    font-size: 13px;
}}

.criterion {{
    display: flex;
    gap: 10px;
    padding: 7px 0;
    color: #c6d0dc;
}}

.check {{
    color: #37f17c;
    font-weight: 900;
}}

.ai {{
    border-top: 2px solid #ad7cff;
}}

.ai-tag {{
    color: #ba97ff;
    font-size: 11px;
    font-weight: 900;
    letter-spacing: .8px;
}}

.pending {{
    display: inline-block;
    margin-top: 12px;
    padding: 6px 10px;
    border-radius: 8px;
    background: rgba(173,124,255,.10);
    color: #ba97ff;
}}

pre {{
    white-space: pre-wrap;
    word-break: break-word;
    background: #070b10;
    border: 1px solid #1f2a36;
    padding: 17px;
    border-radius: 10px;
    color: #9eb0c3;
    font-size: 11px;
    max-height: 420px;
    overflow: auto;
}}

li {{
    color: #bdc8d5;
    margin: 10px 0;
    line-height: 1.5;
}}

.digest {{
    font-family: monospace;
    color: #75879a;
    word-break: break-all;
    font-size: 11px;
}}

.toolbar {{
    position: sticky;
    top: 10px;
    display: flex;
    justify-content: flex-end;
    margin-bottom: 12px;
    z-index: 20;
}}

.print {{
    border: 0;
    border-radius: 999px;
    background: #edf0ed;
    color: #070b11;
    padding: 12px 18px;
    font-weight: 900;
    cursor: pointer;
}}

@media print {{

    body {{
        background: white;
        color: black;
    }}

    .page {{
        padding: 0;
    }}

    .toolbar {{
        display: none;
    }}

    .card,
    .metric {{
        background: white;
        color: black;
        border-color: #ddd;
        break-inside: avoid;
    }}

    p,
    li,
    .criterion {{
        color: #222;
    }}

    .muted,
    .eyebrow {{
        color: #666;
    }}

    pre {{
        color: #222;
        background: #f6f6f6;
        max-height: none;
    }}

}}

</style>

</head>


<body>

<div class="page">

<div class="toolbar">

<button
    class="print"
    onclick="window.print()"
>
PRINT / SAVE PDF
</button>

</div>


<div class="top">

<div>

<div class="logo">
Crash<span>Test</span>
</div>

<div class="subtitle">
Embedded Firmware Resilience Evidence Report
</div>

</div>

<div class="verdict {verdict_class}">
{e(verdict)}
</div>

</div>


<div class="card hero">

<div class="eyebrow">
TEST IDENTIFICATION
</div>

<h1>
Sensor / I2C Fault Injection
</h1>

<p>
Test ID:
<strong>{e(record["test_id"])}</strong>
</p>

<p>
Started:
{e(record["timestamps"]["started_at"])}
<br>
Completed:
{e(record["timestamps"]["completed_at"])}
</p>

</div>


<div class="metrics">

<div class="metric">

<div class="eyebrow">
VERDICT
</div>

<div class="metric-value">
{e(verdict)}
</div>

</div>


<div class="metric">

<div class="eyebrow">
DETECTION LATENCY
</div>

<div class="metric-value">
{e(latency_text)}
</div>

</div>


<div class="metric">

<div class="eyebrow">
SAFE STATE
</div>

<div class="metric-value">
{e(record["measurements"]["safe_state"])}
</div>

</div>


<div class="metric">

<div class="eyebrow">
RECOVERY
</div>

<div class="metric-value">
{e(record["measurements"]["recovery"])}
</div>

</div>

</div>


<div class="two">


<div class="card">

<h2>
System Under Test
</h2>

<p>
<strong>DUT:</strong>
{e(record["system"]["dut"])}
</p>

<p>
<strong>Sensor:</strong>
{e(record["system"]["sensor"])}
</p>

<p>
<strong>Interface:</strong>
{e(record["system"]["interface"])}
</p>

<p>
<strong>DUT Serial:</strong>
{e(record["system"]["dut_port"])}
</p>

<p>
<strong>Fault Injector:</strong>
{e(record["system"]["fault_injector"])}
</p>

</div>


<div class="card">

<h2>
Fault Definition
</h2>

<p>
<strong>Requested Fault:</strong>
{e(record["fault"]["requested"])}
</p>

<p>
<strong>Observed Root Cause:</strong>
{e(record["fault"]["root_cause"])}
</p>

<p>
<strong>Injection Path:</strong>
{e(record["test"]["injection_path"])}
</p>

<p class="muted">
{e(record["test"]["implementation_note"])}
</p>

</div>


</div>


<div class="card">

<h2>
Deterministic Executive Summary
</h2>

<p>
{e(analysis["executive_summary"])}
</p>

<p>
{e(analysis["engineering_interpretation"])}
</p>

</div>


<div class="two">


<div class="card">

<h2>
Test Timeline
</h2>

{timeline_html}

</div>


<div class="card">

<h2>
Acceptance Criteria
</h2>

{criteria_html}

</div>


</div>


<div class="card">

<h2>
Risk Assessment
</h2>

<p>
{e(analysis["risk_assessment"])}
</p>

</div>


<div class="card">

<h2>
Recommended Next Actions
</h2>

<ul>
{recommendations_html}
</ul>

</div>


<div class="card ai">

<div class="ai-tag">
FETCH.AI ENGINEERING AGENT
</div>

<h2 style="margin-top:14px;">
Agent Analysis
</h2>

<div class="pending">
PENDING AGENT INTEGRATION
</div>

<p>
The deterministic report is complete without AI.
The Fetch.ai agent will later use this evidence package
to explain the result, compare historical runs and
recommend the next validation test.
</p>

<p>
<strong>
AI is never permitted to change PASS/FAIL.
</strong>
</p>

</div>


<div class="card">

<h2>
Captured Evidence
</h2>

<pre>{e(evidence_text)}</pre>

</div>


<div class="card">

<h2>
Evidence Integrity
</h2>

<div class="eyebrow">
SHA-256 EVIDENCE DIGEST
</div>

<p class="digest">
{e(record["evidence_digest_sha256"])}
</p>

<p class="muted">
This digest is generated from the deterministic
test identity, verdict, measurements and timeline.
</p>

</div>


</div>

</body>

</html>
"""


def save_report(record):

    test_id = record[
        "test_id"
    ]

    json_path = (
        REPORTS
        / f"{test_id}.json"
    )

    html_path = (
        REPORTS
        / f"{test_id}.html"
    )

    log_path = (
        REPORTS
        / f"{test_id}.log"
    )

    latest_json = (
        REPORTS
        / "latest.json"
    )

    latest_html = (
        REPORTS
        / "latest.html"
    )

    report_document = report_html(
        record
    )

    json_text = json.dumps(
        record,
        indent=2
    )

    json_path.write_text(
        json_text,
        encoding="utf-8"
    )

    html_path.write_text(
        report_document,
        encoding="utf-8"
    )

    log_path.write_text(
        record[
            "raw_console_log"
        ],
        encoding="utf-8"
    )

    latest_json.write_text(
        json_text,
        encoding="utf-8"
    )

    latest_html.write_text(
        report_document,
        encoding="utf-8"
    )

    return {
        "json": json_path,
        "html": html_path,
        "log": log_path
    }
