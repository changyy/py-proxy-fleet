"""
Output utilities for saving request results and logs.
"""

import json
import gzip
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
import logging

from ..models.task import TaskResult


logger = logging.getLogger(__name__)


class OutputManager:
    """Manages output files and directories for task results."""
    
    def __init__(self, output_dir: str = "output", compress: bool = False):
        """
        Initialize output manager.
        
        Args:
            output_dir: Base directory for output files
            compress: Whether to compress output files
        """
        self.output_dir = Path(output_dir)
        self.compress = compress
        
        # Create output directories
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "responses").mkdir(exist_ok=True)
        (self.output_dir / "results").mkdir(exist_ok=True)
        (self.output_dir / "logs").mkdir(exist_ok=True)
    
    def save_task_result(self, result: TaskResult) -> str:
        """
        Save task result to JSON file.
        
        Args:
            result: Task result to save
            
        Returns:
            Path to saved file
        """
        try:
            # Generate filename based on task info
            timestamp = result.started_at.strftime("%Y%m%d_%H%M%S")
            task_id = result.task_id or "unknown"
            filename = f"{timestamp}_{task_id}_result.json"
            
            if self.compress:
                filename += ".gz"
            
            file_path = self.output_dir / "results" / filename
            
            # Prepare result data with proper datetime serialization
            result_data = result.dict()
            
            # Convert datetime objects and bytes to proper format
            for key, value in result_data.items():
                if isinstance(value, datetime):
                    result_data[key] = value.isoformat()
                elif isinstance(value, bytes):
                    # Convert bytes to string for JSON serialization
                    try:
                        result_data[key] = value.decode('utf-8', errors='ignore')
                    except:
                        result_data[key] = value.hex()  # Fallback to hex representation
            
            # Save to file
            if self.compress:
                with gzip.open(file_path, 'wt', encoding='utf-8') as f:
                    json.dump(result_data, f, indent=2, ensure_ascii=False)
            else:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(result_data, f, indent=2, ensure_ascii=False)
            
            logger.debug(f"Saved task result to {file_path}")
            return str(file_path)
        
        except Exception as e:
            logger.error(f"Failed to save task result: {e}")
            return ""
    
    def save_response_data(
        self, 
        result: TaskResult, 
        max_size: int = 10485760
    ) -> Optional[str]:
        """
        Save response data to separate file if it's not too large.
        
        Args:
            result: Task result containing response data
            max_size: Maximum response size to save (bytes)
            
        Returns:
            Path to saved response file or None
        """
        if not result.response_data or result.response_size and result.response_size > max_size:
            return None
        
        try:
            # Generate filename based on URL hash and timestamp
            url_hash = hashlib.md5(result.url.encode()).hexdigest()[:8]
            timestamp = result.started_at.strftime("%Y%m%d_%H%M%S")
            
            # Determine file extension from content type
            content_type = result.response_headers.get('content-type', '') if result.response_headers else ''
            if 'json' in content_type:
                ext = '.json'
            elif 'html' in content_type:
                ext = '.html'
            elif 'xml' in content_type:
                ext = '.xml'
            else:
                ext = '.txt'
            
            filename = f"{timestamp}_{url_hash}_response{ext}"
            
            if self.compress:
                filename += ".gz"
            
            file_path = self.output_dir / "responses" / filename
            
            # Save response data
            if isinstance(result.response_data, bytes):
                mode = 'wb' if not self.compress else 'wt'
                data = result.response_data.decode('utf-8', errors='ignore') if self.compress else result.response_data
            else:
                mode = 'w' if not self.compress else 'wt'
                data = result.response_data
            
            if self.compress:
                with gzip.open(file_path, mode, encoding='utf-8' if 't' in mode else None) as f:
                    f.write(data)
            else:
                with open(file_path, mode, encoding='utf-8' if 'b' not in mode else None) as f:
                    f.write(data)
            
            logger.debug(f"Saved response data to {file_path}")
            return str(file_path)
        
        except Exception as e:
            logger.error(f"Failed to save response data: {e}")
            return None
    
    def save_summary_report(
        self, 
        results: list, 
        proxy_stats: Dict[str, Any],
        start_time: datetime,
        end_time: datetime
    ):
        """
        Save execution summary report.
        
        Args:
            results: List of task results
            proxy_stats: Proxy usage statistics
            start_time: Execution start time
            end_time: Execution end time
        """
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{timestamp}_summary_report.json"
            file_path = self.output_dir / "logs" / filename
            
            # Calculate statistics
            total_tasks = len(results)
            successful_tasks = sum(1 for r in results if r.is_success)
            failed_tasks = total_tasks - successful_tasks
            
            avg_response_time = 0
            if successful_tasks > 0:
                response_times = [r.response_time for r in results if r.response_time]
                avg_response_time = sum(response_times) / len(response_times) if response_times else 0
            
            duration = (end_time - start_time).total_seconds()
            
            summary = {
                'execution_summary': {
                    'start_time': start_time.isoformat(),
                    'end_time': end_time.isoformat(),
                    'duration_seconds': duration,
                    'total_tasks': total_tasks,
                    'successful_tasks': successful_tasks,
                    'failed_tasks': failed_tasks,
                    'success_rate': successful_tasks / total_tasks if total_tasks > 0 else 0,
                    'avg_response_time': avg_response_time
                },
                'proxy_statistics': proxy_stats,
                'generated_at': datetime.now().isoformat()
            }
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(summary, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Saved summary report to {file_path}")
        
        except Exception as e:
            logger.error(f"Failed to save summary report: {e}")


def setup_logging(log_file: Optional[str] = None, level: str = "INFO") -> logging.Logger:
    """
    Setup logging configuration.
    
    Args:
        log_file: Optional log file path
        level: Logging level
        
    Returns:
        Configured logger
    """
    log_level = getattr(logging, level.upper(), logging.INFO)
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Setup root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # File handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    
    return root_logger
