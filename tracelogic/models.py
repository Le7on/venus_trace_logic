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
    """An aggregated pipetting step (Aspirate/Dispense/PickupTip/EjectTip/LiquidLevel)."""
    ActionType: PipettingActionType
    StartTime: Optional[datetime]
    EndTime: Optional[datetime]
    Duration: Optional[timedelta]
    ChannelActions: list[ChannelAction] = field(default_factory=list)
    StartLineNumber: int = 0
    LiquidClass: Optional[str] = None          # LC Utilized line preceding this step


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
    LiquidClass: Optional[str] = None          # LC used for this transfer


@dataclass
class LiquidLevelEvent:
    """Result of a 'Get Last Liquid Level' step — height per channel (mm)."""
    Timestamp: Optional[datetime]
    StartLineNumber: int
    ChannelLevels: dict[int, float] = field(default_factory=dict)  # {channel: mm}


@dataclass
class VariableEvent:
    """A USER Trace line recording a variable assignment or value."""
    Timestamp: Optional[datetime]
    LineNumber: int
    RawDetail: str
    Name: Optional[str] = None    # parsed variable name if detectable
    Value: Optional[str] = None   # parsed value if detectable


@dataclass
class SqlEvent:
    """A USER Trace line containing a SQL statement."""
    Timestamp: Optional[datetime]
    LineNumber: int
    Statement: str                 # full SQL text


@dataclass
class SequenceEvent:
    """A USER Trace line describing a sequence state (name/current/count/etc.)."""
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
    LiquidClasses: list[str] = field(default_factory=list)   # all LC names referenced
    Errors: list[str] = field(default_factory=list)
