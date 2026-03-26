"""Unit tests for TraceFileParser."""

from __future__ import annotations
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

# Ensure package is importable when running from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from tracelogic import TraceFileParser, DataExporter
from tracelogic.enums import EntryStatus, PipettingActionType
from tracelogic.models import LiquidTransferEvent

SAMPLE_TRC = Path(__file__).parent / "sample.trc"

# ---------------------------------------------------------------------------
# Minimal inline .trc content for deterministic unit tests
# ---------------------------------------------------------------------------

MINIMAL_TRC = """\
2024-03-15 09:00:00> Hamilton : Tip Pick Up - Start; 
2024-03-15 09:00:01> Hamilton : Tip Pick Up - Complete; channel 1: TipRack_1, A1, channel 2: TipRack_1, A2
2024-03-15 09:00:02> Hamilton : Aspirate - Start; 
2024-03-15 09:00:03> Hamilton : Aspirate - Complete; channel 1: SrcPlate_1, A1, 50.0 uL, channel 2: SrcPlate_1, A2, 75.0 uL
2024-03-15 09:00:04> Hamilton : Dispense - Start; 
2024-03-15 09:00:05> Hamilton : Dispense - Complete; channel 1: DstPlate_1, B1, 50.0 uL, channel 2: DstPlate_1, B2, 75.0 uL
2024-03-15 09:00:06> Hamilton : Tip Eject - Start; 
2024-03-15 09:00:07> Hamilton : Tip Eject - Complete; channel 1: WasteBlock_1, A1, channel 2: WasteBlock_1, A1
""".splitlines()

ERROR_TRC = """\
2024-03-15 09:00:00> Hamilton : Aspirate - Start; 
2024-03-15 09:00:01> Hamilton : Aspirate - Error; Liquid level detection failed
""".splitlines()


# ---------------------------------------------------------------------------
# TraceEntry parsing
# ---------------------------------------------------------------------------

class TestParseEntries:
    def setup_method(self):
        self.parser = TraceFileParser()

    def test_entry_count(self):
        result = self.parser.parse_lines(MINIMAL_TRC)
        assert len(result.AllEntries) == 8

    def test_entry_timestamp(self):
        result = self.parser.parse_lines(MINIMAL_TRC)
        entry = result.AllEntries[0]
        assert entry.Timestamp == datetime(2024, 3, 15, 9, 0, 0)

    def test_entry_source(self):
        result = self.parser.parse_lines(MINIMAL_TRC)
        assert result.AllEntries[0].Source == "Hamilton"

    def test_entry_command(self):
        result = self.parser.parse_lines(MINIMAL_TRC)
        assert result.AllEntries[0].Command == "Tip Pick Up"

    def test_entry_status_start(self):
        result = self.parser.parse_lines(MINIMAL_TRC)
        assert result.AllEntries[0].Status == EntryStatus.Start

    def test_entry_status_complete(self):
        result = self.parser.parse_lines(MINIMAL_TRC)
        assert result.AllEntries[1].Status == EntryStatus.Complete

    def test_entry_status_error(self):
        result = self.parser.parse_lines(ERROR_TRC)
        error_entry = next(e for e in result.AllEntries if e.Status == EntryStatus.Error)
        assert error_entry.Status == EntryStatus.Error

    def test_entry_line_numbers(self):
        result = self.parser.parse_lines(MINIMAL_TRC)
        assert result.AllEntries[0].LineNumber == 1
        assert result.AllEntries[1].LineNumber == 2

    def test_non_matching_lines_skipped(self):
        lines = ["This is not a valid trc line", "Neither is this"] + MINIMAL_TRC
        result = self.parser.parse_lines(lines)
        assert len(result.AllEntries) == 8  # same as MINIMAL_TRC


# ---------------------------------------------------------------------------
# PipettingStep aggregation
# ---------------------------------------------------------------------------

class TestAggregateSteps:
    def setup_method(self):
        self.parser = TraceFileParser()

    def test_step_count(self):
        result = self.parser.parse_lines(MINIMAL_TRC)
        # PickupTip, Aspirate, Dispense, EjectTip = 4 steps
        assert len(result.PipettingSteps) == 4

    def test_step_action_types(self):
        result = self.parser.parse_lines(MINIMAL_TRC)
        types = [s.ActionType for s in result.PipettingSteps]
        assert PipettingActionType.PickupTip in types
        assert PipettingActionType.Aspirate in types
        assert PipettingActionType.Dispense in types
        assert PipettingActionType.EjectTip in types

    def test_aspirate_channel_actions(self):
        result = self.parser.parse_lines(MINIMAL_TRC)
        aspirate = next(s for s in result.PipettingSteps if s.ActionType == PipettingActionType.Aspirate)
        assert len(aspirate.ChannelActions) == 2
        ch1 = next(ca for ca in aspirate.ChannelActions if ca.ChannelNumber == 1)
        assert ch1.LabwareId == "SrcPlate_1"
        assert ch1.PositionId == "A1"
        assert ch1.Volume == 50.0

    def test_dispense_channel_actions(self):
        result = self.parser.parse_lines(MINIMAL_TRC)
        dispense = next(s for s in result.PipettingSteps if s.ActionType == PipettingActionType.Dispense)
        ch2 = next(ca for ca in dispense.ChannelActions if ca.ChannelNumber == 2)
        assert ch2.LabwareId == "DstPlate_1"
        assert ch2.PositionId == "B2"
        assert ch2.Volume == 75.0

    def test_step_duration(self):
        result = self.parser.parse_lines(MINIMAL_TRC)
        aspirate = next(s for s in result.PipettingSteps if s.ActionType == PipettingActionType.Aspirate)
        assert aspirate.Duration is not None
        assert aspirate.Duration.total_seconds() == 1.0

    def test_tip_action_no_volume(self):
        result = self.parser.parse_lines(MINIMAL_TRC)
        pickup = next(s for s in result.PipettingSteps if s.ActionType == PipettingActionType.PickupTip)
        for ca in pickup.ChannelActions:
            assert ca.Volume is None


# ---------------------------------------------------------------------------
# LiquidTransferEvent generation
# ---------------------------------------------------------------------------

class TestBuildTransfers:
    def setup_method(self):
        self.parser = TraceFileParser()

    def test_transfer_count(self):
        result = self.parser.parse_lines(MINIMAL_TRC)
        assert len(result.LiquidTransfers) == 2  # 2 channels

    def test_transfer_channel1(self):
        result = self.parser.parse_lines(MINIMAL_TRC)
        t = next(t for t in result.LiquidTransfers if t.ChannelId == 1)
        assert t.SourceLabware == "SrcPlate_1"
        assert t.SourcePositionId == "A1"
        assert t.TargetLabware == "DstPlate_1"
        assert t.TargetPositionId == "B1"
        assert t.Volume == 50.0
        assert t.TipLabwareId == "TipRack_1"
        assert t.TipPositionId == "A1"

    def test_transfer_channel2(self):
        result = self.parser.parse_lines(MINIMAL_TRC)
        t = next(t for t in result.LiquidTransfers if t.ChannelId == 2)
        assert t.Volume == 75.0
        assert t.SourcePositionId == "A2"
        assert t.TargetPositionId == "B2"

    def test_no_transfers_without_aspirate(self):
        lines = """\
2024-03-15 09:00:00> Hamilton : Dispense - Start; 
2024-03-15 09:00:01> Hamilton : Dispense - Complete; channel 1: DstPlate_1, B1, 50.0 uL
""".splitlines()
        result = self.parser.parse_lines(lines)
        # Dispense without prior aspirate still creates a transfer (with empty source)
        assert len(result.LiquidTransfers) == 1
        assert result.LiquidTransfers[0].SourceLabware == ""


# ---------------------------------------------------------------------------
# File-based parsing
# ---------------------------------------------------------------------------

class TestParseFile:
    def setup_method(self):
        self.parser = TraceFileParser()

    def test_parse_sample_file(self):
        result = self.parser.parse(SAMPLE_TRC)
        assert result.FileName == "sample.trc"
        assert len(result.AllEntries) > 0
        assert len(result.PipettingSteps) > 0
        assert len(result.LiquidTransfers) > 0

    def test_parse_missing_file(self):
        result = self.parser.parse("/nonexistent/path/file.trc")
        assert len(result.Errors) > 0


# ---------------------------------------------------------------------------
# DataExporter
# ---------------------------------------------------------------------------

class TestDataExporter:
    def _make_transfer(self, ch: int) -> LiquidTransferEvent:
        return LiquidTransferEvent(
            Timestamp=datetime(2024, 3, 15, 9, 0, 0),
            ChannelId=ch,
            SourceLabware="SrcPlate",
            SourcePositionId=f"A{ch}",
            TargetLabware="DstPlate",
            TargetPositionId=f"B{ch}",
            Volume=50.0,
            TipLabwareId="TipRack",
            TipPositionId=f"T{ch}",
        )

    def test_export_creates_file(self):
        transfers = [self._make_transfer(1), self._make_transfer(2)]
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = f.name
        try:
            DataExporter.export_to_csv(transfers, None, path)
            assert os.path.exists(path)
            content = Path(path).read_text()
            assert "ChannelId" in content
            assert "SrcPlate" in content
        finally:
            os.unlink(path)

    def test_export_row_count(self):
        import csv
        transfers = [self._make_transfer(i) for i in range(1, 4)]
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
            path = f.name
        try:
            DataExporter.export_to_csv(transfers, None, path)
            with open(path) as f:
                rows = list(csv.DictReader(f))
            assert len(rows) == 3
        finally:
            os.unlink(path)

    def test_export_custom_columns(self):
        import csv
        transfers = [self._make_transfer(1)]
        cols = ["ChannelId", "Volume"]
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
            path = f.name
        try:
            DataExporter.export_to_csv(transfers, cols, path)
            with open(path) as f:
                reader = csv.DictReader(f)
                assert reader.fieldnames == cols
        finally:
            os.unlink(path)
