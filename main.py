"""CLI entry point for TraceLogic .trc parser."""

from __future__ import annotations
import argparse
import sys
from pathlib import Path

from tracelogic import TraceFileParser, DataExporter
from tracelogic.models import TraceAnalysisResult


def print_summary(result: TraceAnalysisResult) -> None:
    """Print a concise summary of the analysis result."""
    print(f"File       : {result.FileName}")
    print(f"Entries    : {len(result.AllEntries)}")
    print(f"Steps      : {len(result.PipettingSteps)}")
    print(f"Transfers  : {len(result.LiquidTransfers)}")
    if result.Errors:
        print(f"Errors     : {len(result.Errors)}")
        for e in result.Errors:
            print(f"  ! {e}")


def print_entries(result: TraceAnalysisResult) -> None:
    """Print all TraceEntry objects."""
    print(f"\n{'#':>5}  {'Timestamp':<20}  {'Source':<20}  {'Command':<20}  {'Status':<10}  Details")
    print("-" * 100)
    for e in result.AllEntries:
        ts = e.Timestamp.strftime("%Y-%m-%d %H:%M:%S") if e.Timestamp else "N/A"
        print(f"{e.LineNumber:>5}  {ts:<20}  {e.Source:<20}  {e.Command:<20}  {e.Status.value:<10}  {e.Details[:60]}")


def print_steps(result: TraceAnalysisResult) -> None:
    """Print all PipettingStep objects."""
    print(f"\n{'#':>4}  {'Action':<12}  {'Start':<20}  {'End':<20}  {'Duration':>10}  Channels")
    print("-" * 100)
    for i, s in enumerate(result.PipettingSteps, 1):
        start = s.StartTime.strftime("%Y-%m-%d %H:%M:%S") if s.StartTime else "N/A"
        end = s.EndTime.strftime("%Y-%m-%d %H:%M:%S") if s.EndTime else "N/A"
        dur = str(s.Duration) if s.Duration else "N/A"
        channels = ", ".join(str(ca.ChannelNumber) for ca in s.ChannelActions)
        print(f"{i:>4}  {s.ActionType.value:<12}  {start:<20}  {end:<20}  {dur:>10}  [{channels}]")


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Parse Hamilton Venus .trc log files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py run.trc
  python main.py run.trc --export transfers.csv
  python main.py run.trc --show-entries
  python main.py run.trc --show-steps
""",
    )
    parser.add_argument("file", help="Path to the .trc log file")
    parser.add_argument("--export", metavar="OUTPUT.CSV", help="Export transfers to CSV")
    parser.add_argument("--show-entries", action="store_true", help="Print all TraceEntry rows")
    parser.add_argument("--show-steps", action="store_true", help="Print all PipettingStep rows")

    args = parser.parse_args()

    trc_path = Path(args.file)
    if not trc_path.exists():
        print(f"Error: file not found: {trc_path}", file=sys.stderr)
        sys.exit(1)

    trace_parser = TraceFileParser()
    result = trace_parser.parse(trc_path)

    print_summary(result)

    if args.show_entries:
        print_entries(result)

    if args.show_steps:
        print_steps(result)

    if args.export:
        DataExporter.export_to_csv(result.LiquidTransfers, None, args.export)
        print(f"\nExported {len(result.LiquidTransfers)} transfer(s) → {args.export}")


if __name__ == "__main__":
    main()
