import json

from pathlib import Path

from flask import (
    Flask,
    abort,
    jsonify,
    render_template,
    send_file
)


ROOT = Path(__file__).resolve().parents[1]

REPORTS = ROOT / "reports"

REPORTS.mkdir(
    exist_ok=True
)

app = Flask(__name__)


def read_json(
    path,
    fallback=None
):

    try:

        return json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

    except Exception:

        return fallback


def reports_list():

    output = []

    for path in REPORTS.glob(
        "CT-*.json"
    ):

        data = read_json(
            path
        )

        if data:
            output.append(
                data
            )

    output.sort(

        key=lambda item:
            item.get(
                "timestamps",
                {}
            ).get(
                "completed_at",
                ""
            ),

        reverse=True
    )

    return output


@app.route("/")
def home():

    return render_template(
        "index.html"
    )


@app.route("/api/live")
def api_live():

    return jsonify(

        read_json(

            REPORTS
            / "live.json",

            {
                "state":
                    "IDLE",

                "running":
                    False,

                "last_line":
                    "Waiting for CrashTest..."
            }
        )
    )


@app.route("/api/ui")
def api_ui():

    return jsonify(

        read_json(

            REPORTS
            / "ui_state.json",

            {
                "state":
                    "HOME",

                "last_button":
                    None,

                "last_button_time":
                    0,

                "latest_report":
                    None
            }
        )
    )


@app.route("/api/reports")
def api_reports():

    output = []

    for record in reports_list()[:25]:

        output.append({

            "test_id":
                record.get(
                    "test_id"
                ),

            "verdict":
                record.get(
                    "verdict",
                    {}
                ).get(
                    "result",
                    "UNKNOWN"
                ),

            "root_cause":
                record.get(
                    "fault",
                    {}
                ).get(
                    "root_cause",
                    "UNKNOWN"
                ),

            "latency":
                record.get(
                    "measurements",
                    {}
                ).get(
                    "detection_latency_ms"
                ),

            "safe":
                record.get(
                    "measurements",
                    {}
                ).get(
                    "safe_state",
                    "UNKNOWN"
                ),

            "recovery":
                record.get(
                    "measurements",
                    {}
                ).get(
                    "recovery",
                    "UNKNOWN"
                )
        })

    return jsonify(
        output
    )


@app.route(
    "/api/report/<test_id>"
)
def api_report(
    test_id
):

    path = (
        REPORTS
        / f"{test_id}.json"
    )

    if not path.exists():
        abort(404)

    return jsonify(
        read_json(
            path
        )
    )


@app.route(
    "/report/<test_id>"
)
def report_page(
    test_id
):

    path = (
        REPORTS
        / f"{test_id}.html"
    )

    if not path.exists():
        abort(404)

    return send_file(
        path
    )


@app.route(
    "/latest-report"
)
def latest_report():

    path = (
        REPORTS
        / "latest.html"
    )

    if not path.exists():

        return """
        <body style="
            background:#070b11;
            color:#edf3fb;
            font-family:Arial;
            padding:60px;
        ">

        <h1>
        CrashTest
        </h1>

        <h2>
        No engineering report yet.
        </h2>

        <p>
        Complete a CrashTest first.
        </p>

        </body>
        """, 404

    return send_file(
        path
    )


@app.route(
    "/download/<test_id>/json"
)
def download_json(
    test_id
):

    path = (
        REPORTS
        / f"{test_id}.json"
    )

    if not path.exists():
        abort(404)

    return send_file(
        path,
        as_attachment=True
    )


@app.route(
    "/download/<test_id>/log"
)
def download_log(
    test_id
):

    path = (
        REPORTS
        / f"{test_id}.log"
    )

    if not path.exists():
        abort(404)

    return send_file(
        path,
        as_attachment=True
    )


if __name__ == "__main__":

    app.run(

        host=
            "127.0.0.1",

        port=
            5050,

        debug=
            False
    )
