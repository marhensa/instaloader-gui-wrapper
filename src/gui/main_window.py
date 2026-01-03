"""
Instaloader GUI Wrapper - Main Window Implementation
==================================================

This module provides the primary user interface for the Instaloader GUI Wrapper application.
It implements the main application window with all UI components, user interactions,
configuration management, and coordinates the download operations through worker threads.

The UI is structured with a tabbed interface containing basic settings, advanced options,
and application information, along with a log viewer and download preview panel.

Features:
- User authentication via credentials or session files
- Two-factor authentication support
- Profile and post download configuration
- Progress tracking with real-time feedback
- Content preview for downloaded media
- Anti-detection timing system configuration
- Settings persistence management

Classes:
    InstaloaderGUIWrapper: Main application window class that manages the entire UI

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
import glob
from datetime import datetime
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                           QLineEdit, QCheckBox, QPushButton, QTextEdit, 
                           QProgressBar, QLabel, QFileDialog, QDateEdit,
                           QGroupBox, QSizePolicy, QDoubleSpinBox, QSpinBox,
                           QTabWidget, QMessageBox, QFrame, QDialog, QInputDialog,
                           QApplication)
from PyQt6.QtCore import (Qt, QDate, pyqtSignal, QEventLoop, QTimer, QMetaObject, 
                         Q_ARG, QThread, pyqtSlot)
from PyQt6.QtGui import QPixmap, QIcon, QFont, QIntValidator

from .components import LogViewer
from ..core.downloader import DownloaderThread, ProfileCheckThread
from ..config.settings import Settings
from ..config.constants import (DEFAULT_BASE_DELAY, DEFAULT_JITTER, 
                              DEFAULT_STORY_MULTIPLIER, DEFAULT_CRITICAL_WAIT, 
                              DEFAULT_LONG_SESSION_CHANCE, DEFAULT_REQUEST_TIMEOUT,
                              SUPPORTED_MEDIA_FORMATS, APP_NAME, APP_VERSION, 
                              INSTALOADER_VERSION, APP_ROOT, EXEC_DIR, get_resource_path)
from ..core.logger import get_logger

class InstaloaderGUIWrapper(QMainWindow):
    """
    Main application window for Instaloader GUI Wrapper.
    
    This class creates and manages the entire user interface, handling all user 
    interactions and coordinating the background download processes. It provides 
    functionality for downloading Instagram profiles, posts, stories, and highlights
    with various configuration options.
    
    The window is divided into a left panel containing settings and controls, and a
    right panel showing download previews. The left panel is further organized into
    tabs for basic settings, advanced settings, and application information.
    
    Signals:
        start_download (dict): Emitted when a download is initiated
        two_factor_signal (str): Sends 2FA code to the downloader thread
        two_factor_prompt: Triggers the 2FA dialog to appear
    
    Attributes:
        is_downloading (bool): Flag indicating if a download is currently in progress
        downloader_thread (DownloaderThread): Thread handling the download operations
        profile_check_thread (ProfileCheckThread): Thread for verifying profile existence
        logger: Application-wide logger instance
        last_download_path (str): Path to the most recently downloaded file
        single_post_profile (str): Username of the owner of a single post being downloaded
    """
    start_download = pyqtSignal(dict)
    two_factor_signal = pyqtSignal(str)
    two_factor_prompt = pyqtSignal()
    
    def __init__(self):
        """
        Initialize the main window and configure the UI components.
        
        Sets up the window properties, initializes all UI components,
        loads saved settings, and configures signal connections.
        
        The initialization sequence is:
        1. Setup basic window properties (title, icon, size)
        2. Initialize logger and state variables
        3. Build the user interface components
        4. Load saved application settings
        5. Apply styling to components
        6. Set up 2FA handling mechanism
        """
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION} | Instaloader Python Library v{INSTALOADER_VERSION}")
        self.setWindowIcon(QIcon(get_resource_path("icon.ico")))
        self.setMinimumSize(1200, 800)
        self.downloader_thread = None
        self.last_download_path = None
        self.profile_check_thread = None
        self.single_post_profile = None  # Track profile owner for single post downloads
        
        # Initialize logger for application-wide logging
        self.logger = get_logger()
        self.logger.info("Initializing application UI")
        
        # Flag to track active download state
        self.is_downloading = False
        
        # Set up the user interface components
        self.setup_ui()
        self.load_settings()
        self.apply_styles()
        self.logger.info("Application UI fully initialized")
        
        # Initialize 2FA dialog variables
        self.two_factor_dialog = None
        self.two_factor_input = None
        # Connect 2FA signal to handler that will run in the main thread
        self.two_factor_prompt.connect(self.create_two_factor_dialog)

    def setup_ui(self):
        """
        Create the main UI layout structure.
        
        Constructs the basic window layout with left panel for controls
        and right panel for preview images and information.
        """
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        
        # Create left panel with controls (2/3 of window width)
        left_panel = self.create_left_panel()
        main_layout.addWidget(left_panel, stretch=2)
        
        # Create right panel with preview (1/3 of window width)
        right_panel = self.create_right_panel()
        main_layout.addWidget(right_panel, stretch=1)

    def create_left_panel(self):
        """
        Create the left panel containing all control elements.
        
        Returns:
            QWidget: The fully configured left panel with all UI components
        """
        left_panel = QWidget()
        layout = QVBoxLayout(left_panel)
        left_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        # Create tabbed interface
        self.tabs = QTabWidget()
        self.basic_tab = QWidget()
        self.advanced_tab = QWidget()
        self.about_tab = QWidget()
        
        self.tabs.addTab(self.basic_tab, "Basic Settings")
        self.tabs.addTab(self.advanced_tab, "Advanced Settings")
        self.tabs.addTab(self.about_tab, "About")
        
        basic_layout = QVBoxLayout(self.basic_tab)
        advanced_layout = QVBoxLayout(self.advanced_tab)
        about_layout = QVBoxLayout(self.about_tab)
        
        # Set up the tab contents
        self.setup_input_fields(basic_layout)
        self.setup_download_options(basic_layout)
        self.setup_advanced_settings(advanced_layout)
        self.setup_about_tab(about_layout)
        
        layout.addWidget(self.tabs)
        
        # Add progress tracking section
        self.setup_progress_bars(layout)
        
        # Add log viewer at the bottom
        self.log_viewer = LogViewer()
        layout.addWidget(self.log_viewer)
        
        # Custom style for group boxes to improve appearance
        left_panel.setStyleSheet("QGroupBox { padding-top: 12px; margin-top: 5px; }")
        
        return left_panel

    def create_right_panel(self):
        """
        Create the right panel with preview image and information.
        
        Returns:
            QWidget: The configured right panel with preview components
        """
        right_panel = QWidget()
        right_panel.setMinimumWidth(400)
        right_panel.setMaximumWidth(600)
        layout = QVBoxLayout(right_panel)
        
        # Image preview area with placeholder text
        self.preview_label = QLabel("No images downloaded yet")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumHeight(400)
        self.preview_label.setStyleSheet("background-color: #2B2B2B; border: 1px solid #3E3E3E;")
        
        # Image information text area
        self.image_info = QTextEdit()
        self.image_info.setReadOnly(True)
        self.image_info.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.image_info.setStyleSheet("background-color: #2B2B2B; border: 1px solid #3E3E3E;")
        
        # Add components to layout
        layout.addWidget(QLabel("Latest Download Preview"))
        layout.addWidget(self.preview_label)
        layout.addWidget(QLabel("Image Information"))
        layout.addWidget(self.image_info)
        
        return right_panel

    def setup_input_fields(self, layout):
        """
        Create and configure the authentication and target selection inputs.
        
        This method creates UI components for:
        1. Login credentials (username/password)
        2. Session file handling
        3. Target profile selection
        4. Single post URL input
        5. Download location configuration
        
        Args:
            layout (QVBoxLayout): Layout to add the input components to
        """
        # Create login credentials group
        cred_group = QGroupBox("👤 Login Credentials")
        cred_layout = QVBoxLayout()
        
        # Username/password input row
        login_layout = QHBoxLayout()
        self.username = QLineEdit()
        self.username.setPlaceholderText("Instagram Username")
        self.password = QLineEdit()
        self.password.setPlaceholderText("Instagram Password")
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        login_layout.addWidget(self.username)
        login_layout.addWidget(self.password)
        cred_layout.addLayout(login_layout)
        
        # Visual separator
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        cred_layout.addWidget(line)
        
        # Save session option with help tooltip
        save_session_layout = QHBoxLayout()
        self.save_session = QCheckBox("💾 Save 'Session File' after login (avoids login and/or 2FA next time)")
        save_font = self.save_session.font()
        save_font.setBold(False)
        self.save_session.setFont(save_font)
        self.save_session.setChecked(True)  # Enabled by default
        self.save_session.setToolTip("Save login session to avoid having to enter credential and 2FA code on future logins")
        save_session_layout.addWidget(self.save_session)
        
        # Help icon with tooltip explaining session files
        help_label = QLabel("❓")
        help_label.setStyleSheet("color: #E0E0E0;")
        session_locations = (
            "Session files are like password stored cookies, located in:\n"
            "(!!! make sure to delete it if you use public computer !!!)\n"
            "Windows: %localappdata%\\Instaloader\\session-yourusername\n"
            "Linux: ~/.config/instaloader/session-yourusername"
        )
        help_label.setToolTip(session_locations)
        save_session_layout.addWidget(help_label)
        
        save_session_layout.addStretch()
        cred_layout.addLayout(save_session_layout)
        
        # Spacer for visual separation
        cred_layout.addSpacing(10)
        
        # Session file selection
        session_layout = QHBoxLayout()
        session_layout.setSpacing(5)
        
        # Container for checkbox and help icon
        checkbox_container = QWidget()
        checkbox_layout = QHBoxLayout(checkbox_container)
        checkbox_layout.setContentsMargins(0, 0, 0, 0)
        checkbox_layout.setSpacing(2)
        
        # Session option toggle
        self.use_session = QCheckBox("Check to Use 'Session File'")
        self.use_session.stateChanged.connect(self.toggle_credentials)
        
        checkbox_layout.addWidget(self.use_session)
        checkbox_layout.addStretch(0)
        
        session_layout.addWidget(checkbox_container)
        
        # Session file path and selection button
        self.session_path = QLineEdit()
        self.session_path.setReadOnly(True)
        self.session_button = QPushButton("Select Session File")
        
        # Configure size policies
        self.session_path.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.session_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        checkbox_container.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        
        session_layout.addWidget(self.session_path, stretch=1)
        session_layout.addWidget(self.session_button)
        
        # Connect session button to file dialog
        self.session_button.clicked.connect(self.select_session_file)
        cred_layout.addLayout(session_layout)
        
        cred_group.setLayout(cred_layout)
        layout.addWidget(cred_group)

        # Target profile/post selection group
        target_group = QGroupBox("📥 Download Target")
        target_layout = QVBoxLayout()
        
        # Profile selection row with name verification
        profile_layout = QHBoxLayout()
        profile_label = QLabel("Target Profile:")
        self.target_profile = QLineEdit()
        self.target_profile.setPlaceholderText("username without @")
        
        self.check_name_button = QPushButton("Check Name")
        self.check_name_button.clicked.connect(self.check_profile_name)
        self.check_name_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        
        # Display area for profile verification results
        self.profile_name_display = QLabel("")
        
        profile_layout.addWidget(profile_label, 0)
        profile_layout.addWidget(self.target_profile, 3)  # Wider field for better visibility
        profile_layout.addWidget(self.check_name_button, 0)
        profile_layout.addWidget(self.profile_name_display, 2)
        target_layout.addLayout(profile_layout)
        
        # Single post URL input row
        url_layout = QHBoxLayout()
        self.download_single_post = QCheckBox("Download Single Post")
        self.download_single_post.stateChanged.connect(self.toggle_single_post)
        
        url_label = QLabel("URL:")
        self.post_url = QLineEdit()
        self.post_url.setPlaceholderText("https://www.instagram.com/p/xyzabc123/ (supports posts/reels/stories/highlights)")
        self.post_url.setEnabled(False)  # Disabled by default
        
        url_layout.addWidget(self.download_single_post)
        url_layout.addWidget(url_label)
        url_layout.addWidget(self.post_url)
        target_layout.addLayout(url_layout)
        
        # Download location selection
        save_layout = QHBoxLayout()
        
        dir_label = QLabel("📂 Download Location:")
        self.dir_path = QLineEdit()
        self.dir_path.setReadOnly(True)
        # Auto-populate with default downloads directory
        # Using EXEC_DIR to ensure it points to the AppImage/Exe location, not temp dir
        self.dir_path.setText(EXEC_DIR)
        self.dir_button = QPushButton("Browse...")
        self.dir_button.clicked.connect(self.select_directory)
        
        # Option to skip existing files
        self.skip_existing = QCheckBox("Skip Existing Files")
        self.skip_existing.setChecked(True)  # Enabled by default
        self.skip_existing.setToolTip("Skip downloading files that already exist locally")
        
        save_layout.addWidget(dir_label)
        save_layout.addWidget(self.dir_path, 3)  # Wider field for better path visibility
        save_layout.addWidget(self.dir_button)
        save_layout.addWidget(self.skip_existing)
        target_layout.addLayout(save_layout)
        
        target_group.setLayout(target_layout)
        layout.addWidget(target_group)

    def setup_download_options(self, layout):
        """
        Create and configure the download options section.
        
        Args:
            layout (QVBoxLayout): Layout to add the options components to
        """
        options_group = QGroupBox("🔽 Download Options (for Target Profile)")
        options_layout = QVBoxLayout()
        
        # Date range selection
        date_layout = QHBoxLayout()
        date_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)  # Center contents
        
        # Container for date range selectors
        self.date_widget = QWidget()
        date_sub_layout = QHBoxLayout(self.date_widget)
        date_sub_layout.setContentsMargins(0, 0, 0, 0)
        date_sub_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Date range inputs
        since_label = QLabel("Date Range From:")
        self.since_date = QDateEdit()
        self.since_date.setCalendarPopup(True)
        self.since_date.setDate(QDate.currentDate().addYears(-1))  # Default to 1 year ago
        
        until_label = QLabel("To:")
        self.until_date = QDateEdit()
        self.until_date.setCalendarPopup(True)
        self.until_date.setDate(QDate.currentDate())  # Default to today
        
        date_sub_layout.addWidget(since_label)
        date_sub_layout.addWidget(self.since_date)
        date_sub_layout.addWidget(until_label)
        date_sub_layout.addWidget(self.until_date)
        
        # Option to ignore date filtering
        self.ignore_date_range = QCheckBox("Ignore Date Range")
        self.ignore_date_range.setToolTip("Download all posts regardless of date range settings")
        self.ignore_date_range.stateChanged.connect(self.toggle_date_range)
        self.ignore_date_range.setChecked(True)  # Set to checked by default
        
        date_layout.addStretch(1)  # For centering
        date_layout.addWidget(self.date_widget)
        date_layout.addWidget(self.ignore_date_range)
        date_layout.addStretch(1)  # For centering
        
        options_layout.addLayout(date_layout)
        
        # Add max posts limit option
        limit_layout = QHBoxLayout()
        limit_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.limit_posts = QCheckBox("Limit Number of Posts:")
        self.limit_posts.setToolTip("Set a maximum number of posts to download")
        self.limit_posts.stateChanged.connect(self.toggle_post_limit)
        
        self.max_posts = QSpinBox()
        self.max_posts.setMinimum(1)
        self.max_posts.setMaximum(10000)
        self.max_posts.setValue(50)  # Default reasonable value
        self.max_posts.setEnabled(False)  # Disabled by default
        self.max_posts.setToolTip("Maximum number of posts to download")
        
        limit_layout.addStretch(1)
        limit_layout.addWidget(self.limit_posts)
        limit_layout.addWidget(self.max_posts)
        limit_layout.addStretch(1)
        
        options_layout.addLayout(limit_layout)
        
        # Separator line
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        options_layout.addWidget(line)
        
        # Main content type selection row (centered)
        checkbox_row1 = QHBoxLayout()
        checkbox_row1.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.download_highlights = QCheckBox("+ Download Highlights")
        self.download_stories = QCheckBox("+ Download Stories")
        
        checkbox_row1.addWidget(self.download_highlights)
        checkbox_row1.addWidget(self.download_stories)
        options_layout.addLayout(checkbox_row1)
        
        # Specialized download mode options (centered)
        checkbox_row2 = QHBoxLayout()
        checkbox_row2.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.only_highlights = QCheckBox("Only Download Highlights") 
        self.only_highlights.setToolTip("Skip downloading posts and stories, only download highlights")
        self.only_stories = QCheckBox("Only Download Stories")
        self.only_stories.setToolTip("Skip downloading posts, only download stories")
        self.profile_pic_only = QCheckBox("Only Download Profile Picture")
        self.profile_pic_only.setToolTip("Download only the profile picture")
        
        checkbox_row2.addWidget(self.only_highlights)
        checkbox_row2.addWidget(self.only_stories)
        checkbox_row2.addWidget(self.profile_pic_only)
        options_layout.addLayout(checkbox_row2)

        # Connect option toggles to handle mutual exclusivity
        self.only_stories.stateChanged.connect(self.handle_only_stories)
        self.only_highlights.stateChanged.connect(self.handle_only_highlights)
        self.profile_pic_only.stateChanged.connect(self.handle_profile_pic_only)
        
        options_group.setLayout(options_layout)
        layout.addWidget(options_group)
        
        # Add control button group below options group
        self.control_group = QHBoxLayout()
        
        self.start_button = QPushButton("▶ Start")
        self.stop_button = QPushButton("⏹ Stop")
        
        # Set object names for styling
        self.start_button.setObjectName("start_button")
        self.stop_button.setObjectName("stop_button")
        
        # Connect buttons
        self.start_button.clicked.connect(self.toggle_start_pause)
        self.stop_button.clicked.connect(self.stop_download)
        
        # Set initial button states
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        
        self.control_group.addWidget(self.start_button)
        self.control_group.addWidget(self.stop_button)
        
        layout.addLayout(self.control_group)

    def setup_advanced_settings(self, layout):
        """
        Create and configure the advanced settings tab content.
        
        Args:
            layout (QVBoxLayout): Layout to add the advanced settings to
        """
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        
        timing_group = QGroupBox("⏱️ Anti-Detection Timing System")
        timing_layout = QVBoxLayout()
        timing_group.setLayout(timing_layout)
        
        # Information text about timing system
        info_text = QLabel(
            "Adjust to find right balance between download speed and account safety."
        )
        info_text.setWordWrap(True)
        info_text.setStyleSheet("color: #808080; font-style: italic; margin-bottom: 10px;")
        timing_layout.addWidget(info_text)
        
        # Button row for settings management
        buttons_layout = QHBoxLayout()
        self.reset_button = QPushButton("Reset to Default Values")
        self.reset_button.clicked.connect(self.reset_advanced_settings)
        self.save_button = QPushButton("💾 Save Settings")
        self.save_button.clicked.connect(self.save_settings)
        buttons_layout.addWidget(self.reset_button)
        buttons_layout.addWidget(self.save_button)
        buttons_layout.addStretch()
        timing_layout.addLayout(buttons_layout)

        # Base delay setting
        base_delay_layout = QHBoxLayout()
        base_delay_label = QLabel("Base Delay (seconds):")
        base_delay_label.setToolTip("Time to wait between each posts downloads")
        base_delay_layout.addWidget(base_delay_label)
        self.base_delay = QDoubleSpinBox()
        self.base_delay.setRange(1, 60)
        self.base_delay.setValue(DEFAULT_BASE_DELAY)
        self.base_delay.setDecimals(1)
        self.base_delay.setSingleStep(0.5)
        base_delay_layout.addWidget(self.base_delay)
        
        # Explanation text for base delay
        base_delay_info = QLabel("The minimum waiting time between downloads to simulate human browsing")
        base_delay_info.setStyleSheet("color: #808080; font-style: italic;")
        base_delay_info.setWordWrap(True)
        
        # Jitter setting
        jitter_layout = QHBoxLayout()
        jitter_label = QLabel("Random Jitter (seconds):")
        jitter_label.setToolTip("Random additional delay to appear as human behavior")
        jitter_layout.addWidget(jitter_label)
        self.jitter = QDoubleSpinBox()
        self.jitter.setRange(0, 20)
        self.jitter.setValue(DEFAULT_JITTER)
        self.jitter.setDecimals(1)
        self.jitter.setSingleStep(0.5)
        jitter_layout.addWidget(self.jitter)
        
        # Explanation text for jitter
        jitter_info = QLabel("Random extra time added to delays to make browsing pattern less predictable")
        jitter_info.setStyleSheet("color: #808080; font-style: italic;")
        jitter_info.setWordWrap(True)

        # Story multiplier setting
        story_layout = QHBoxLayout()
        story_label = QLabel("Story Delay Multiplier:")
        story_label.setToolTip("Extra time caution for story downloads")
        story_layout.addWidget(story_label)
        self.story_multiplier = QDoubleSpinBox()
        self.story_multiplier.setRange(1, 10)
        self.story_multiplier.setValue(DEFAULT_STORY_MULTIPLIER)
        self.story_multiplier.setDecimals(1)
        self.story_multiplier.setSingleStep(0.5)
        story_layout.addWidget(self.story_multiplier)

        # Explanation text for story multiplier
        story_info = QLabel("Multiplies the base delay when downloading stories for added safety")
        story_info.setStyleSheet("color: #808080; font-style: italic;")
        story_info.setWordWrap(True)
        
        # Critical wait setting
        critical_layout = QHBoxLayout()
        critical_label = QLabel("Critical Wait (minutes):")
        critical_label.setToolTip("Timeout duration after errors or temporary ban")
        critical_layout.addWidget(critical_label)
        self.critical_wait = QSpinBox()
        self.critical_wait.setRange(1, 120)
        self.critical_wait.setValue(DEFAULT_CRITICAL_WAIT)
        critical_layout.addWidget(self.critical_wait)

        # Explanation text for critical wait
        critical_info = QLabel("Pause duration after encountering errors or rate limits")
        critical_info.setStyleSheet("color: #808080; font-style: italic;")
        critical_info.setWordWrap(True)
        
        # Long session chance setting
        session_layout = QHBoxLayout()
        session_label = QLabel("Long Session Chance (0-1):")
        session_label.setToolTip("Probability of taking a longer break")
        session_layout.addWidget(session_label)
        self.long_session_chance = QDoubleSpinBox()
        self.long_session_chance.setRange(0, 1)
        self.long_session_chance.setValue(DEFAULT_LONG_SESSION_CHANCE)
        self.long_session_chance.setDecimals(2)
        self.long_session_chance.setSingleStep(0.05)
        session_layout.addWidget(self.long_session_chance)

        # Explanation text for long session chance
        session_info = QLabel("Probability (0-1) that a longer break will be taken between downloads")
        session_info.setStyleSheet("color: #808080; font-style: italic;")
        session_info.setWordWrap(True)
        
        # Request timeout setting
        timeout_layout = QHBoxLayout()
        timeout_label = QLabel("Request Timeout (seconds):")
        timeout_label.setToolTip("Maximum time to wait for server response")
        timeout_layout.addWidget(timeout_label)
        self.request_timeout = QSpinBox()
        self.request_timeout.setRange(30, 600)
        self.request_timeout.setValue(DEFAULT_REQUEST_TIMEOUT)
        self.request_timeout.setSingleStep(30)
        timeout_layout.addWidget(self.request_timeout)

        # Explanation text for request timeout
        timeout_info = QLabel("Maximum time to wait for Instagram server to respond before timing out")
        timeout_info.setStyleSheet("color: #808080; font-style: italic;")
        timeout_info.setWordWrap(True)

        # Add all parameter groups to timing layout
        parameter_layouts = [
            (base_delay_layout, base_delay_info),
            (jitter_layout, jitter_info),
            (story_layout, story_info),
            (session_layout, session_info),
            (timeout_layout, timeout_info),
            (critical_layout, critical_info)  # Moved to the end of the list
        ]
        
        for layout_pair, info_label in parameter_layouts:
            timing_layout.addLayout(layout_pair)
            timing_layout.addWidget(info_label)
            timing_layout.addSpacing(8)  # Spacing between parameter groups
        
        # Add timing group to content layout
        content_layout.addWidget(timing_group)
        content_layout.addStretch()
        
        # Add content widget to main layout
        layout.addWidget(content_widget)

    def setup_about_tab(self, layout):
        """
        Create and configure the about tab content.
        
        Args:
            layout (QVBoxLayout): Layout to add the about content to
        """
        # Create scrollable area for about content
        scroll = QWidget()
        scroll_layout = QVBoxLayout(scroll)
        scroll_layout.setContentsMargins(20, 20, 20, 20)
        scroll_layout.setSpacing(20)

        # App title
        title_label = QLabel(f"{APP_NAME} v{APP_VERSION}")
        title_label.setStyleSheet("font-size: 24px; font-weight: bold;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        scroll_layout.addWidget(title_label)

        # Version info with hyperlink to Instaloader - changed color to white
        version_label = QLabel(f'Using <a href="https://instaloader.github.io/" style="color: white">Instaloader</a> Library v{INSTALOADER_VERSION}')
        version_label.setOpenExternalLinks(True)
        version_label.setStyleSheet("font-size: 14px; color: #808080;")
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        scroll_layout.addWidget(version_label)

        # Moved app description right after the version info
        desc_text = QLabel(
            "A desktop application that provides a user-friendly "
            "graphical user interface for downloading contents "
            "from Instagram profiles using the Instaloader Python library."
        )
        desc_text.setWordWrap(True)
        desc_text.setStyleSheet("font-size: 14px;")
        desc_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        scroll_layout.addWidget(desc_text)

        # Developer info
        dev_label = QLabel('Developed by <a href="https://github.com/marhensa/" style="color: white">@marhensa</a>')
        dev_label.setOpenExternalLinks(True)
        dev_label.setStyleSheet("font-size: 16px; color: #4CAF50;")
        dev_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dev_label.setWordWrap(True)
        scroll_layout.addWidget(dev_label)

        # GitHub link
        github_label = QLabel('<a href="https://github.com/marhensa/instaloader-gui-wrapper" style="color: #2196F3;">GitHub Repository</a>')
        github_label.setOpenExternalLinks(True)
        github_label.setStyleSheet("font-size: 14px;")
        github_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        scroll_layout.addWidget(github_label)
        
        # Donation info
        donation_label = QLabel('If you find this tool useful, please consider supporting development: <a href="https://ko-fi.com/marhensa" style="color: white">Ko-fi @marhensa</a>')
        donation_label.setOpenExternalLinks(True)
        donation_label.setStyleSheet("font-size: 14px; color: #FFB74D;")
        donation_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        donation_label.setWordWrap(True)
        scroll_layout.addWidget(donation_label)

        # Separator line
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        scroll_layout.addWidget(line)

        # Disclaimer text
        disclaimer_text = QLabel(
            "DISCLAIMER: This tool is for personal use only. Respect Instagram's terms of "
            "service and copyright rules. The developer are not responsible "
            "for misuse of this application.\n\n"
            "• Your Instagram credentials can be saved into Session files\n"
            "• which are more secure than entering credentials each time,\n"
            "• but make sure delete those files if using this app in public PC!\n\n"
            "• WARNING! Excessive downloads may trigger Instagram's rate limiting / temporary ban.\n"
            "• Use at your own risk. The developer are not responsible for any consequences.\n"
            "• This tool is not affiliated with Instagram or Facebook.\n"
        )
        disclaimer_text.setWordWrap(True)
        disclaimer_text.setStyleSheet("font-size: 14px;")
        disclaimer_text.setAlignment(Qt.AlignmentFlag.AlignLeft)
        scroll_layout.addWidget(disclaimer_text)

        # Add stretch to keep content at top
        scroll_layout.addStretch()

        layout.addWidget(scroll)

    def setup_progress_bars(self, layout):
        """
        Create and configure the progress bars for download tracking.
        
        Args:
            layout (QVBoxLayout): Layout to add the progress bars to
        """
        self.overall_progress = QProgressBar()
        self.current_progress = QProgressBar()
        
        for bar in (self.overall_progress, self.current_progress):
            bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            bar.setMinimumWidth(200)
            bar.setFixedHeight(20)
        
        layout.addWidget(QLabel("Overall Progress:"))
        layout.addWidget(self.overall_progress)
        layout.addWidget(QLabel("Current Item Progress:"))
        layout.addWidget(self.current_progress)

    def apply_styles(self):
        """
        Apply custom styles to the application UI.
        
        With qdarktheme applied globally, we only need minimal custom styling
        for specific components.
        """
        custom_style = """
            QGroupBox {
                padding-top: 12px;  /* Reduced from default ~24px */
                margin-top: 5px;    /* Reduced from default ~10px */
            }
            QPushButton#start_button,
            QPushButton#stop_button {
                background-color: #0D47A1;
                color: #FFFFFF;
                font-weight: bold;
                padding: 8px 20px;
                font-size: 14px;
                min-width: 150px;
            }
            QPushButton#stop_button {
                background-color: #C62828;
            }
            QPushButton#start_button:disabled,
            QPushButton#stop_button:disabled {
                background-color: #424242;
                color: #9E9E9E;
            }
            QToolTip {
                background-color: #2B2B2B;
                color: #E0E0E0;
                border: 1px solid #3E3E3E;
                padding: 4px;
                font-size: 12px;
            }
        """
        
        self.setStyleSheet(custom_style)
        
        # Set object name for the start button to apply specific styling
        self.start_button.setObjectName("start_button")

    def reset_advanced_settings(self):
        """
        Reset advanced settings to their default values.
        
        Resets all timing and delay settings to their predefined defaults and saves the settings.
        """
        self.base_delay.setValue(DEFAULT_BASE_DELAY)
        self.jitter.setValue(DEFAULT_JITTER)
        self.story_multiplier.setValue(DEFAULT_STORY_MULTIPLIER)
        self.critical_wait.setValue(DEFAULT_CRITICAL_WAIT)
        self.long_session_chance.setValue(DEFAULT_LONG_SESSION_CHANCE)
        self.request_timeout.setValue(DEFAULT_REQUEST_TIMEOUT)
        self.log_message("Advanced settings reset to default values", "INFO")
        self.save_settings()

    def toggle_credentials(self, state):
        """
        Toggle the enabled state of credential input fields based on session file usage.
        
        When using session files, username/password fields are disabled and cleared.
        When using direct login, session file path is cleared.
        
        Args:
            state (int): The state of the use_session checkbox
                         Qt.Checked (2) indicates session file usage
                         Qt.Unchecked (0) indicates direct credential usage
        """
        enabled = not bool(state)
        self.username.setEnabled(enabled)
        self.password.setEnabled(enabled)
        
        # Save session checkbox should be disabled when using session file
        self.save_session.setEnabled(enabled)
        
        if state:
            self.username.setText("")
            self.password.setText("")
            self.save_session.setChecked(False)  # Uncheck save_session when using session file
        else:
            self.session_path.setText("")
            self.save_session.setChecked(True)  # Re-check save_session when using credentials

    def select_session_file(self):
        """
        Open a file dialog to select a session file.
        
        Tries to determine the default session directory based on the operating system.
        """
        import os
        
        # Try to determine default session directory
        if os.name == 'nt':  # Windows
            default_dir = os.path.join(os.getenv('LOCALAPPDATA', ''), 'Instaloader')
        else:  # Linux/Mac
            default_dir = os.path.expanduser('~/.config/instaloader')
        
        if not os.path.exists(default_dir):
            default_dir = ""
            
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Session File",
            default_dir,
            "All Files (*)")  # Cross-platform filter for all files
            
        if file_path:
            self.session_path.setText(os.path.normpath(file_path))
            self.use_session.setChecked(True)  # Automatically check the "Use Session File" checkbox

    def select_directory(self):
        """
        Open a directory selection dialog to choose the download location.
        
        Uses APP_ROOT as the starting directory to direct to the app location.
        """
        dir_path = QFileDialog.getExistingDirectory(self, "Select Download Directory", APP_ROOT)
        if dir_path:
            self.dir_path.setText(os.path.normpath(dir_path))

    def toggle_date_range(self, state):
        """
        Toggle the enabled state of the date range input fields.
        
        Args:
            state (int): The state of the ignore_date_range checkbox (checked/unchecked)
        """
        self.date_widget.setEnabled(not bool(state))

    def handle_only_stories(self, state):
        """
        Handle the state change of the only_stories checkbox.
        
        Disables conflicting options and ensures appropriate settings for story downloads.
        
        Args:
            state (int): The state of the only_stories checkbox (checked/unchecked)
        """
        if self.only_stories.isChecked():
            self.download_highlights.setChecked(False)
            self.download_highlights.setEnabled(False)
            self.profile_pic_only.setChecked(False)
            self.only_highlights.setChecked(False)
            self.only_highlights.setEnabled(False)
            self.download_stories.setChecked(True)
            self.download_stories.setEnabled(False)
            # Stories are always current (24h max), so date range must be ignored
            self.ignore_date_range.setChecked(True)
            self.ignore_date_range.setEnabled(False)
        else:
            self.download_highlights.setEnabled(True)
            self.download_stories.setEnabled(True)
            self.only_highlights.setEnabled(True)
            self.ignore_date_range.setEnabled(True)

    def handle_only_highlights(self, state):
        """
        Handle the state change of the only_highlights checkbox.
        
        Disables conflicting options and ensures appropriate settings for highlight downloads.
        
        Args:
            state (int): The state of the only_highlights checkbox (checked/unchecked)
        """
        if self.only_highlights.isChecked():
            self.download_stories.setChecked(False)
            self.download_stories.setEnabled(False)
            self.profile_pic_only.setChecked(False)
            self.only_stories.setChecked(False)
            self.only_stories.setEnabled(False)
            self.download_highlights.setChecked(True)
            self.download_highlights.setEnabled(False)
        else:
            self.download_stories.setEnabled(True)
            self.download_highlights.setEnabled(True)
            self.only_stories.setEnabled(True)
            self.ignore_date_range.setEnabled(True)

    def handle_profile_pic_only(self, state):
        """
        Handle the state change of the profile_pic_only checkbox.
        
        Disables conflicting options and ensures appropriate settings for profile picture downloads.
        
        Args:
            state (int): The state of the profile_pic_only checkbox (checked/unchecked)
        """
        checkboxes = [
            self.download_highlights,
            self.download_stories,
            self.only_stories,
            self.only_highlights,
            self.ignore_date_range
        ]
        if self.profile_pic_only.isChecked():
            for checkbox in checkboxes:
                # Don't uncheck ignore_date_range, we need to handle it separately
                if checkbox != self.ignore_date_range:
                    checkbox.setChecked(False)
                checkbox.setEnabled(False)
            
            # Profile pics are always current, so date range must be ignored
            self.ignore_date_range.setChecked(True)
            self.date_widget.setEnabled(False)
        else:
            for checkbox in checkboxes:
                checkbox.setEnabled(True)
            self.toggle_date_range(self.ignore_date_range.isChecked())

    def save_settings(self):
        """
        Save the current advanced settings to the configuration file.
        
        Only saves the advanced settings related to timing and delays.
        """
        config = {
            'base_delay': self.base_delay.value(),
            'jitter': self.jitter.value(),
            'story_multiplier': self.story_multiplier.value(),
            'critical_wait': self.critical_wait.value(),
            'long_session_chance': self.long_session_chance.value(),
            'request_timeout': self.request_timeout.value(),
        }
        
        success, message = Settings.save_settings(config)
        self.log_message(message, "INFO" if success else "ERROR")

    def load_settings(self):
        """
        Load the saved settings from the configuration file.
        
        Loads only the advanced settings related to timing and delays.
        """
        settings, message = Settings.load_settings()
        if settings:
            self.base_delay.setValue(settings.get('base_delay', DEFAULT_BASE_DELAY))
            self.jitter.setValue(settings.get('jitter', DEFAULT_JITTER))
            self.story_multiplier.setValue(settings.get('story_multiplier', DEFAULT_STORY_MULTIPLIER))
            self.critical_wait.setValue(settings.get('critical_wait', DEFAULT_CRITICAL_WAIT))
            self.long_session_chance.setValue(settings.get('long_session_chance', DEFAULT_LONG_SESSION_CHANCE))
            self.request_timeout.setValue(settings.get('request_timeout', DEFAULT_REQUEST_TIMEOUT))
        
        self.log_message(message, "INFO")
        
        # Always set default dates
        self.since_date.setDate(QDate.currentDate().addYears(-1))
        self.until_date.setDate(QDate.currentDate())

    def reset_progress_bars(self):
        """
        Reset both progress bars to 0.
        
        Resets the overall and current item progress bars to their initial state.
        """
        self.overall_progress.setValue(0)
        self.current_progress.setValue(0)
        self.logger.info("Progress bars reset")

    def toggle_start_pause(self):
        """Toggle between Start and Pause states with improved state handling"""
        try:
            if not self.is_downloading:
                # Start new download
                config = self.get_config()
                if not self.validate_config(config):
                    return
                    
                self.save_settings()
                self.single_post_profile = None
                self.reset_progress_bars()
                
                self.downloader_thread = DownloaderThread(config)
                
                # Connect signals
                self.downloader_thread.log_signal.connect(self.log_message)
                self.downloader_thread.progress_signal.connect(self.update_progress)
                self.downloader_thread.finished.connect(self.download_finished)
                self.downloader_thread.file_downloaded_signal.connect(self.update_preview)
                self.downloader_thread.stopped_signal.connect(self.download_stopped)
                self.downloader_thread.state_changed_signal.connect(self.handle_state_change)
                self.downloader_thread.two_factor_required_signal.connect(self.handle_two_factor)
                self.two_factor_signal.connect(self.downloader_thread.set_two_factor_code)
                
                # Update UI state
                self.start_button.setText("⏸ Pause")
                self.stop_button.setEnabled(True)
                self.is_downloading = True
                self.downloader_thread.start()
                
            elif self.downloader_thread:
                # Toggle pause/resume
                if self.downloader_thread.is_paused:
                    if self.downloader_thread.resume():
                        self.start_button.setText("⏸ Pause")
                    else:
                        self.log_message("Failed to resume download", "ERROR")
                else:
                    if self.downloader_thread.pause():
                        self.start_button.setText("▶ Resume")
                    else:
                        self.log_message("Failed to pause download", "ERROR")

        except Exception as e:
            self.logger.error(f"Error in toggle_start_pause: {str(e)}")
            self.log_message(f"Error controlling download: {str(e)}", "ERROR")
            self.reset_ui_state()

    def handle_state_change(self, state, details):
        """Handle download state changes with improved error handling"""
        try:
            if state == 'paused':
                self.start_button.setText("▶ Resume")
            elif state == 'resumed':
                self.start_button.setText("⏸ Pause")
            elif state in ['stopped', 'completed', 'error']:
                self.reset_ui_state()
                self.is_downloading = False
                
            if state == 'error':
                self.log_message(f"Download error: {details}", "ERROR")
                
        except Exception as e:
            self.logger.error(f"Error handling state change: {str(e)}")
            self.reset_ui_state()

    def download_finished(self):
        """
        Handle the completion of the download process.
        """
        if self.is_downloading:
            self.is_downloading = False
            self.reset_ui_state()
            self.log_message("Download process completed!", "INFO")

    def validate_config(self, config):
        """
        Validate the current configuration before starting the download.
        
        Ensures all required fields are filled and URLs are in the correct format.
        Also validates that the From date is not more recent than the To date.
        
        Args:
            config (dict): The current configuration dictionary
            
        Returns:
            bool: True if the configuration is valid, False otherwise
        """
        is_single_post = self.download_single_post.isChecked()
        
        # Check date range validity if date filtering is enabled
        if not self.ignore_date_range.isChecked():
            since_date = self.since_date.date()
            until_date = self.until_date.date()
            if since_date > until_date:
                self.log_message("Invalid date range: 'From' date cannot be more recent than 'To' date!", "ERROR")
                return False
        
        if is_single_post:
            if not config['post_url']:
                self.log_message("Post URL is required for single post download!", "ERROR")
                return False
                
            # Updated URL patterns to handle all variations including username in path
            valid_url = False
            url = config['post_url']
            
            # Compiled patterns for better performance and readability
            instagram_patterns = {
                # Posts - both with and without username
                'post': r'https?://(www\.)?instagram\.com/(?:[^/]+/)?p/[\w-]+/?',
                
                # Reels - both with and without username
                'reel': r'https?://(www\.)?instagram\.com/(?:[^/]+/)?reel/[\w-]+/?',
                
                # Stories - requires username
                'story': r'https?://(www\.)?instagram\.com/stories/[^/]+/[\w-]+/?',
                
                # Highlights - both with and without username
                'highlight': r'https?://(www\.)?instagram\.com/(?:[^/]+/)?stories/highlights/[\w-]+/?'
            }
            
            import re
            for pattern_type, pattern in instagram_patterns.items():
                if re.match(pattern, url):
                    valid_url = True
                    self.logger.info(f"URL matched {pattern_type} pattern")
                    break
                    
            if not valid_url:
                self.log_message(
                    "Invalid Instagram URL format. URL must be in one of these formats:\n"
                    "• Posts: instagram.com/[username]/p/postid\n"
                    "• Reels: instagram.com/[username]/reel/reelid\n"
                    "• Stories: instagram.com/stories/username/storyid\n"
                    "• Highlights: instagram.com/[username]/stories/highlights/highlightid", 
                    "ERROR"
                )
                return False
        else:
            # Only check for target profile when not in single post mode
            if not config['target_profile']:
                self.log_message("Target profile name is required!", "ERROR")
                return False

        # Common validations
        if not config['download_dir']:
            self.log_message("Please select a download directory!", "ERROR")
            return False
            
        if not config['use_session'] and (not config['username'] or not config['password']):
            self.log_message("Please enter your username and password or use a session file!", "ERROR")
            return False
            
        if config['use_session'] and not config['session_path']:
            self.log_message("Please select a session file!", "ERROR")
            return False
            
        return True

    def update_progress(self, current, total, progress_type='overall'):
        """
        Update the progress bars based on the current progress.
        
        Args:
            current (int): The current progress value
            total (int): The total progress value
            progress_type (str): The type of progress ('overall' or 'current')
        """
        if progress_type == 'overall':
            self.overall_progress.setValue(int(current/total * 100) if total > 0 else 0)
        else:
            self.current_progress.setValue(int(current/total * 100) if total > 0 else 0)

    def log_message(self, message, level='INFO'):
        """
        Log a message to the UI and the log file.
        
        Args:
            message (str): The message to log
            level (str): The log level ('INFO', 'WARNING', 'ERROR')
        """
        self.log_viewer.append_log(message, level)
        
        # Log to file using the proper logger
        log_method = getattr(self.logger, level.lower(), None)
        if log_method:
            log_method(message)

    def update_preview(self, file_path):
        """Update preview with downloaded file."""
        try:
            # Skip if file doesn't exist or empty
            if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
                return
                
            # Check file type
            ext = os.path.splitext(file_path)[1].lower()
            base_path = os.path.splitext(file_path)[0]
            
            preview_path = file_path
            if ext == '.mp4':
                # Try to find thumbnail for video
                thumbnail_path = base_path + '.jpg'
                if os.path.exists(thumbnail_path):
                    preview_path = thumbnail_path
                else:
                    self.show_video_placeholder(file_path)
                    return
            elif ext not in ['.jpg', '.jpeg', '.png', '.webp']:
                return
                
            # Load and scale image
            pixmap = QPixmap(preview_path)
            if pixmap.isNull():
                return
                
            # Scale image to fit preview area
            label_size = self.preview_label.size()
            scaled_pixmap = self.scale_image(pixmap, label_size)
            
            # Update UI
            self.preview_label.setPixmap(scaled_pixmap)
            self.last_download_path = file_path
            
            # Show file information including JSON metadata
            self.show_media_info(file_path)
            
        except Exception as e:
            self.logger.error(f"Error updating preview: {str(e)}")

    def scale_image(self, pixmap, target_size):
        """
        Scale an image while maintaining aspect ratio and quality.
        
        Args:
            pixmap (QPixmap): The image to scale
            target_size (QSize): The target size
            
        Returns:
            QPixmap: The scaled image
        """
        # Get dimensions
        img_width = pixmap.width()
        img_height = pixmap.height()
        target_width = target_size.width()
        target_height = target_size.height()
        
        # Calculate scaling factors
        width_ratio = target_width / img_width
        height_ratio = target_height / img_height
        
        # Use the smaller ratio to fit within the preview area
        scale_factor = min(width_ratio, height_ratio)
        
        # Calculate new dimensions
        new_width = int(img_width * scale_factor)
        new_height = int(img_height * scale_factor)
        
        # Scale with high quality
        return pixmap.scaled(
            new_width, 
            new_height,
            Qt.AspectRatioMode.KeepAspectRatio, 
            Qt.TransformationMode.SmoothTransformation
        )

    def show_video_placeholder(self, video_path):
        """
        Show video thumbnail or placeholder.
        
        Args:
            video_path (str): Path to the video file
        """
        base_path = os.path.splitext(video_path)[0]
        thumbnail_path = base_path + '.jpg'
        
        if os.path.exists(thumbnail_path):
            # Use thumbnail if available
            pixmap = QPixmap(thumbnail_path)
            if not pixmap.isNull():
                label_size = self.preview_label.size()
                scaled_pixmap = self.scale_image(pixmap, label_size)
                self.preview_label.setPixmap(scaled_pixmap)
                self.preview_label.setStyleSheet("")  # Clear any placeholder styling
                self.show_media_info(video_path)
                return
        
        # Fallback to placeholder if no thumbnail
        self.preview_label.setText("📹 Video File\nPreview not available")
        self.preview_label.setStyleSheet("""
            QLabel {
                background-color: #2B2B2B;
                border: 1px solid #3E3E3E;
                padding: 20px;
                font-size: 14px;
                qproperty-alignment: AlignCenter;
            }
        """)
        self.show_media_info(video_path)

    def show_media_info(self, file_path):
        """
        Show information about the media file in the preview panel.
        
        Args:
            file_path (str): Path to the media file
        """
        import os
        from datetime import datetime
        import re
        
        # Determine content type based on path
        content_type = "Unknown"
        if "/stories/" in file_path.replace("\\", "/"):
            content_type = "Story"
        elif "/posts/" in file_path.replace("\\", "/"):
            content_type = "Post"
        elif "/profile_pic/" in file_path.replace("\\", "/"):
            content_type = "Profile Picture"
        elif "/highlights/" in file_path.replace("\\", "/"):
            content_type = "Highlight"
            
        # Get highlight name if applicable
        highlight_name = ""
        if content_type == "Highlight":
            path_parts = file_path.replace("\\", "/").split("/")
            try:
                highlight_index = path_parts.index("highlights")
                if highlight_index + 1 < len(path_parts):
                    highlight_name = f" ({path_parts[highlight_index+1]})"
            except ValueError:
                pass
            
        info_text = f"Content Type: {content_type}{highlight_name}\n\n"
        
        # Read caption from companion .txt file
        txt_path = os.path.splitext(file_path)[0] + ".txt"
        if os.path.exists(txt_path):
            try:
                with open(txt_path, 'r', encoding='utf-8') as f:
                    caption = f.read().strip()
                    if caption:
                        info_text += f"Caption:\n{caption}\n\n"
            except Exception as e:
                self.logger.warning(f"Error reading caption from txt: {str(e)}")
        
        # Extract date from filename (format: YYYY-MM-DD_HH-MM-SS_UTC)
        filename = os.path.basename(file_path)
        date_pattern = r'(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})_UTC'
        match = re.search(date_pattern, filename)
        if match:
            date_str = match.group(1)
            try:
                post_date = datetime.strptime(date_str, '%Y-%m-%d_%H-%M-%S')
                info_text += f"Post Date: {post_date.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            except ValueError:
                pass
        
        # Add file creation time (download time)
        try:
            creation_time = datetime.fromtimestamp(os.path.getctime(file_path))
            info_text += f"Downloaded: {creation_time.strftime('%Y-%m-%d %H:%M:%S')}"
        except Exception as e:
            self.logger.warning(f"Error getting file information: {str(e)}")
        
        # Display in the info text area
        self.image_info.setText(info_text)

    def get_config(self):
        """
        Get the current configuration from the UI components.
        
        Returns:
            dict: The current configuration dictionary
        """
        config = {
            'use_session': self.use_session.isChecked(),
            'session_path': self.session_path.text(),
            'username': self.username.text(),
            'password': self.password.text(),
            'save_session': self.save_session.isChecked(),
            'target_profile': self.target_profile.text(),
            'download_dir': self.dir_path.text(),
            'download_highlights': self.download_highlights.isChecked(),
            'download_stories': self.download_stories.isChecked(),
            'only_stories': self.only_stories.isChecked(),
            'only_highlights': self.only_highlights.isChecked(),
            'profile_pic_only': self.profile_pic_only.isChecked(),
            'ignore_date_range': self.ignore_date_range.isChecked(),
            'since_date': self.since_date.date().toPyDate(),
            'until_date': self.until_date.date().toPyDate(),
            'base_delay': self.base_delay.value(),
            'jitter': self.jitter.value(),
            'story_multiplier': self.story_multiplier.value(),
            'critical_wait': self.critical_wait.value() * 60,  # Convert to seconds
            'long_session_chance': self.long_session_chance.value(),
            'skip_existing': self.skip_existing.isChecked(),
            'request_timeout': self.request_timeout.value(),
            # Add new fields for single post download
            'download_single_post': self.download_single_post.isChecked(),
            'post_url': self.post_url.text().strip(),
            # Add post limit options
            'limit_posts': self.limit_posts.isChecked(),
            'max_posts': self.max_posts.value() if self.limit_posts.isChecked() else 0,
        }
        
        # Extract post ID if we're in single post mode
        if config['download_single_post'] and config['post_url']:
            config['post_id'] = self.extract_post_id(config['post_url'])
            
        return config
        
    def extract_post_id(self, url):
        """
        Extract post ID from Instagram URL for different content types.
        
        Parses URLs for posts, reels, stories, and highlights to extract
        the unique identifier needed for downloading.
        
        Args:
            url (str): Instagram content URL
            
        Returns:
            str: Extracted post ID or URL on failure
        """
        import re
        
        # Extract post ID using regex for different URL formats
        # Updated to handle URLs with and without username in path
        post_match = re.search(r'instagram\.com/(?:[^/]+/)?p/([\w-]+)', url)
        if post_match:
            return post_match.group(1)
            
        reel_match = re.search(r'instagram\.com/(?:[^/]+/)?reel/([\w-]+)', url)
        if reel_match:
            return reel_match.group(1)
            
        stories_match = re.search(r'instagram\.com/stories/([^/]+)/([\w-]+)', url)
        if stories_match:
            # For stories, combine username and story ID
            return f"{stories_match.group(1)}_{stories_match.group(2)}"
            
        highlights_match = re.search(r'instagram\.com/(?:[^/]+/)?stories/highlights/([\w-]+)', url)
        if highlights_match:
            return highlights_match.group(1)
            
        # Default fallback - return URL as is
        return url

    def closeEvent(self, event):
        """
        Handle the application close event.
        
        Ensures any running threads are properly terminated and settings are saved.
        
        Args:
            event (QCloseEvent): The close event
        """
        self.logger.info("Application shutdown requested")
        
        # Cleanup profile check thread if running
        if self.profile_check_thread and self.profile_check_thread.isRunning():
            self.logger.info("Waiting for profile check thread to finish...")
            self.profile_check_thread.wait()
            self.profile_check_thread = None
            
        if self.is_downloading:
            reply = QMessageBox.question(
                self, 'Confirm Exit',
                'A download is in progress. Are you sure you want to quit?',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.No:
                self.logger.info("Shutdown cancelled - download in progress")
                event.ignore()
                return
                
        if self.downloader_thread and self.downloader_thread.isRunning():
            self.logger.info("Stopping download thread before shutdown...")
            self.log_message("Stopping download thread before shutdown...", "INFO")
            
            # Set the flag to indicate we're stopping
            if hasattr(self.downloader_thread, 'is_running'):
                self.downloader_thread.is_running = False
                self.downloader_thread.is_stopped = True
            
            # Call quit and wait with a timeout
            self.downloader_thread.quit()
            if not self.downloader_thread.wait(3000):  # Wait up to 3 seconds
                self.logger.warning("Download thread did not stop gracefully, terminating...")
                self.downloader_thread.terminate()  # Force termination as a last resort
        
        # Save settings before closing
        self.save_settings()
        self.logger.info("Settings saved, application shutting down")
        event.accept()

    def handle_two_factor(self):
        """
        Handle the 2FA request from the downloader thread.
        
        Emits a signal to create and show the 2FA dialog in the main thread.
        """
        self.logger.info("Received two_factor_required_signal")
        
        # Emit signal to create and show dialog in main thread
        self.two_factor_prompt.emit()
    
    def create_two_factor_dialog(self):
        """
        Create and show the 2FA dialog in the main thread.
        
        This dialog is displayed when Instagram requires two-factor authentication
        during the login process. It allows the user to enter their 6-digit verification
        code from an authentication app or SMS.
        
        The dialog includes:
        - An informational label explaining the 2FA requirement
        - A specialized input field for the 6-digit code 
        - Submit and Cancel buttons
        
        Note:
            This method runs in the main thread as it creates UI components.
            The dialog is non-modal, allowing the user to interact with it
            while the background thread waits for the code.
        """
        self.logger.info("Creating 2FA dialog in main thread")
        
        # Create dialog and all UI components
        dialog = QDialog(self)
        dialog.setWindowTitle("Two-Factor Authentication Required")
        dialog.setMinimumWidth(400)
        # No longer need to set custom stylesheet as qdarktheme applies globally
        # dialog.setStyleSheet(get_dark_style())
        dialog.setModal(True)
        
        layout = QVBoxLayout(dialog)
        
        info_label = QLabel(
            "Instagram requires a verification code to complete login.\n\n"
            "Please enter the 6-digit code from your:\n"
            "• Authentication app (like Google Authenticator)\n"
            "• SMS messages on your registered phone"
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # Store reference to the input field
        self.two_factor_input = QLineEdit()
        self.two_factor_input.setPlaceholderText("Enter 6-digit verification code")
        self.two_factor_input.setMaxLength(6)
        self.two_factor_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.two_factor_input.setMinimumHeight(36)
        self.two_factor_input.setFont(QFont("Arial", 14))
        
        # Create validator directly
        validator = QIntValidator(0, 999999)
        self.two_factor_input.setValidator(validator)
        layout.addWidget(self.two_factor_input)
        
        button_layout = QHBoxLayout()
        submit_button = QPushButton("Submit Code")
        submit_button.setDefault(True)
        submit_button.setMinimumHeight(36)
        cancel_button = QPushButton("Cancel")
        cancel_button.setMinimumHeight(36)
        button_layout.addWidget(submit_button)
        button_layout.addWidget(cancel_button)
        layout.addLayout(button_layout)
        
        # Connect handlers
        submit_button.clicked.connect(self.submit_two_factor_code)
        cancel_button.clicked.connect(self.cancel_two_factor)
        self.two_factor_input.returnPressed.connect(self.submit_two_factor_code)
        
        # Store reference to the dialog
        self.two_factor_dialog = dialog
        
        # Focus and show
        self.two_factor_input.setFocus()
        dialog.show()
    
    def submit_two_factor_code(self):
        """
        Submit the 2FA code entered by the user.
        
        This method:
        1. Retrieves the entered verification code from the input field
        2. Emits the code via signal to the downloader thread
        3. Closes the dialog
        
        If the input field is empty, a warning is logged but no code is emitted.
        """
        if self.two_factor_input and self.two_factor_dialog:
            code = self.two_factor_input.text().strip()
            if code:
                self.logger.info("2FA code submitted")
                self.two_factor_signal.emit(code)
                self.two_factor_dialog.accept()
            else:
                self.logger.warning("No 2FA code entered")
        
    def cancel_two_factor(self):
        """
        Cancel the 2FA process.
        
        Emits an empty 2FA code signal and closes the dialog.
        """
        self.logger.warning("2FA canceled by user")
        self.two_factor_signal.emit("")
        if self.two_factor_dialog:
            self.two_factor_dialog.reject()

    def toggle_single_post(self, state):
        """
        Handle toggling between profile and single post download mode.
        
        Args:
            state (int): The state of the download_single_post checkbox (checked/unchecked)
        """
        is_single_post = self.download_single_post.isChecked()
        
        # Enable/disable appropriate fields
        self.post_url.setEnabled(is_single_post)
        self.target_profile.setEnabled(not is_single_post)
        
        if is_single_post:
            self.target_profile.setText("")
            # Force ignore date range to be checked and disabled
            self.ignore_date_range.setChecked(True)
            self.ignore_date_range.setEnabled(False)
            self.date_widget.setEnabled(False)
        else:
            self.post_url.setText("")
            # Re-enable date range controls
            self.ignore_date_range.setEnabled(True)
            self.date_widget.setEnabled(not self.ignore_date_range.isChecked())
        
        # Disable most download options when in single post mode
        download_option_checkboxes = [
            self.download_highlights,
            self.download_stories, 
            self.only_highlights,
            self.only_stories,
            self.profile_pic_only,
            self.limit_posts
        ]
        
        for checkbox in download_option_checkboxes:
            if is_single_post:
                checkbox.setChecked(False)
                checkbox.setEnabled(False)
            else:
                checkbox.setEnabled(True)
        
        # Also disable the max_posts spinner in single post mode
        self.max_posts.setEnabled(False if is_single_post else self.limit_posts.isChecked())

    def check_profile_name(self):
        """
        Check if the target profile exists and display the profile name.
        
        Initiates a background thread to check the profile name and updates the UI with the result.
        """
        username = self.target_profile.text().strip()
        if not username:
            self.profile_name_display.setText("Please enter a username")
            self.profile_name_display.setStyleSheet("color: #FF5252;")  # Red text
            return
            
        # Show checking indicator
        self.profile_name_display.setText("Checking...")
        self.profile_name_display.setStyleSheet("color: #E0E0E0;")  # Default text color
        self.check_name_button.setEnabled(False)
        QApplication.processEvents()  # Make sure UI updates
        
        # Clean up existing thread if any
        if self.profile_check_thread is not None and self.profile_check_thread.isRunning():
            self.profile_check_thread.wait()
            self.profile_check_thread.deleteLater()
        
        # Create new thread
        self.profile_check_thread = ProfileCheckThread(username)
        self.profile_check_thread.result_signal.connect(self.display_profile_result)
        self.profile_check_thread.finished.connect(self.profile_check_finished)
        self.profile_check_thread.start()

    def profile_check_finished(self):
        """
        Clean up thread resources after profile check is complete.
        """
        if self.profile_check_thread is not None:
            self.profile_check_thread.deleteLater()
            self.profile_check_thread = None

    def display_profile_result(self, success, result):
        """
        Display the result of the profile check.
        
        Args:
            success (bool): Whether the profile check was successful
            result (str): The result message to display
        """
        self.check_name_button.setEnabled(True)
        
        if success:
            self.profile_name_display.setText(f"✓ {result}")
            self.profile_name_display.setStyleSheet("color: #4CAF50;")  # Green text
            self.log_message(f"Profile found: {self.target_profile.text().strip()} ({result})", "INFO")
        else:
            self.profile_name_display.setText(f"✗ {result}")
            self.profile_name_display.setStyleSheet("color: #FF5252;")  # Red text
            self.log_message(f"Profile check failed: {result}", "ERROR")

    def set_session_file(self, session_path):
        """
        Set the session file path and check the use session checkbox after successful login.
        
        Args:
            session_path (str): The path to the session file
        """
        self.logger.info(f"Automatically setting up session file: {session_path}")
        if os.path.exists(session_path):
            self.session_path.setText(os.path.normpath(session_path))
            self.use_session.setChecked(True)
            self.log_message("Session file has been set for next download. "
                            "You won't need to enter login credentials again.", "INFO")

    def toggle_post_limit(self, state):
        """
        Toggle the enabled state of the max posts input field.
        
        Args:
            state (int): The state of the limit_posts checkbox (checked/unchecked)
        """
        self.max_posts.setEnabled(bool(state))
        
    def stop_download(self):
        if not self.downloader_thread:
            return
            
        reply = QMessageBox.question(
            self, 'Confirm Stop',
            'Are you sure you want to stop the download?',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.downloader_thread.stop()
            self.reset_ui_state()
            
    def reset_ui_state(self):
        """Reset UI elements to their initial state"""
        self.start_button.setEnabled(True)
        self.start_button.setText("▶ Start")
        self.stop_button.setEnabled(False)

    def download_stopped(self):
        """Handle download being manually stopped by user"""
        self.is_downloading = False
        self.reset_ui_state()
        self.logger.info("Download stopped by user!")
        self.log_message("Download stopped by user", "WARNING")
        # Don't reset progress bars completely to show how far we got
