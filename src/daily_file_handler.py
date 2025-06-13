import logging
import logging.config
from datetime import datetime
from pathlib import Path
import os

class DailyFileHandler(logging.FileHandler):
    """Custom handler that creates a new log file each day with date in filename"""
    
    def __init__(self, filename_pattern, mode='a', encoding='utf-8', delay=False):
        """
        filename_pattern should contain {date} placeholder
        e.g., 'logs/app-{date}.log'
        """
        self.filename_pattern = filename_pattern
        self.current_date = None
        self.mode = mode
        self.encoding = encoding
        self.delay = delay
        
        # Initialize with today's filename
        filename = self._get_current_filename()
        super().__init__(filename, mode, encoding, delay)
    
    def _get_current_filename(self):
        """Generate filename with current date"""
        current_date = datetime.now().strftime('%Y-%m-%d')
        return self.filename_pattern.format(date=current_date)
    
    def emit(self, record):
        """Override emit to check if we need a new file for today"""
        current_date = datetime.now().strftime('%Y-%m-%d')
        
        # If date has changed, close current file and open new one
        if self.current_date != current_date:
            if self.stream and not self.stream.closed:
                self.stream.close()
            
            self.current_date = current_date
            self.baseFilename = self._get_current_filename()
            
            # Ensure directory exists
            Path(self.baseFilename).parent.mkdir(parents=True, exist_ok=True)
            
            # Reset stream so it gets reopened with new filename
            self.stream = None
        
        super().emit(record)