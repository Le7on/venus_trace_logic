"""Enumerations for TraceLogic parser."""

from enum import Enum


class EntryStatus(Enum):
    """Status of a trace log entry."""
    Start    = "Start"
    Complete = "Complete"
    Progress = "Progress"
    Error    = "Error"
    Unknown  = "Unknown"


class PipettingActionType(Enum):
    """Type of pipetting action."""
    Aspirate     = "Aspirate"
    Dispense     = "Dispense"
    PickupTip    = "PickupTip"
    EjectTip     = "EjectTip"
    LiquidLevel  = "LiquidLevel"    # Get Last Liquid Level
    Initialize   = "Initialize"
    Unknown      = "Unknown"
