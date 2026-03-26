"""CSV exporter for LiquidTransferEvent data."""

from __future__ import annotations
import csv
from pathlib import Path
from typing import Optional

from .models import LiquidTransferEvent

# Default column order matching C# DataExporter
DEFAULT_COLUMNS = [
    "Timestamp",
    "ChannelId",
    "SourceLabware",
    "SourcePositionId",
    "TargetLabware",
    "TargetPositionId",
    "Volume",
    "TipLabwareId",
    "TipPositionId",
]


class DataExporter:
    """Exports analysis results to various formats.

    Corresponds to C# DataExporter class.
    """

    @staticmethod
    def export_to_csv(
        transfers: list[LiquidTransferEvent],
        columns: Optional[list[str]],
        filepath: str | Path,
    ) -> None:
        """Export a list of LiquidTransferEvent objects to a CSV file.

        Args:
            transfers: List of LiquidTransferEvent instances to export.
            columns: Column names to include (in order). Defaults to DEFAULT_COLUMNS.
            filepath: Destination CSV file path.
        """
        cols = columns if columns else DEFAULT_COLUMNS
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)

        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            writer.writeheader()
            for t in transfers:
                row: dict[str, object] = {
                    "Timestamp": t.Timestamp.isoformat() if t.Timestamp else "",
                    "ChannelId": t.ChannelId,
                    "SourceLabware": t.SourceLabware,
                    "SourcePositionId": t.SourcePositionId,
                    "TargetLabware": t.TargetLabware,
                    "TargetPositionId": t.TargetPositionId,
                    "Volume": t.Volume if t.Volume is not None else "",
                    "TipLabwareId": t.TipLabwareId,
                    "TipPositionId": t.TipPositionId,
                }
                writer.writerow({k: row[k] for k in cols if k in row})
