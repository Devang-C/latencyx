# latencyx/exporters/console.py
import logging
from ..config import config, TimeUnit

logger = logging.getLogger("latencyx")

class ConsoleExporter:
    """Export spans to console/logs"""
    
    def export(self, span):
        # Format duration with color
        duration_str = self._format_duration(span.duration_ms)
        
        # Build the main line
        parts = [
            f"[{span.span_type}]",
            span.name,
            f"duration={duration_str}"
        ]
        
        # Add key metadata as key=value pairs
        if span.metadata:
            # Priority order for common fields
            priority_fields = ['status_code', 'method', 'client', 'host']
            
            # Add priority fields first
            for field in priority_fields:
                if field in span.metadata:
                    value = span.metadata[field]
                    # Shorten field names for readability
                    display_name = 'status' if field == 'status_code' else field
                    parts.append(f"{display_name}={value}")
            
            # Add remaining fields
            for key, value in span.metadata.items():
                if key not in priority_fields:
                    parts.append(f"{key}={value}")
        
        # Add error at the end with visual indicator
        if span.error:
            parts.append(f"ERROR={span.error}")
        
        # Join with consistent spacing
        message = " ".join(parts)
        
        # Use different log levels for errors vs success
        if span.error:
            logger.error(message)
        else:
            logger.info(message)
    
    def _format_duration(self, duration_ms: float) -> str:
        """Format duration with appropriate precision"""
        if config.time_unit == TimeUnit.SECONDS:
            return f"{duration_ms / 1000:.3f}s"
        
        # Use color/formatting based on duration
        if duration_ms < 100:
            return f"{duration_ms:.2f}ms"
        elif duration_ms < 1000:
            return f"{duration_ms:.1f}ms"
        else:
            return f"{duration_ms / 1000:.2f}s"