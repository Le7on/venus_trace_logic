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
            "LiquidClass": s.LiquidClass or "",
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
            "LiquidClass": t.LiquidClass or "",
        }
        for t in result.LiquidTransfers
    ]

    liquid_levels = [
        {
            "Timestamp": fmt_dt(lv.Timestamp),
            "StartLineNumber": lv.StartLineNumber,
            "ChannelLevels": {str(k): v for k, v in lv.ChannelLevels.items()},
        }
        for lv in result.LiquidLevels
    ]

    variables = [
        {
            "Timestamp": fmt_dt(v.Timestamp),
            "LineNumber": v.LineNumber,
            "Name": v.Name or "",
            "Value": v.Value or "",
            "RawDetail": v.RawDetail,
        }
        for v in result.Variables
    ]

    sql_stmts = [
        {
            "Timestamp": fmt_dt(s.Timestamp),
            "LineNumber": s.LineNumber,
            "SqlType": s.SqlType,
            "Database": s.Database or "",
            "TableOrProc": s.TableOrProc or "",
            "Label": s.Label or "",
            "IsTruncated": "⚠️ Yes" if s.IsTruncated else "No",
            "Statement": s.Statement,
        }
        for s in result.SqlStatements
    ]

    sequences = [
        {
            "Timestamp": fmt_dt(s.Timestamp),
            "LineNumber": s.LineNumber,
            "Name": s.Name or "",
            "Current": s.Current if s.Current is not None else "",
            "Count": s.Count if s.Count is not None else "",
            "Total": s.Total if s.Total is not None else "",
            "Max": s.Max if s.Max is not None else "",
            "Used": s.Used if s.Used is not None else "",
            "LabwareId": s.LabwareId or "",
            "PositionId": s.PositionId or "",
        }
        for s in result.Sequences
    ]

    arrays = [
        {
            "Timestamp": fmt_dt(a.Timestamp),
            "StartLineNumber": a.StartLineNumber,
            "Name": a.Name,
            "Length": len(a.Values),
            "Values": a.Values,
        }
        for a in result.Arrays
    ]

    summary = (
        f"File: {result.FileName} | "
        f"Entries: {len(result.AllEntries)} | "
        f"Steps: {len(result.PipettingSteps)} | "
        f"Transfers: {len(result.LiquidTransfers)} | "
        f"LiquidLevels: {len(result.LiquidLevels)} | "
        f"Variables: {len(result.Variables)} | "
        f"SQL: {len(result.SqlStatements)} | "
        f"Sequences: {len(result.Sequences)} | "
        f"Arrays: {len(result.Arrays)}"
        + (f" | Errors: {len(result.Errors)}" if result.Errors else "")
    )

    return {
        "entries": entries,
        "steps": steps,
        "transfers": transfers,
        "liquid_levels": liquid_levels,
        "variables": variables,
        "sql_stmts": sql_stmts,
        "sequences": sequences,
        "arrays": arrays,
        "liquid_classes": result.LiquidClasses,
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

    content = f.read()
    # Try UTF-8 first, fall back to latin-1 for real Hamilton STAR files
    try:
        lines = content.decode("utf-8", errors="strict").splitlines()
    except UnicodeDecodeError:
        lines = content.decode("latin-1", errors="replace").splitlines()

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
