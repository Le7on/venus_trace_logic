"""Hamilton Venus .trc log file parser."""

from __future__ import annotations
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from .enums import EntryStatus, PipettingActionType
from .models import (
    ChannelAction,
    LiquidTransferEvent,
    PipettingStep,
    TraceAnalysisResult,
    TraceEntry,
)

# ---------------------------------------------------------------------------
# Compiled regular expressions (identical to C# originals)
# ---------------------------------------------------------------------------

# Main log line pattern
_RE_LINE = re.compile(
    r"^(?P<timestamp>[\d\- :]+)> (?P<source>.+?) : (?P<command>.+?) - (?P<status>\w+); ?(?P<details>.*)$"
)

# Channel action with volume (Aspirate / Dispense)
_RE_VOLUME_ACTION = re.compile(
    r"channel (?P<channel>\d+): (?P<labware>[^,]+), (?P<position>[^,]+), (?P<volume>[\d\.]+) uL"
)

# Channel action without volume (PickupTip / EjectTip)
_RE_TIP_ACTION = re.compile(
    r"channel (?P<channel>\d+): (?P<labware>[^,]+), (?P<position>[^,>]+)"
)

_TIMESTAMP_FMT = "%Y-%m-%d %H:%M:%S"

# Commands that map to pipetting action types
_PIPETTING_COMMANDS: dict[str, PipettingActionType] = {
    "aspirate": PipettingActionType.Aspirate,
    "dispense": PipettingActionType.Dispense,
    "pickuptip": PipettingActionType.PickupTip,
    "tip pick up": PipettingActionType.PickupTip,
    "ejecttip": PipettingActionType.EjectTip,
    "tip eject": PipettingActionType.EjectTip,
}


def _parse_timestamp(raw: str) -> Optional[datetime]:
    """Parse a timestamp string from a .trc line."""
    try:
        return datetime.strptime(raw.strip(), _TIMESTAMP_FMT)
    except ValueError:
        return None


def _parse_status(raw: str) -> EntryStatus:
    """Map a raw status string to EntryStatus enum."""
    try:
        return EntryStatus(raw.strip().capitalize())
    except ValueError:
        return EntryStatus.Unknown


def _detect_action_type(command: str) -> Optional[PipettingActionType]:
    """Return the PipettingActionType for a command string, or None."""
    key = command.strip().lower()
    return _PIPETTING_COMMANDS.get(key)


def _parse_channel_actions(details: str, with_volume: bool) -> list[ChannelAction]:
    """Extract ChannelAction objects from a details string."""
    actions: list[ChannelAction] = []
    if with_volume:
        for m in _RE_VOLUME_ACTION.finditer(details):
            actions.append(
                ChannelAction(
                    ChannelNumber=int(m.group("channel")),
                    LabwareId=m.group("labware").strip(),
                    PositionId=m.group("position").strip(),
                    Volume=float(m.group("volume")),
                )
            )
    else:
        for m in _RE_TIP_ACTION.finditer(details):
            actions.append(
                ChannelAction(
                    ChannelNumber=int(m.group("channel")),
                    LabwareId=m.group("labware").strip(),
                    PositionId=m.group("position").strip(),
                )
            )
    return actions


class TraceFileParser:
    """Parser for Hamilton Venus .trc log files.

    Corresponds to C# TraceFileParser class.

    Usage::

        parser = TraceFileParser()
        result = parser.parse("run.trc")
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse(self, filepath: str | Path) -> TraceAnalysisResult:
        """Parse a .trc file and return a TraceAnalysisResult.

        Args:
            filepath: Path to the .trc log file.

        Returns:
            TraceAnalysisResult containing entries, steps, transfers, and errors.
        """
        path = Path(filepath)
        result = TraceAnalysisResult(FileName=path.name)

        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as exc:
            result.Errors.append(f"Cannot read file: {exc}")
            return result

        result.AllEntries = self._parse_entries(lines, result.Errors)
        result.PipettingSteps = self._aggregate_steps(result.AllEntries)
        result.LiquidTransfers = self._build_transfers(result.PipettingSteps)
        return result

    def parse_lines(self, lines: list[str]) -> TraceAnalysisResult:
        """Parse an in-memory list of log lines (useful for testing).

        Args:
            lines: Raw text lines from a .trc file.

        Returns:
            TraceAnalysisResult.
        """
        result = TraceAnalysisResult(FileName="<memory>")
        result.AllEntries = self._parse_entries(lines, result.Errors)
        result.PipettingSteps = self._aggregate_steps(result.AllEntries)
        result.LiquidTransfers = self._build_transfers(result.PipettingSteps)
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_entries(self, lines: list[str], errors: list[str]) -> list[TraceEntry]:
        """Parse raw lines into TraceEntry objects."""
        entries: list[TraceEntry] = []
        for lineno, raw in enumerate(lines, start=1):
            m = _RE_LINE.match(raw)
            if not m:
                # Non-matching lines are silently skipped (continuation lines, etc.)
                continue
            entry = TraceEntry(
                LineNumber=lineno,
                Timestamp=_parse_timestamp(m.group("timestamp")),
                Source=m.group("source").strip(),
                Command=m.group("command").strip(),
                Status=_parse_status(m.group("status")),
                Details=m.group("details").strip(),
                RawLine=raw,
            )
            entries.append(entry)
        return entries

    def _aggregate_steps(self, entries: list[TraceEntry]) -> list[PipettingStep]:
        """Aggregate TraceEntry pairs (Start/Complete) into PipettingStep objects."""
        steps: list[PipettingStep] = []
        # pending[command_lower] = (start_entry, action_type)
        pending: dict[str, tuple[TraceEntry, PipettingActionType]] = {}

        for entry in entries:
            action_type = _detect_action_type(entry.Command)
            if action_type is None:
                continue

            key = entry.Command.strip().lower()

            if entry.Status == EntryStatus.Start:
                pending[key] = (entry, action_type)

            elif entry.Status in (EntryStatus.Complete, EntryStatus.Error):
                start_entry, atype = pending.pop(key, (None, action_type))

                # Determine channel actions from the Complete/Error entry details
                with_volume = atype in (
                    PipettingActionType.Aspirate,
                    PipettingActionType.Dispense,
                )
                channel_actions = _parse_channel_actions(entry.Details, with_volume)

                start_time = start_entry.Timestamp if start_entry else None
                end_time = entry.Timestamp
                duration = (
                    (end_time - start_time)
                    if (start_time and end_time)
                    else None
                )

                step = PipettingStep(
                    ActionType=atype,
                    StartTime=start_time,
                    EndTime=end_time,
                    Duration=duration,
                    ChannelActions=channel_actions,
                    StartLineNumber=(
                        start_entry.LineNumber if start_entry else entry.LineNumber
                    ),
                )
                steps.append(step)

        return steps

    def _build_transfers(
        self, steps: list[PipettingStep]
    ) -> list[LiquidTransferEvent]:
        """Build LiquidTransferEvent list by pairing Aspirate→Dispense per channel.

        State machine per channel:
          PickupTip  → record tip info
          Aspirate   → record source info
          Dispense   → emit LiquidTransferEvent
          EjectTip   → clear tip info
        """
        # Per-channel state
        tip_labware: dict[int, str] = {}
        tip_position: dict[int, str] = {}
        aspirate_labware: dict[int, str] = {}
        aspirate_position: dict[int, str] = {}
        aspirate_volume: dict[int, float] = {}
        aspirate_time: dict[int, Optional[datetime]] = {}

        transfers: list[LiquidTransferEvent] = []

        for step in steps:
            if step.ActionType == PipettingActionType.PickupTip:
                for ca in step.ChannelActions:
                    tip_labware[ca.ChannelNumber] = ca.LabwareId
                    tip_position[ca.ChannelNumber] = ca.PositionId

            elif step.ActionType == PipettingActionType.Aspirate:
                for ca in step.ChannelActions:
                    aspirate_labware[ca.ChannelNumber] = ca.LabwareId
                    aspirate_position[ca.ChannelNumber] = ca.PositionId
                    aspirate_volume[ca.ChannelNumber] = ca.Volume or 0.0
                    aspirate_time[ca.ChannelNumber] = step.EndTime

            elif step.ActionType == PipettingActionType.Dispense:
                for ca in step.ChannelActions:
                    ch = ca.ChannelNumber
                    event = LiquidTransferEvent(
                        Timestamp=aspirate_time.get(ch),
                        ChannelId=ch,
                        SourceLabware=aspirate_labware.get(ch, ""),
                        SourcePositionId=aspirate_position.get(ch, ""),
                        TargetLabware=ca.LabwareId,
                        TargetPositionId=ca.PositionId,
                        Volume=aspirate_volume.get(ch),
                        TipLabwareId=tip_labware.get(ch, ""),
                        TipPositionId=tip_position.get(ch, ""),
                    )
                    transfers.append(event)
                    # Clear aspirate state after dispense
                    aspirate_labware.pop(ch, None)
                    aspirate_position.pop(ch, None)
                    aspirate_volume.pop(ch, None)
                    aspirate_time.pop(ch, None)

            elif step.ActionType == PipettingActionType.EjectTip:
                for ca in step.ChannelActions:
                    tip_labware.pop(ca.ChannelNumber, None)
                    tip_position.pop(ca.ChannelNumber, None)

        return transfers
