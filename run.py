"""
Instaloader GUI Wrapper - Application Entry Point
===============================================

This module serves as the main entry point for the Instaloader GUI Wrapper application.
It initializes the application, sets up logging, applies theming, and launches the 
main window to provide users with a graphical interface for Instagram content downloads.

The main() function handles:
- Logger initialization for application-wide consistent logging
- QApplication creation and setup
- Dark theme application for consistent UI appearance
- Main window initialization and display
- Graceful shutdown handling

This module should be run directly to start the application.

Example:
    $ python run.py

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
import sys
import os
import locale  # Restore missing import

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
import qdarktheme  # Add qdarktheme import
from src.gui import InstaloaderGUIWrapper
from src.core.logger import get_logger

def main():
    """
    Application entry point that sets up logging, initializes the main window,
    and starts the event loop.
    
    Returns:
        None: Application exits with system status code when event loop terminates.
    """
    # Initialize logger
    logger = get_logger()
    
    logger.info("====================================")
    logger.info("Instaloader GUI Wrapper starting up")
    logger.info("====================================")
    
    # Create Qt application
    app = QApplication(sys.argv)
    
    # Set convention for time formatting to C (standard English)
    # Qt init can reset locale, so we must set it AFTER QApplication creation
    try:
        old_locale = locale.getlocale(locale.LC_TIME)
        locale.setlocale(locale.LC_TIME, 'C')
        new_locale = locale.getlocale(locale.LC_TIME)
        logger.info(f"Locale forced to C for time parsing. Old: {old_locale}, New: {new_locale}")
    except locale.Error as e:
        logger.error(f"Failed to set locale: {e}")

    # Set application identity for Wayland/desktop integration
    app.setApplicationName("instaloader-gui-wrapper")
    app.setOrganizationName("marhensa")
    app.setDesktopFileName("instaloader-gui-wrapper")
    
    # Set application icon
    app_root = os.path.dirname(os.path.abspath(__file__))
    icon_path = os.path.join(app_root, "assets", "icon.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
        logger.info(f"Application icon set from: {icon_path}")
    
    # Apply dark theme to all widgets using qdarktheme
    qdarktheme.setup_theme()
    logger.info("Applied dark theme to application")
    
    # Create main window
    window = InstaloaderGUIWrapper()
    window.show()
    
    logger.info("Main window initialized and displayed")
    
    # Register graceful shutdown handler
    app.aboutToQuit.connect(lambda: logger.info("Application shutdown initiated"))
    
    # Start application event loop - blocks until app exit
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
