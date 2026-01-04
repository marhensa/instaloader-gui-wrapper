"""
Instaloader GUI Wrapper - Constants
=================================

This module defines application-wide constants, default values, and configuration settings
used throughout the application. It centralizes configuration to ensure consistency across
all components and provides sensible default values for critical parameters.

Key constant groups:
- Application metadata and identification
- Directory and file paths
- Anti-detection system parameters
- Media handling configuration
- User interface color scheme

Having these constants in a centralized location makes it easier to modify application
behavior without having to search through multiple files.

Author: @marhensa
Version: 1.4
License: MIT License

Copyright (c) 2026 marhensa

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files, to deal in the Software
without restriction, including rights to use, copy, modify, merge, publish,
and/or distribute copies of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND.
"""
import os
import sys

def get_resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

# Application metadata and directory structure
APP_NAME = "Instaloader GUI Wrapper"
APP_VERSION = "1.4"

# Get instaloader version dynamically
try:
    import instaloader
    INSTALOADER_VERSION = instaloader.__version__
except (ImportError, AttributeError):
    INSTALOADER_VERSION = "unknown"

# Get absolute path to the application root directory (where code lives)
APP_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Determine execution directory (where the binary/script resides)
# This handles AppImage, PyInstaller, and source execution differently
if 'APPIMAGE' in os.environ:
    # Running as AppImage - use the directory containing the AppImage file
    EXEC_DIR = os.path.dirname(os.environ['APPIMAGE'])
elif getattr(sys, 'frozen', False):
    # Running as PyInstaller executable - use directory containing executable
    EXEC_DIR = os.path.dirname(sys.executable)
else:
    # Running from source - use project root
    EXEC_DIR = APP_ROOT

# Configuration file paths - store settings near executable/AppImage
CONFIG_DIR = os.path.join(EXEC_DIR, 'user-settings')
CONFIG_FILE = os.path.join(CONFIG_DIR, 'settings.json')
CONFIG_BACKUP = f"{CONFIG_FILE}.backup"

# Anti-detection system default parameters
DEFAULT_BASE_DELAY = 8.0       # Base delay between requests in seconds
DEFAULT_JITTER = 3.0           # Random time addition to appear more human-like
DEFAULT_STORY_MULTIPLIER = 2.5 # Stories are rate-limited more strictly
DEFAULT_CRITICAL_WAIT = 30     # Minutes to wait after encountering rate limits
DEFAULT_LONG_SESSION_CHANCE = 0.25  # Probability of taking a longer pause
DEFAULT_LONG_PAUSE_MIN = 20.0       # Minimum duration of a safety break in seconds
DEFAULT_LONG_PAUSE_MAX = 30.0       # Maximum duration of a safety break in seconds
DEFAULT_REQUEST_TIMEOUT = 300  # Request timeout in seconds

# Media handling settings
SUPPORTED_MEDIA_FORMATS = ('.jpg', '.jpeg', '.png', '.webp', '.mp4')  # Supported preview formats

# UI color scheme
COLORS = {
    'BACKGROUND': '#1E1E1E',    # Main background color
    'SECONDARY_BG': '#2B2B2B',  # Secondary background for inputs, etc.
    'BORDER': '#3E3E3E',        # Border color
    'TEXT': '#E0E0E0',          # Default text color
    'BUTTON': '#0D47A1',        # Button background color
    'BUTTON_HOVER': '#1565C0',  # Button hover state
    'BUTTON_PRESSED': '#0A3D91',# Button pressed state
    'INFO': '#E0E0E0',          # Info message color
    'WARNING': '#FFB74D',       # Warning message color
    'ERROR': '#FF5252'          # Error message color
}
