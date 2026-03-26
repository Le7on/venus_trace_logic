"""Data models for TraceLogic, corresponding to C# Models."""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from .enums import EntryStatus, PipettingActionType


@dataclass
class TraceEntry:
    """A single parsed line from a Hamilton Venus .trc log file.

    Corresponds to C# TraceEntry model.
    """
    LineNumber: int
    Timestamp: Optional[datetime]
    Source: str
    Command: str
    Status: EntryStatus
    Details: str
    RawLine: str


@dataclass
class ChannelAction:
    """A single channel's action within a pipetting step.

    Corresponds to C# ChannelAction model.
    """
    ChannelNumber: int
    LabwareId: str
    PositionId: str
    Volume: Optional[float] = None  # None for tip actions


@dataclass
class PipettingStep:
    """An aggregated pipetting step (Aspirate/Dispense/PickupTip/EjectTip).

    Corresponds to C# PipettingStep model.
    """
    ActionType: PipettingActionType
    StartTime: Optional[datetime]
    EndTime: Optional[datetime]
    Duration: Optional[timedelta]
    ChannelActions: list[ChannelAction] = field(default_factory=list)
    StartLineNumber: int = 0


@dataclass
class LiquidTransferEvent:
    """A complete liquid transfer event pairing aspirate and dispense.

    Corresponds to C# LiquidTransferEvent model.
    """
    Timestamp: Optional[datetime]
    ChannelId: int
    SourceLabware: str
    SourcePositionId: str
    TargetLabware: str
    TargetPositionId: str
    Volume: Optional[float]
    TipLabwareId: str
    TipPositionId: str


@dataclass
class TraceAnalysisResult:
    """Complete result of parsing and analysing a .trc file.

    Corresponds to C# TraceAnalysisResult model.
    """
    FileName: str
    AllEntries: list[TraceEntry] = field(default_factory=list)
    PipettingSteps: list[PipettingStep] = field(default_factory=list)
    LiquidTransfers: list[LiquidTransferEvent] = field(default_factory=list)
    Errors: list[str] = field(default_factory=list)
