"""Data models for TraceLogic, corresponding to C# Models."""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from .enums import EntryStatus, PipettingActionType


@dataclass
class TraceEntry:
    """A single parsed line from a Hamilton Venus .trc log file."""
    LineNumber: int
    Timestamp: Optional[datetime]
    Source: str
    Command: str
    Status: EntryStatus
    Details: str
    RawLine: str


@dataclass
class ChannelAction:
    """A single channel's action within a pipetting step."""
    ChannelNumber: int
    LabwareId: str
    PositionId: str
    Volume: Optional[float] = None


@dataclass
class PipettingStep:
    """An aggregated pipetting step."""
    ActionType: PipettingActionType
    StartTime: Optional[datetime]
    EndTime: Optional[datetime]
    Duration: Optional[timedelta]
    ChannelActions: list[ChannelAction] = field(default_factory=list)
    StartLineNumber: int = 0
    LiquidClass: Optional[str] = None


@dataclass
class LiquidTransferEvent:
    """A complete liquid transfer event pairing aspirate and dispense."""
    Timestamp: Optional[datetime]
    ChannelId: int
    SourceLabware: str
    SourcePositionId: str
    TargetLabware: str
    TargetPositionId: str
    Volume: Optional[float]
    TipLabwareId: str
    TipPositionId: str
    LiquidClass: Optional[str] = None


@dataclass
class LiquidLevelEvent:
    """Result of a 'Get Last Liquid Level' step — height per channel (mm)."""
    Timestamp: Optional[datetime]
    StartLineNumber: int
    ChannelLevels: dict[int, float] = field(default_factory=dict)


@dataclass
class VariableEvent:
    """A USER Trace line recording a variable assignment or value."""
    Timestamp: Optional[datetime]
    LineNumber: int
    RawDetail: str
    Name: Optional[str] = None
    Value: Optional[str] = None


@dataclass
class SqlEvent:
    """A USER Trace line containing a SQL statement."""
    Timestamp: Optional[datetime]
    LineNumber: int
    Statement: str                  # full SQL text (may be truncated by .trc line limit)
    SqlType: str = ""               # SELECT / INSERT / UPDATE / DELETE / EXEC / USE / UNKNOWN
    Database: Optional[str] = None  # extracted from "Use DbName"
    TableOrProc: Optional[str] = None  # main table or stored procedure name
    Label: Optional[str] = None     # label prefix e.g. "Initial SQL Query", "SQL_ActiveUser"
    IsTruncated: bool = False       # True if line ends mid-statement (no semicolon)


@dataclass
class SequenceEvent:
    """A USER Trace line describing a sequence state."""
    Timestamp: Optional[datetime]
    LineNumber: int
    Name: Optional[str] = None
    Current: Optional[int] = None
    Count: Optional[int] = None
    Total: Optional[int] = None
    Max: Optional[int] = None
    Used: Optional[int] = None
    LabwareId: Optional[str] = None
    PositionId: Optional[str] = None
    RawDetail: str = ""


@dataclass
class ArrayEvent:
    """A DEBUG TraceArray block — named array with indexed values.

    Example .trc block::

        2026-01-01 09:00:00> DEBUG : TraceArray - complete; name = myArray
        2026-01-01 09:00:00> DEBUG : TraceArray - complete; 0 = 100
        2026-01-01 09:00:00> DEBUG : TraceArray - complete; 1 = 200
    """
    Timestamp: Optional[datetime]
    StartLineNumber: int
    Name: str
    Values: list[str] = field(default_factory=list)   # index-ordered values
    RawItems: dict[int, str] = field(default_factory=dict)  # {index: value}


@dataclass
class ErrorEvent:
    """An error or warning entry with surrounding context lines."""
    Timestamp: Optional[datetime]
    LineNumber: int
    Source: str
    Command: str
    Severity: str           # "ERROR" or "WARNING"
    Message: str            # error/warning message text
    ContextBefore: list[str] = field(default_factory=list)  # up to 3 lines before
    ContextAfter: list[str] = field(default_factory=list)   # up to 3 lines after


@dataclass
class TraceAnalysisResult:
    """Complete result of parsing and analysing a .trc file."""
    FileName: str
    AllEntries: list[TraceEntry] = field(default_factory=list)
    PipettingSteps: list[PipettingStep] = field(default_factory=list)
    LiquidTransfers: list[LiquidTransferEvent] = field(default_factory=list)
    LiquidLevels: list[LiquidLevelEvent] = field(default_factory=list)
    Variables: list[VariableEvent] = field(default_factory=list)
    SqlStatements: list[SqlEvent] = field(default_factory=list)
    Sequences: list[SequenceEvent] = field(default_factory=list)
    Arrays: list[ArrayEvent] = field(default_factory=list)
    LiquidClasses: list[str] = field(default_factory=list)
    ErrorEvents: list["ErrorEvent"] = field(default_factory=list)
    Errors: list[str] = field(default_factory=list)
