"""Flask web application for TraceLogic."""

from __future__ import annotations
import csv
import io
import os
import webbrowser
import threading
from datetime import datetime, timedelta

from flask import Flask, render_template, request, jsonify, Response, session

from tracelogic.parser import TraceFileParser
from tracelogic.models import TraceAnalysisResult

app = Flask(__name__)
app.secret_key = os.urandom(24)

# In-memory store for last parse result (single-user use)
_last_result: dict | None = None


def _serialize_result(result: TraceAnalysisResult) -> dict:
    """Convert TraceAnalysisResult to JSON-serializable dict."""

    def fmt_dt(v):
        return v.isoformat() if isinstance(v, datetime) else (str(v) if v else "")

    def fmt_td(v):
        if isinstance(v, timedelta):
            total = int(v.total_seconds())
            h, rem = divmod(total, 3600)
            m, s = divmod(rem, 60)
            return f"{h:02d}:{m:02d}:{s:02d}"
        return str(v) if v else ""

    entries = [
        {
            "LineNumber": e.LineNumber,
            "Timestamp": fmt_dt(e.Timestamp),
            "Source": e.Source,
            "Command": e.Command,
            "Status": e.Status.value,
            "Details": e.Details,
        }
        for e in result.AllEntries
    ]

    steps = [
        {
            "ActionType": s.ActionType.value,
            "StartTime": fmt_dt(s.StartTime),
            "EndTime": fmt_dt(s.EndTime),
            "Duration": fmt_td(s.Duration),
            "StartLineNumber": s.StartLineNumber,
            "ChannelActionsCount": len(s.ChannelActions),
        }
        for s in result.PipettingSteps
    ]

    transfers = [
        {
            "Timestamp": fmt_dt(t.Timestamp),
            "ChannelId": t.ChannelId,
            "SourceLabware": t.SourceLabware,
            "SourcePositionId": t.SourcePositionId,
            "TargetLabware": t.TargetLabware,
            "TargetPositionId": t.TargetPositionId,
            "Volume": t.Volume if t.Volume is not None else "",
            "TipLabwareId": t.TipLabwareId,
            "TipPositionId": t.TipPositionId,
        }
        for t in result.LiquidTransfers
    ]

    summary = (
        f"File: {result.FileName} | "
        f"Entries: {len(result.AllEntries)} | "
        f"Steps: {len(result.PipettingSteps)} | "
        f"Transfers: {len(result.LiquidTransfers)}"
        + (f" | Errors: {len(result.Errors)}" if result.Errors else "")
    )

    return {
        "entries": entries,
        "steps": steps,
        "transfers": transfers,
        "summary": summary,
        "errors": result.Errors,
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/parse", methods=["POST"])
def parse():
    global _last_result
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "Empty filename"}), 400

    content = f.read().decode("utf-8", errors="replace")
    lines = content.splitlines()

    parser = TraceFileParser()
    result = parser.parse_lines(lines)
    result.FileName = f.filename

    data = _serialize_result(result)
    _last_result = data
    return jsonify(data)


@app.route("/export")
def export():
    global _last_result
    if _last_result is None:
        return "No data to export. Please parse a file first.", 400

    transfers = _last_result["transfers"]
    if not transfers:
        return "No liquid transfer data to export.", 400

    columns = [
        "Timestamp", "ChannelId", "SourceLabware", "SourcePositionId",
        "TargetLabware", "TargetPositionId", "Volume", "TipLabwareId", "TipPositionId",
    ]

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(transfers)

    output = buf.getvalue()
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=liquid_transfers.csv"},
    )


def _open_browser():
    webbrowser.open("http://localhost:5000")


if __name__ == "__main__":
    threading.Timer(1.0, _open_browser).start()
    app.run(host="0.0.0.0", port=5000, debug=False)
