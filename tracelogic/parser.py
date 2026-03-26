"""Hamilton Venus .trc log file parser."""

from __future__ import annotations
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from .enums import EntryStatus, PipettingActionType
from .models import (
    ArrayEvent,
    ChannelAction,
    LiquidLevelEvent,
    LiquidTransferEvent,
    PipettingStep,
    SequenceEvent,
    SqlEvent,
    TraceAnalysisResult,
    TraceEntry,
    VariableEvent,
)

# ---------------------------------------------------------------------------
# Compiled regular expressions
# ---------------------------------------------------------------------------

# Main log line
_RE_LINE = re.compile(
    r"^(?P<timestamp>[\d\- :]+)> (?P<source>.+?) : (?P<command>.+?) - (?P<status>\w+); ?(?P<details>.*)$"
)

# Channel action with volume:  > channel 1: VGM, A3, 384 uL
_RE_VOLUME_ACTION = re.compile(
    r"channel (?P<channel>\d+): (?P<labware>[^,]+), (?P<position>[^,]+), (?P<volume>[\d\.]+) uL"
)

# Channel action without volume:  > channel 1: HT_L_0001, 1  or  > channel 1: Waste,
_RE_TIP_ACTION = re.compile(
    r"channel (?P<channel>\d+): (?P<labware>[^,]+), (?P<position>[^,>]*)"
)

# Liquid level per channel:  > channel 1: 150.6 mm
_RE_LIQUID_LEVEL = re.compile(
    r"channel (?P<channel>\d+): (?P<level>[\d\.]+) mm"
)

# LC Utilized line:  LC Utilized>>>>>>>>>>>>>>>>>    SomeLiquidClass
_RE_LC_UTILIZED = re.compile(
    r"LC Utilized[>\s]+(?P<lc>\S+)"
)

# Variable assignment patterns
_RE_VAR_SET = re.compile(
    r"(?P<name>[\w]+)\s+(?:variable\s+)?is\s+set\s+to:\s*(?P<value>.+)", re.IGNORECASE
)
_RE_VAR_EQ = re.compile(
    r"(?P<name>[\w\s]+?)\s*=\s*(?P<value>.+)"
)

# Sequence property lines: "name = QNS_Controls", "current = 1", etc.
_RE_SEQ_PROP = re.compile(
    r"^(?P<key>name|current|count|total|max|used|labwareId|positionId)\s*=\s*(?P<value>[^,]+)$",
    re.IGNORECASE
)

# SQL detection: must contain SQL keyword as a statement start (not just in text)
_RE_SQL = re.compile(
    r"(?:^|:\s*)(?:Use\s+\w|Select\b|Insert\s+(?:Into\b|[\w\[])|\bUpdate\s+[\w\[`]|Delete\s+From\b|Exec(?:ute)?\s+\w)",
    re.IGNORECASE
)

# SQL label prefixes (strip these to get the raw SQL)
_RE_SQL_LABEL = re.compile(
    r"^(?:\|+\s*)?(?P<label>[\w\s\-]+?)\s*(?:SQL\s*\w*\s*)?:\s*(?P<sql>(?:Use|Select|Insert|Update|Delete|Exec)\b.+)$",
    re.IGNORECASE
)
_RE_SQL_FINAL = re.compile(
    r"^##\s*Final String\s*:\s*(?P<sql>.+)$", re.IGNORECASE
)

# SQL keywords to uppercase-normalize
_SQL_KEYWORDS = [
    "SELECT", "FROM", "WHERE", "AND", "OR", "NOT", "IN", "AS",
    "INSERT", "INTO", "VALUES", "UPDATE", "SET", "DELETE",
    "USE", "EXEC", "EXECUTE", "TOP", "DISTINCT", "ORDER", "BY",
    "ASC", "DESC", "GROUP", "HAVING", "JOIN", "LEFT", "RIGHT",
    "INNER", "OUTER", "ON", "COUNT", "SUM", "AVG", "MAX", "MIN",
    "FORMAT", "CAST", "CONVERT", "CASE", "WHEN", "THEN", "ELSE",
    "END", "NULL", "IS", "LIKE", "BETWEEN", "EXISTS", "WITH",
]
_SQL_KW_RE = re.compile(
    r'\b(' + '|'.join(_SQL_KEYWORDS) + r')\b', re.IGNORECASE
)


def _normalize_sql(sql: str) -> str:
    """Uppercase all SQL keywords while preserving string literals."""
    # Protect single-quoted strings
    parts = re.split(r"('(?:[^']|'')*')", sql)
    result = []
    for i, part in enumerate(parts):
        if i % 2 == 1:  # inside quotes — leave as-is
            result.append(part)
        else:
            result.append(_SQL_KW_RE.sub(lambda m: m.group().upper(), part))
    return "".join(result)


def _detect_sql_type(sql: str) -> str:
    """Detect SQL statement type from normalized SQL."""
    s = sql.strip().upper()
    # USE ... EXEC is really an EXEC
    if re.match(r'USE\s+\w+\s+EXEC\b', s):
        return "EXEC"
    for kw in ("SELECT", "INSERT", "UPDATE", "DELETE", "EXEC", "EXECUTE", "USE"):
        if re.match(rf'\s*(?:USE\s+\w+\s+)?{kw}\b', s):
            return kw.replace("EXECUTE", "EXEC")
    return "UNKNOWN"

# Extract database name from "Use DbName"
_RE_USE_DB = re.compile(r"\bUse\s+(\w+)", re.IGNORECASE)
# Extract table name from FROM/INTO/UPDATE/JOIN clauses
_RE_TABLE = re.compile(r"\b(?:From|Into|Update|Join)\s+([\w\.]+)", re.IGNORECASE)
# Extract stored procedure name from EXEC
_RE_PROC = re.compile(r"\bExec(?:ute)?\s+([\w\.]+)", re.IGNORECASE)


def _parse_sql_event(entry: "TraceEntry") -> Optional["SqlEvent"]:
    """Extract and enrich a SqlEvent from a USER Trace entry."""
    from .models import SqlEvent
    detail = entry.Details

    # Try label patterns first
    label = None
    sql_text = None

    m = _RE_SQL_FINAL.match(detail.strip())
    if m:
        label = "Final String"
        sql_text = m.group("sql").strip()
    else:
        m = _RE_SQL_LABEL.match(detail.strip())
        if m:
            label = m.group("label").strip()
            sql_text = m.group("sql").strip()
        elif _RE_SQL.search(detail):
            sql_text = detail.strip()

    if not sql_text:
        return None

    # Normalize keywords to uppercase
    sql_text = _normalize_sql(sql_text)

    # Detect SQL type
    sql_type = _detect_sql_type(sql_text)

    # Extract database
    db_m = _RE_USE_DB.search(sql_text)
    database = db_m.group(1) if db_m else None

    # Extract table or proc
    table_or_proc = None
    if sql_type == "EXEC":
        pm = _RE_PROC.search(sql_text)
        table_or_proc = pm.group(1) if pm else None
    else:
        tm = _RE_TABLE.search(sql_text)
        table_or_proc = tm.group(1) if tm else None

    # Detect truncation (no semicolon at end, statement looks incomplete)
    is_truncated = not sql_text.rstrip().endswith(";") and len(sql_text) > 150

    return SqlEvent(
        Timestamp=entry.Timestamp,
        LineNumber=entry.LineNumber,
        Statement=sql_text,
        SqlType=sql_type,
        Database=database,
        TableOrProc=table_or_proc,
        Label=label,
        IsTruncated=is_truncated,
    )

_TIMESTAMP_FMT = "%Y-%m-%d %H:%M:%S"

# Commands → PipettingActionType (longest-first substring match)
_PIPETTING_COMMANDS: dict[str, PipettingActionType] = {
    "1000ul channel aspirate (single step)":    PipettingActionType.Aspirate,
    "1000ul channel dispense (single step)":    PipettingActionType.Dispense,
    "1000ul channel tip pick up (single step)": PipettingActionType.PickupTip,
    "1000ul channel tip eject (single step)":   PipettingActionType.EjectTip,
    "1000ul channel get last liquid level (single step)": PipettingActionType.LiquidLevel,
    "co-re 96 head aspirate (single step)":     PipettingActionType.Aspirate,
    "co-re 96 head dispense (single step)":     PipettingActionType.Dispense,
    "co-re 96 head tip pick up (single step)":  PipettingActionType.PickupTip,
    "co-re 96 head tip eject (single step)":    PipettingActionType.EjectTip,
    "initialize (single step)":                 PipettingActionType.Initialize,
    "aspirate":    PipettingActionType.Aspirate,
    "dispense":    PipettingActionType.Dispense,
    "tip pick up": PipettingActionType.PickupTip,
    "pickuptip":   PipettingActionType.PickupTip,
    "tip eject":   PipettingActionType.EjectTip,
    "ejecttip":    PipettingActionType.EjectTip,
    "liquid level": PipettingActionType.LiquidLevel,
}

# Outer wrapper commands to skip (they contain no channel data themselves)
_WRAPPER_COMMANDS = {
    "1000ul channel aspirate",
    "1000ul channel dispense",
    "1000ul channel tip pick up",
    "1000ul channel tip eject",
    "1000ul channel get last liquid level",
    "co-re 96 head aspirate",
    "co-re 96 head dispense",
    "co-re 96 head tip pick up",
    "co-re 96 head tip eject",
}


def _parse_timestamp(raw: str) -> Optional[datetime]:
    try:
        return datetime.strptime(raw.strip(), _TIMESTAMP_FMT)
    except ValueError:
        return None


def _parse_status(raw: str) -> EntryStatus:
    mapping = {
        "start": EntryStatus.Start,
        "complete": EntryStatus.Complete,
        "progress": EntryStatus.Progress,
        "error": EntryStatus.Error,
    }
    return mapping.get(raw.strip().lower(), EntryStatus.Unknown)


def _detect_action_type(command: str) -> Optional[PipettingActionType]:
    key = command.strip().lower()
    if key in _PIPETTING_COMMANDS:
        return _PIPETTING_COMMANDS[key]
    for cmd_key in sorted(_PIPETTING_COMMANDS, key=len, reverse=True):
        if cmd_key in key:
            return _PIPETTING_COMMANDS[cmd_key]
    return None


def _is_wrapper_command(command: str) -> bool:
    """Return True for outer wrapper commands that have no channel data."""
    key = command.strip().lower()
    return key in _WRAPPER_COMMANDS


def _parse_channel_actions(details: str, with_volume: bool) -> list[ChannelAction]:
    actions: list[ChannelAction] = []
    regex = _RE_VOLUME_ACTION if with_volume else _RE_TIP_ACTION
    for m in regex.finditer(details):
        actions.append(ChannelAction(
            ChannelNumber=int(m.group("channel")),
            LabwareId=m.group("labware").strip(),
            PositionId=m.group("position").strip(),
            Volume=float(m.group("volume")) if with_volume else None,
        ))
    return actions


def _parse_liquid_levels(details: str) -> dict[int, float]:
    return {
        int(m.group("channel")): float(m.group("level"))
        for m in _RE_LIQUID_LEVEL.finditer(details)
    }


def _parse_variable(detail: str) -> tuple[Optional[str], Optional[str]]:
    """Try to extract (name, value) from a USER Trace detail string."""
    m = _RE_VAR_SET.search(detail)
    if m:
        return m.group("name").strip(), m.group("value").strip()
    m = _RE_VAR_EQ.search(detail)
    if m:
        name = m.group("name").strip()
        value = m.group("value").strip()
        # Filter out noise (long sentences are not variable assignments)
        if len(name) < 60 and "\n" not in name:
            return name, value
    return None, None


def _parse_sequence_props(detail: str) -> Optional[dict]:
    """Parse sequence property lines like 'name = QNS_Controls', 'current = 1'."""
    m = _RE_SEQ_PROP.match(detail.strip())
    if m:
        return {m.group("key").lower(): m.group("value").strip()}
    return None


class TraceFileParser:
    """Parser for Hamilton Venus .trc log files."""

    def parse(self, filepath: str | Path) -> TraceAnalysisResult:
        """Parse a .trc file and return a TraceAnalysisResult."""
        path = Path(filepath)
        result = TraceAnalysisResult(FileName=path.name)
        for enc in ("utf-8", "latin-1"):
            try:
                lines = path.read_text(encoding=enc, errors="replace").splitlines()
                break
            except OSError as exc:
                result.Errors.append(f"Cannot read file ({enc}): {exc}")
                return result

        result.AllEntries = self._parse_entries(lines, result.Errors)
        result.PipettingSteps, result.LiquidLevels = self._aggregate_steps(result.AllEntries)
        result.LiquidTransfers = self._build_transfers(result.PipettingSteps)
        result.Variables, result.SqlStatements, result.Sequences, result.Arrays = \
            self._parse_user_traces(result.AllEntries)
        result.LiquidClasses = self._collect_liquid_classes(result.AllEntries)
        return result

    def parse_lines(self, lines: list[str]) -> TraceAnalysisResult:
        """Parse in-memory lines (useful for testing)."""
        result = TraceAnalysisResult(FileName="<memory>")
        result.AllEntries = self._parse_entries(lines, result.Errors)
        result.PipettingSteps, result.LiquidLevels = self._aggregate_steps(result.AllEntries)
        result.LiquidTransfers = self._build_transfers(result.PipettingSteps)
        result.Variables, result.SqlStatements, result.Sequences, result.Arrays = \
            self._parse_user_traces(result.AllEntries)
        result.LiquidClasses = self._collect_liquid_classes(result.AllEntries)
        return result

    # ------------------------------------------------------------------
    # Step 1: parse raw lines → TraceEntry
    # ------------------------------------------------------------------

    def _parse_entries(self, lines: list[str], errors: list[str]) -> list[TraceEntry]:
        entries: list[TraceEntry] = []
        for lineno, raw in enumerate(lines, start=1):
            m = _RE_LINE.match(raw)
            if not m:
                continue
            entries.append(TraceEntry(
                LineNumber=lineno,
                Timestamp=_parse_timestamp(m.group("timestamp")),
                Source=m.group("source").strip(),
                Command=m.group("command").strip(),
                Status=_parse_status(m.group("status")),
                Details=m.group("details").strip(),
                RawLine=raw,
            ))
        return entries

    # ------------------------------------------------------------------
    # Step 2: aggregate → PipettingStep + LiquidLevelEvent
    # ------------------------------------------------------------------

    def _aggregate_steps(
        self, entries: list[TraceEntry]
    ) -> tuple[list[PipettingStep], list[LiquidLevelEvent]]:
        steps: list[PipettingStep] = []
        levels: list[LiquidLevelEvent] = []
        pending: dict[str, tuple[TraceEntry, PipettingActionType]] = {}
        last_lc: Optional[str] = None  # most recent LC Utilized

        for entry in entries:
            # Track LC Utilized lines
            lc_m = _RE_LC_UTILIZED.search(entry.Details)
            if lc_m and entry.Source == "USER":
                last_lc = lc_m.group("lc").strip()
                continue

            # Skip outer wrapper commands
            if _is_wrapper_command(entry.Command):
                continue

            action_type = _detect_action_type(entry.Command)
            if action_type is None:
                continue

            key = entry.Command.strip().lower()

            if entry.Status == EntryStatus.Start:
                pending[key] = (entry, action_type)

            elif entry.Status in (EntryStatus.Complete, EntryStatus.Error):
                start_entry, atype = pending.pop(key, (None, action_type))

                if atype == PipettingActionType.LiquidLevel:
                    levels.append(LiquidLevelEvent(
                        Timestamp=entry.Timestamp,
                        StartLineNumber=start_entry.LineNumber if start_entry else entry.LineNumber,
                        ChannelLevels=_parse_liquid_levels(entry.Details),
                    ))
                    continue

                with_volume = atype in (PipettingActionType.Aspirate, PipettingActionType.Dispense)
                channel_actions = _parse_channel_actions(entry.Details, with_volume)

                start_time = start_entry.Timestamp if start_entry else None
                end_time = entry.Timestamp
                duration = (end_time - start_time) if (start_time and end_time) else None

                step = PipettingStep(
                    ActionType=atype,
                    StartTime=start_time,
                    EndTime=end_time,
                    Duration=duration,
                    ChannelActions=channel_actions,
                    StartLineNumber=start_entry.LineNumber if start_entry else entry.LineNumber,
                    LiquidClass=last_lc if with_volume else None,
                )
                steps.append(step)

        return steps, levels

    # ------------------------------------------------------------------
    # Step 3: build LiquidTransferEvent (Aspirate→Dispense per channel)
    # ------------------------------------------------------------------

    def _build_transfers(self, steps: list[PipettingStep]) -> list[LiquidTransferEvent]:
        tip_labware: dict[int, str] = {}
        tip_position: dict[int, str] = {}
        asp_labware: dict[int, str] = {}
        asp_position: dict[int, str] = {}
        asp_volume: dict[int, float] = {}
        asp_time: dict[int, Optional[datetime]] = {}
        asp_lc: dict[int, Optional[str]] = {}
        transfers: list[LiquidTransferEvent] = []

        for step in steps:
            if step.ActionType == PipettingActionType.PickupTip:
                for ca in step.ChannelActions:
                    tip_labware[ca.ChannelNumber] = ca.LabwareId
                    tip_position[ca.ChannelNumber] = ca.PositionId

            elif step.ActionType == PipettingActionType.Aspirate:
                for ca in step.ChannelActions:
                    asp_labware[ca.ChannelNumber] = ca.LabwareId
                    asp_position[ca.ChannelNumber] = ca.PositionId
                    asp_volume[ca.ChannelNumber] = ca.Volume or 0.0
                    asp_time[ca.ChannelNumber] = step.EndTime
                    asp_lc[ca.ChannelNumber] = step.LiquidClass

            elif step.ActionType == PipettingActionType.Dispense:
                for ca in step.ChannelActions:
                    ch = ca.ChannelNumber
                    transfers.append(LiquidTransferEvent(
                        Timestamp=asp_time.get(ch),
                        ChannelId=ch,
                        SourceLabware=asp_labware.get(ch, ""),
                        SourcePositionId=asp_position.get(ch, ""),
                        TargetLabware=ca.LabwareId,
                        TargetPositionId=ca.PositionId,
                        Volume=asp_volume.get(ch),
                        TipLabwareId=tip_labware.get(ch, ""),
                        TipPositionId=tip_position.get(ch, ""),
                        LiquidClass=asp_lc.get(ch),
                    ))
                    asp_labware.pop(ch, None)
                    asp_position.pop(ch, None)
                    asp_volume.pop(ch, None)
                    asp_time.pop(ch, None)
                    asp_lc.pop(ch, None)

            elif step.ActionType == PipettingActionType.EjectTip:
                for ca in step.ChannelActions:
                    tip_labware.pop(ca.ChannelNumber, None)
                    tip_position.pop(ca.ChannelNumber, None)

        return transfers

    # ------------------------------------------------------------------
    # Step 4: parse USER Trace lines → Variables / SQL / Sequences
    # ------------------------------------------------------------------

    def _parse_user_traces(
        self, entries: list[TraceEntry]
    ) -> tuple[list[VariableEvent], list[SqlEvent], list[SequenceEvent], list[ArrayEvent]]:
        variables: list[VariableEvent] = []
        sql_stmts: list[SqlEvent] = []
        sequences: list[SequenceEvent] = []
        arrays: list[ArrayEvent] = []

        # Sequence accumulator
        seq_buf: dict = {}
        seq_ts: Optional[datetime] = None
        seq_lineno: int = 0

        # Array accumulator
        arr_buf: Optional[ArrayEvent] = None

        def flush_seq():
            if seq_buf:
                sequences.append(SequenceEvent(
                    Timestamp=seq_ts,
                    LineNumber=seq_lineno,
                    Name=seq_buf.get("name"),
                    Current=int(seq_buf["current"]) if "current" in seq_buf else None,
                    Count=int(seq_buf["count"]) if "count" in seq_buf else None,
                    Total=int(seq_buf["total"]) if "total" in seq_buf else None,
                    Max=int(seq_buf["max"]) if "max" in seq_buf else None,
                    Used=int(seq_buf["used"]) if "used" in seq_buf else None,
                    LabwareId=seq_buf.get("labwareid"),
                    PositionId=seq_buf.get("positionid"),
                    RawDetail=str(seq_buf),
                ))
                seq_buf.clear()

        def flush_arr():
            nonlocal arr_buf
            if arr_buf:
                # Build ordered Values list from RawItems
                if arr_buf.RawItems:
                    max_idx = max(arr_buf.RawItems.keys())
                    arr_buf.Values = [
                        arr_buf.RawItems.get(i, "") for i in range(max_idx + 1)
                    ]
                arrays.append(arr_buf)
                arr_buf = None

        # Regex for array index lines: "[1]: value"
        re_arr_idx = re.compile(r"^\[(?P<idx>\d+)\]:\s*(?P<val>.+)$")
        # Array command detection: command contains "TraceArray"
        def is_array_cmd(cmd: str) -> bool:
            return "TraceArray" in cmd or "tracearray" in cmd.lower()

        for entry in entries:
            detail = entry.Details

            # ---- Array block (DEBUG : *TraceArray*) ----
            if entry.Source == "DEBUG" and is_array_cmd(entry.Command):
                idx_m = re_arr_idx.match(detail.strip())

                if idx_m and arr_buf is not None:
                    # Indexed value line: [1]: value
                    arr_buf.RawItems[int(idx_m.group("idx"))] = idx_m.group("val").strip()
                elif not idx_m:
                    # Non-indexed line = header/description → start new array block
                    flush_arr()
                    arr_name = entry.Command.split("::")[-1].strip()  # e.g. TraceArray or TraceArray_2
                    arr_buf = ArrayEvent(
                        Timestamp=entry.Timestamp,
                        StartLineNumber=entry.LineNumber,
                        Name=f"{arr_name}: {detail.strip()[:80]}",
                    )
                continue

            flush_arr()

            if entry.Source not in ("USER", "TRACELEVEL"):
                flush_seq()
                continue

            # ---- SQL ----
            if _RE_SQL.search(detail):
                evt = _parse_sql_event(entry)
                if evt:
                    sql_stmts.append(evt)
                flush_seq()
                continue

            # ---- Sequence properties ----
            seq_props = _parse_sequence_props(detail)
            if seq_props:
                nonlocal_key = list(seq_props.keys())[0]
                if nonlocal_key == "name" and seq_buf:
                    flush_seq()
                seq_buf.update(seq_props)
                seq_ts = entry.Timestamp
                seq_lineno = entry.LineNumber
                continue
            else:
                flush_seq()

            # ---- Variable assignment ----
            name, value = _parse_variable(detail)
            if name and value:
                variables.append(VariableEvent(
                    Timestamp=entry.Timestamp,
                    LineNumber=entry.LineNumber,
                    RawDetail=detail,
                    Name=name,
                    Value=value,
                ))

        flush_seq()
        flush_arr()
        return variables, sql_stmts, sequences, arrays

    # ------------------------------------------------------------------
    # Step 5: collect all referenced liquid class names
    # ------------------------------------------------------------------

    def _collect_liquid_classes(self, entries: list[TraceEntry]) -> list[str]:
        seen: list[str] = []
        seen_set: set[str] = set()
        for entry in entries:
            # LC Utilized lines
            m = _RE_LC_UTILIZED.search(entry.Details)
            if m:
                lc = m.group("lc").strip()
                if lc not in seen_set:
                    seen.append(lc)
                    seen_set.add(lc)
            # End-of-method "Object referenced: Liquid class X"
            if "Object referenced: Liquid class" in entry.Details:
                lc = entry.Details.split("Liquid class", 1)[1].strip()
                if lc and lc not in seen_set:
                    seen.append(lc)
                    seen_set.add(lc)
        return seen
