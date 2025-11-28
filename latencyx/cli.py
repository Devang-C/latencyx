import sys
import time
import json
from pathlib import Path
from datetime import datetime

class LatencyXTail:
    """Live tail viewer for LatencyX traces"""
    
    def __init__(self, file_path="latencyx_traces.jsonl", follow=True, format="table"):
        self.file_path = Path(file_path)
        self.follow = follow
        self.format = format
    
    def run(self):
        """Start tailing the file"""
        if not self.file_path.exists():
            print(f"❌ File not found: {self.file_path}")
            print(f"   Make sure 'json_file' exporter is enabled in your LatencyX config")
            return
        
        print(f"📊 Watching LatencyX traces from: {self.file_path}")
        print(f"   Press Ctrl+C to stop\n")
        
        # Print header
        if self.format == "table":
            self._print_table_header()
        
        try:
            with open(self.file_path, 'r') as f:
                # Skip to end if following
                if self.follow:
                    f.seek(0, 2)  # Seek to end
                
                while True:
                    line = f.readline()
                    
                    if line:
                        try:
                            data = json.loads(line.strip())
                            self._print_span(data)
                        except json.JSONDecodeError:
                            pass  # Skip malformed lines
                    else:
                        if not self.follow:
                            break
                        time.sleep(0.1)  # Wait for new data
        
        except KeyboardInterrupt:
            print("\n\n👋 Stopped watching")
    
    def _print_table_header(self):
        """Print the table header"""
        header_line = "─" * 130
        print(header_line)
        print(f"{'TYPE':<16} │ {'NAME':<38} │ {'DURATION':>11} │ {'STATUS':>8} │ {'DETAILS':<40}")
        print(header_line)
    
    def _print_span(self, data):
        """Print a single span"""
        if self.format == "table":
            self._print_table_row(data)
        else:
            self._print_compact_row(data)
    
    def _print_table_row(self, data):
        """Print table-formatted row with consistent alignment"""
        # Extract and format basic fields
        span_type = data.get('span_type', 'unknown')
        span_name = data.get('span_name', 'unknown')
        duration_ms = data.get('duration_ms', 0)
        
        # Format duration (no pre-alignment here)
        if duration_ms < 100:
            duration_str = f"{duration_ms:.2f}ms"
        elif duration_ms < 1000:
            duration_str = f"{duration_ms:.1f}ms"
        else:
            duration_str = f"{duration_ms/1000:.2f}s"
        
        # Get status - prioritize status_code, fall back to status field
        if 'status_code' in data:
            status_display = str(data['status_code'])
        else:
            status_display = data.get('status', 'unknown')
        
        # Color code by status
        status_color = ""
        reset = ""
        if data.get('error'):
            status_color = "\033[91m"  # Red
            reset = "\033[0m"
            status_display = "ERROR"
        elif isinstance(data.get('status_code'), int):
            if data['status_code'] >= 500:
                status_color = "\033[91m"  # Red
                reset = "\033[0m"
            elif data['status_code'] >= 400:
                status_color = "\033[93m"  # Yellow
                reset = "\033[0m"
        
        # Build details - only show relevant fields
        details = []
        
        # Common fields mapping (skip redundant info already in span_name)
        detail_fields = {
            'method': 'method',
            'path': 'path',
            'host': 'host',
            'client': 'client',
            'url': 'url',
            'rows': 'rows',
            'query': 'query',
        }
        
        for field, label in detail_fields.items():
            if field in data and data[field]:
                # Skip if already in span_name (avoid redundancy)
                if field == 'method' and data[field] in span_name:
                    continue
                if field == 'path' and data[field] in span_name:
                    continue
                details.append(f"{label}={data[field]}")
        
        # Add error details if present
        if data.get('error'):
            error_msg = str(data['error'])[:30]  # Truncate long errors
            details.append(f"error={error_msg}")
        
        # Join details with space
        details_str = " ".join(details) if details else ""
        
        # Truncate fields to fit columns (with visual indicator)
        if len(span_type) > 16:
            span_type = span_type[:15] + "…"
        if len(span_name) > 38:
            span_name = span_name[:37] + "…"
        if len(details_str) > 40:
            details_str = details_str[:39] + "…"
        
        # Print with consistent column alignment
        print(
            f"{span_type:<16} │ "
            f"{span_name:<38} │ "
            f"{duration_str:>11} │ "
            f"{status_color}{status_display:>8}{reset} │ "
            f"{details_str:<40}"
        )
    
    def _print_compact_row(self, data):
        """Print compact key-value row"""
        span_type = data.get('span_type', 'unknown')
        span_name = data.get('span_name', 'unknown')
        duration_ms = data.get('duration_ms', 0)
        
        # Format duration
        if duration_ms < 100:
            duration_str = f"{duration_ms:.2f}ms"
        elif duration_ms < 1000:
            duration_str = f"{duration_ms:.1f}ms"
        else:
            duration_str = f"{duration_ms/1000:.2f}s"
        
        parts = [
            f"[{span_type}]",
            span_name,
            f"duration={duration_str}"
        ]
        
        # Add relevant metadata
        if 'status_code' in data:
            parts.append(f"status={data['status_code']}")
        
        if 'method' in data and data['method'] not in span_name:
            parts.append(f"method={data['method']}")
        
        if 'host' in data:
            parts.append(f"host={data['host']}")
        
        if 'client' in data:
            parts.append(f"client={data['client']}")
        
        if data.get('error'):
            parts.append(f"ERROR={data['error']}")
        
        print(" ".join(parts))


def main():
    """CLI entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="LatencyX - Latency tracking and observability",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Tail subcommand
    tail_parser = subparsers.add_parser(
        'tail',
        help='Watch traces in real-time',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Watch in table format (default)
  latencyx tail
  
  # Watch in compact format
  latencyx tail --format compact
  
  # Watch a specific file
  latencyx tail --file /path/to/traces.jsonl
  
  # Show existing traces then exit
  latencyx tail --no-follow
        """
    )
    
    tail_parser.add_argument(
        '--file', '-f',
        default='latencyx_traces.jsonl',
        help='Path to traces file (default: latencyx_traces.jsonl)'
    )
    
    tail_parser.add_argument(
        '--format',
        choices=['table', 'compact'],
        default='table',
        help='Output format (default: table)'
    )
    
    tail_parser.add_argument(
        '--no-follow',
        action='store_true',
        help='Print existing traces and exit (like cat, not tail -f)'
    )
    
    args = parser.parse_args()
    
    # Handle commands
    if args.command == 'tail':
        tailer = LatencyXTail(
            file_path=args.file,
            follow=not args.no_follow,
            format=args.format
        )
        tailer.run()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()