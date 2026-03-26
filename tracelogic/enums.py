"""Enumerations for TraceLogic parser."""

from enum import Enum


class EntryStatus(Enum):
    """Status of a trace log entry, corresponding to C# EntryStatus enum."""
    Start = "Start"
    Complete = "Complete"
    Error = "Error"
    Unknown = "Unknown"


class PipettingActionType(Enum):
    """Type of pipetting action, corresponding to C# PipettingActionType enum."""
    Aspirate = "Aspirate"
    Dispense = "Dispense"
    PickupTip = "PickupTip"
    EjectTip = "EjectTip"
