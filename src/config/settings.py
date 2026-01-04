"""
Instaloader GUI Wrapper - Settings Management
===========================================

This module handles the loading, saving, and managing of user preferences and application settings.
It provides a simple interface for persistence of configuration data between application sessions.

The Settings class offers static methods to save and load configuration settings to/from JSON files,
with built-in error handling and backup creation to prevent data loss in case of file corruption.

Features:
- JSON-based configuration storage
- Automatic backup creation
- Platform-independent file handling
- Error recovery with fallback to backups
- Timestamp tracking of setting changes

Classes:
    Settings: Static utility class for managing application settings

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
import json
import os
import logging
from datetime import datetime
import shutil
from .constants import CONFIG_DIR, CONFIG_FILE, CONFIG_BACKUP

class Settings:
    """
    Static class for managing application settings.
    Provides methods to save and load settings from JSON configuration files.
    """
    
    @staticmethod
    def save_settings(config):
        """
        Save user settings to a JSON configuration file with backup creation.
        
        Args:
            config (dict): Dictionary containing configuration settings to save
            
        Returns:
            tuple: (success_flag, message) where success_flag is a boolean indicating
                  if the save operation succeeded and message is a descriptive string
        """
        # Add timestamp for tracking setting changes
        config['last_saved'] = datetime.now().isoformat()
        
        try:
            # Ensure config directory exists
            os.makedirs(CONFIG_DIR, exist_ok=True)
            
            logger = logging.getLogger("instagram_downloader")
            logger.info(f"Saving settings to: {CONFIG_FILE}")
            
            # Create backup of previous settings if they exist
            if os.path.exists(CONFIG_FILE):
                try:
                    shutil.copy2(CONFIG_FILE, CONFIG_BACKUP)
                except Exception as e:
                    logger.error(f"Failed to create settings backup: {e}")
            
            # Write settings to file with pretty formatting
            with open(CONFIG_FILE, 'w') as f:
                json.dump(config, f, indent=4)
            return True, f"Settings saved to {CONFIG_FILE}"
        except Exception as e:
            return False, f"Error saving settings: {e}"

    @staticmethod
    def load_settings():
        """
        Load user settings from JSON configuration file with fallback to backup.
        
        Returns:
            tuple: (settings, message) where settings is a dictionary of configuration
                  values (or None if loading failed) and message is a descriptive string
        """
        logger = logging.getLogger("instagram_downloader")
        logger.info(f"Attempting to load settings from: {CONFIG_FILE}")
        
        try:
            # Try loading the main settings file
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f), "Settings loaded successfully"
        except FileNotFoundError:
            # If main file not found, try loading from backup
            if os.path.exists(CONFIG_BACKUP):
                try:
                    with open(CONFIG_BACKUP, 'r') as f:
                        return json.load(f), "Settings restored from backup"
                except Exception as e:
                    return None, f"Error loading backup settings: {e}"
            return None, "No saved settings found"
        except Exception as e:
            # On any error, try the backup
            if os.path.exists(CONFIG_BACKUP):
                try:
                    with open(CONFIG_BACKUP, 'r') as f:
                        return json.load(f), "Settings restored from backup"
                except Exception as backup_error:
                    return None, f"Error loading settings and backup: {backup_error}"
            return None, f"Error loading settings: {e}"
