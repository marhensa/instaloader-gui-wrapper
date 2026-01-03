"""
Instaloader GUI Wrapper - UI Components
======================================

This module provides reusable UI components used across the application interface.
Components are designed for consistent look-and-feel and to avoid code duplication.

The main component in this module is LogViewer, which displays color-coded log
messages with different formatting based on message severity levels.

Classes:
    LogViewer: A specialized text display widget for showing color-coded log messages

Author: @marhensa
Version: 1.2
License: MIT License

Copyright (c) 2026 marhensa

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files, to deal in the Software
without restriction, including rights to use, copy, modify, merge, publish,
and/or distribute copies of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND.
"""
from PyQt5.QtWidgets import QTextEdit
from PyQt5.QtGui import QTextCharFormat, QColor
from ..config.constants import COLORS


class LogViewer(QTextEdit):
    """
    A specialized QTextEdit widget for displaying color-coded log messages.
    
    This component renders log entries with different colors based on their
    severity level (INFO, WARNING, ERROR) to improve visual distinction and
    readability. The widget is read-only and automatically formatted based
    on the application's color scheme defined in constants.
    
    The LogViewer is used in the main application window to display real-time
    download progress, authentication status, and other important system messages.
    
    Attributes:
        formats (dict): Dictionary of QTextCharFormat objects for different log levels
                        (INFO, WARNING, ERROR) with appropriate colors applied
    """
    
    def __init__(self):
        """
        Initialize the LogViewer widget.
        
        Sets up the widget as read-only and creates text formats with appropriate
        colors for different log severity levels based on the application's
        color scheme.
        """
        super().__init__()
        # Make the log viewer read-only to prevent user editing
        self.setReadOnly(True)
        
        # Initialize text formats for different log severity levels
        self.formats = {
            'INFO': QTextCharFormat(),    # Standard informational messages
            'WARNING': QTextCharFormat(), # Warning messages that need attention
            'ERROR': QTextCharFormat()    # Error messages indicating problems
        }
        
        # Apply colors from the application color scheme to each format
        self.formats['INFO'].setForeground(QColor(COLORS['INFO']))         # Normal messages (usually white/light gray)
        self.formats['WARNING'].setForeground(QColor(COLORS['WARNING']))   # Warnings (usually orange/yellow)
        self.formats['ERROR'].setForeground(QColor(COLORS['ERROR']))       # Errors (usually red)
        
        # Apply consistent styling to the log viewer background and default text color
        self.setStyleSheet(f"background-color: {COLORS['SECONDARY_BG']}; color: {COLORS['TEXT']};")

    def append_log(self, msg, level='INFO'):
        """
        Append a new log message to the viewer with appropriate formatting.
        
        This method applies the correct color formatting based on the message's
        severity level before appending it to the log display.
        
        Args:
            msg (str): The log message text to display
            level (str): Severity level of the message ('INFO', 'WARNING', or 'ERROR')
                         Defaults to 'INFO' if not specified
        """
        # Apply the appropriate text format based on the log level
        self.setCurrentCharFormat(self.formats.get(level, self.formats['INFO']))
        
        # Add the new message to the end of the log display
        self.append(msg)
