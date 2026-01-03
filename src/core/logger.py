"""
Instaloader GUI Wrapper - Logging System
=======================================

This module provides unified logging functionality for the application with support for GUI display,
file output, and console output. It implements a centralized logging system that ensures log entries
are consistently formatted and properly displayed across all application components.

The module includes specialized log handlers for different output targets:
- File logging with immediate flushing to ensure logs are saved even on application crash
- Console logging with Unicode character handling to prevent display issues
- GUI integration for displaying log messages in the application interface

Features:
- Thread-safe logging implementation
- Color-coded log levels for improved readability
- Support for non-ASCII characters in log messages
- Singleton logger instance for application-wide use
- Automatic cleanup on application exit

Classes:
    GUILogHandler: Custom log handler that emits Qt signals for GUI display
    FileHandlerWithFlush: Enhanced file handler with immediate flush after each log entry
    SafeConsoleHandler: Console handler with Unicode character handling

Author: @marhensa
Version: 1.3
License: MIT License

Copyright (c) 2026 marhensa

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files, to deal in the Software
without restriction, including rights to use, copy, modify, merge, publish,
and/or distribute copies of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND.
"""
import logging
import os
import atexit
import sys
from PyQt6.QtCore import pyqtSignal

class GUILogHandler(logging.Handler):
    """
    Custom log handler that emits Qt signals when log records are received.
    Used to display log messages in the GUI.
    """
    def __init__(self, signal):
        """
        Initialize the handler with a Qt signal.
        
        Args:
            signal: PyQt signal that accepts message text and log level arguments
        """
        super().__init__()
        self.signal = signal

    def emit(self, record):
        """
        Process a log record and emit it via signal to the GUI.
        
        Args:
            record: Log record object containing message details
        """
        msg = self.format(record)
        self.signal.emit(msg, record.levelname)

class FileHandlerWithFlush(logging.FileHandler):
    """
    Enhanced file handler that immediately flushes after writing each log entry.
    Ensures logs are written to disk even if application crashes.
    """
    def emit(self, record):
        """
        Write log record to file and flush immediately.
        
        Args:
            record: Log record object containing message details
        """
        super().emit(record)
        self.flush()

class SafeConsoleHandler(logging.StreamHandler):
    """
    Console handler with enhanced Unicode character handling.
    Prevents crashes on Windows consoles that can't display certain characters.
    """
    def emit(self, record):
        """
        Write log record to console with Unicode character handling.
        
        Args:
            record: Log record object containing message details
        """
        try:
            msg = self.format(record)
            stream = self.stream
            # Handle Unicode characters safely for Windows console
            try:
                stream.write(msg + self.terminator)
            except UnicodeEncodeError:
                # Fall back to ASCII representation for problematic Unicode
                safe_msg = msg.encode('ascii', 'backslashreplace').decode('ascii')
                stream.write(safe_msg + self.terminator)
            self.flush()
        except Exception:
            self.handleError(record)
        
# Singleton logger instance for application-wide use
_logger_instance = None

def setup_logger():
    """
    Configure and initialize the application logger with console and file handlers.
    
    Sets up the main application logger with appropriate handlers and formatters.
    Creates both file and console outputs with proper encoding and error handling.
    
    Returns:
        logging.Logger: Configured logger instance
    """
    global _logger_instance
    
    # Return existing logger if already initialized
    if _logger_instance is not None:
        return _logger_instance
    
    # Create and configure logger
    logger = logging.getLogger("instagram_downloader")
    logger.setLevel(logging.INFO)
    
    # Remove any existing handlers to prevent duplicates
    if logger.handlers:
        for handler in logger.handlers:
            logger.removeHandler(handler)
    
    # Configure log file path in same directory as the application
    log_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 
                                  "..", "..", 
                                  "instagram_downloader.log")
    
    # Create and add file handler with immediate flushing
    file_handler = FileHandlerWithFlush(log_file_path, mode='a', delay=False, encoding='utf-8')
    file_handler.setFormatter(
        logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    )
    
    # Create and add console handler with Unicode safety
    console_handler = SafeConsoleHandler(sys.stdout)
    console_handler.setFormatter(
        logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    )
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    # Register cleanup function to ensure logs are flushed on exit
    def cleanup():
        """Close and flush log handlers on application exit."""
        logger.info("Application shutting down - closing log handlers")
        for handler in logger.handlers:
            handler.flush()
            handler.close()
    
    atexit.register(cleanup)
    
    # Verify logging is working
    logger.info("Logger initialized")
    
    # Store singleton instance
    _logger_instance = logger
    return logger

def get_logger():
    """
    Get the singleton logger instance, creating it if needed.
    
    This function provides access to the application-wide logger instance,
    ensuring that the same logger is used throughout the application.
    
    Returns:
        logging.Logger: The application-wide logger instance
    """
    global _logger_instance
    if _logger_instance is None:
        return setup_logger()
    return _logger_instance

class Logger:
    """
    High-level logging interface for download state management.
    Provides structured logging for download state transitions.
    """
    def __init__(self):
        """Initialize logger with application-wide logger instance"""
        self.logger = get_logger()
        self.last_state = None

    def log(self, level, message):
        """Log a message with the specified level"""
        log_method = getattr(self.logger, level.lower(), self.logger.info)
        log_method(message)

    def log_state_change(self, state, details=None):
        """
        Log download state changes with consistent formatting.
        
        Args:
            state (str): The new state ('started', 'paused', 'resumed', 'stopped', 'completed')
            details (str, optional): Additional details about the state change
        """
        states = {
            'started': ('info', 'Download process started'),
            'paused': ('warning', 'Download process paused - Use Resume button to continue'),
            'resumed': ('info', 'Download process resumed from pause'),
            'stopped': ('warning', 'Download process stopped by user'),
            'completed': ('success', 'Download process completed successfully'),
            'error': ('error', 'Download process encountered an error'),
            'rate_limited': ('warning', 'Download paused - Instagram rate limit detected'),
            'pause_failed': ('error', 'Failed to pause download - Process in invalid state'),
            'resume_failed': ('error', 'Failed to resume download - Process in invalid state')
        }
        
        # Get level and base message
        level, message = states.get(state, ('info', f'State changed to: {state}'))
        
        # Add transition details if relevant
        if self.last_state and state in ['paused', 'resumed', 'stopped']:
            message = f"{message} (from {self.last_state} state)"
        
        # Add any additional details
        if details:
            message += f" - {details}"
        
        # Map 'success' to 'info' since logging doesn't have a success level
        if level == 'success':
            level = 'info'
            
        self.log(level, message)
        self.last_state = state

    def log_pause_operation(self, success, current_state):
        """Log the result of a pause operation attempt"""
        if success:
            self.log_state_change('paused', f'Download paused successfully while {current_state}')
        else:
            self.log_state_change('pause_failed', f'Cannot pause while in {current_state} state')

    def log_resume_operation(self, success, current_state):
        """Log the result of a resume operation attempt"""
        if success:
            self.log_state_change('resumed', f'Download resumed from {current_state}')
        else:
            self.log_state_change('resume_failed', f'Cannot resume while in {current_state} state')

    def log_error(self, error_msg, details=None):
        """Log an error with optional details"""
        message = f"Error: {error_msg}"
        if details:
            message += f" - {details}"
        self.log('error', message)

    def log_warning(self, warning_msg, details=None):
        """Log a warning with optional details"""
        message = f"Warning: {warning_msg}"
        if details:
            message += f" - {details}"
        self.log('warning', message)

    def log_info(self, info_msg, details=None):
        """Log an info message with optional details"""
        message = info_msg
        if details:
            message += f" - {details}"
        self.log('info', message)
