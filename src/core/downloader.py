"""
Instaloader GUI Wrapper - Download Core
======================================

This module provides the core functionality for downloading Instagram content through
a multi-threaded approach using PyQt5's QThread. It handles various types of Instagram
content including profiles, posts, stories, highlights, and reels.

The module implements sophisticated anti-detection mechanisms to avoid Instagram's
rate limiting, and provides detailed progress reporting through Qt signals.

Key Features:
- Threaded downloads with progress reporting
- Two-factor authentication support
- Anti-detection timing system
- Session management
- Comprehensive error handling
- Support for various content types:
  * Complete profiles
  * Individual posts
  * Stories and highlights
  * Reels
  * Profile pictures

Classes:
    DownloaderThread: Main worker thread for downloading Instagram content
    ProfileCheckThread: Thread for verifying Instagram profile existence

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

from datetime import datetime
from itertools import dropwhile, takewhile
import time
import random
import logging
import os
import re
import traceback
from PyQt5.QtCore import QThread, pyqtSignal, QEventLoop, QTimer, Qt
import instaloader
from .logger import get_logger, GUILogHandler
import glob
import threading

class DownloaderThread(QThread):
    """
    Main worker thread for downloading Instagram content.
    
    This class handles all download operations in a separate thread to prevent UI blocking.
    It implements sophisticated anti-detection mechanisms and provides detailed progress
    reporting through Qt signals.

    Signals:
        log_signal (str, str): Emits (message, level) for logging
        progress_signal (int, int, str): Emits (current, total, type) for progress updates
        finished: Emits when download completes
        two_factor_required_signal: Emits when 2FA is needed
        session_saved_signal (str): Emits path when session is saved
        file_downloaded_signal (str): Emits path when a file is downloaded
        stopped_signal: Emits when download is manually stopped
        state_changed_signal (str, str): Emits (state, details) for state changes

    Attributes:
        BASE_DELAY (float): Base delay between requests
        JITTER (float): Random delay variation
        STORY_MULTIPLIER (float): Delay multiplier for stories
        CRITICAL_WAIT (int): Delay after critical errors
        LONG_SESSION_CHANCE (float): Probability of taking longer breaks
    """
    log_signal = pyqtSignal(str, str)
    progress_signal = pyqtSignal(int, int, str)
    finished = pyqtSignal()
    two_factor_required_signal = pyqtSignal()  # Signal to request 2FA code
    session_saved_signal = pyqtSignal(str)  # New signal to notify when session is saved
    file_downloaded_signal = pyqtSignal(str)  # New signal for downloaded files
    stopped_signal = pyqtSignal()  # New signal for when download is manually stopped
    state_changed_signal = pyqtSignal(str, str)  # state, details
    
    def __init__(self, config):
        """
        Initialize the downloader thread with configuration settings.
        
        Sets up the thread with the user-provided configuration parameters
        and initializes the anti-detection timing system.
        
        Args:
            config (dict): Dictionary containing user configuration settings including
                           authentication details, download targets, and timing parameters
        """
        super().__init__()
        self.config = config
        self.is_running = True
        self.is_stopped = False  # New flag to track if download was manually stopped
        self.is_paused = False
        self.pause_lock = threading.Event()
        self.pause_lock.set()  # Initially not paused
        self.two_factor_code = None
        self.code_received = False
        # Event loop for handling 2FA synchronization with UI
        self.two_factor_event = QEventLoop()
        self.logger = get_logger()
        self.total_items = 0
        self.completed_items = 0
        
        # Log initialization based on download type
        if config.get('download_single_post', False):
            self.logger.info(f"Initializing single post download: {config['post_url']}")
        else:
            self.logger.info(f"Initializing profile download: {config['target_profile']}")
            
        # Configure anti-detection timing parameters
        self.BASE_DELAY = config.get('base_delay', 8)  # Base delay between requests
        self.JITTER = config.get('jitter', 3)  # Random delay variation
        self.STORY_MULTIPLIER = config.get('story_multiplier', 2.5)  # Extra caution for stories
        self.CRITICAL_WAIT = config.get('critical_wait', 1800)  # Recovery period after errors
        self.LONG_SESSION_CHANCE = config.get('long_session_chance', 0.25)  # Probability of longer breaks

    def _normalize_date(self, date_value, end_of_day=False):
        """
        Convert date to datetime with consistent handling.
        
        Args:
            date_value: String, date, or datetime object
            end_of_day: If True, use max time; otherwise use min time
            
        Returns:
            datetime: Normalized datetime object
        """
        if isinstance(date_value, str):
            return datetime.strptime(date_value, "%Y-%m-%d")
        elif hasattr(date_value, 'timetuple') and not hasattr(date_value, 'hour'):
            # It's a date object, not datetime
            time_part = datetime.max.time() if end_of_day else datetime.min.time()
            return datetime.combine(date_value, time_part)
        return date_value
        
    def quit(self):
        """
        Clean up resources and terminate the download thread.
        
        Ensures that thread termination is properly handled to prevent memory leaks
        and zombie threads when the application closes or downloads are canceled.
        """
        self.logger.info("Download thread stop requested")
        self.is_running = False
        self.is_stopped = True
        # Force thread termination if it doesn't respond
        self.requestInterruption()
        # Emit the stopped signal before calling super().quit()
        self.stopped_signal.emit()
        super().quit()

    def handle_authentication(self, L):
        """
        Handle Instagram authentication with support for 2FA.

        Manages both regular login and two-factor authentication flows. Can use either
        saved session files or direct login with credentials.

        Args:
            L: Instaloader instance to authenticate

        Returns:
            tuple: (success: bool, message: str)
                success: True if authentication succeeded
                message: Description of the authentication result
        """
        try:
            if self.config['use_session']:
                # Load existing session for faster and more reliable auth
                session_file = self.config['session_path']
                if not os.path.exists(session_file):
                    self.logger.error(f"Session file not found: {session_file}")
                    raise FileNotFoundError("Session file not found!")
                    
                # Extract username from session filename
                username = os.path.splitext(os.path.basename(session_file))[0]
                self.logger.info(f"Loading session file for user: {username}")
                L.load_session_from_file(username, session_file)
                return True, "Session loaded successfully!"
            else:
                self.logger.info(f"Logging in with credentials for user: {self.config['username']}")
                
                try:
                    # Attempt regular login first
                    L.context.login(self.config['username'], self.config['password'])
                    self.logger.info("Login successful without 2FA")
                    
                    # Save session after successful login
                    if self.config.get('save_session', True):
                        self._save_session(L, self.config['username'])
                        
                    return True, "Login successful!"
                except instaloader.exceptions.TwoFactorAuthRequiredException:
                    # Handle 2FA
                    self.logger.info("Two-factor authentication required, requesting code from user")
                    self.log_signal.emit("Two-factor authentication required. Please enter the code.", "INFO")
                    
                    # Reset variables
                    self.two_factor_code = None
                    self.code_received = False
                    
                    # Signal the UI to show the 2FA dialog in the main thread
                    self.two_factor_required_signal.emit()
                    
                    # Use simple polling to wait for the code
                    max_wait_secs = 120
                    start_time = time.time()
                    
                    while not self.code_received and time.time() - start_time < max_wait_secs:
                        if not self.is_running:
                            return False, "Download canceled during 2FA"
                        time.sleep(0.2)
                    
                    if not self.code_received or not self.two_factor_code:
                        self.logger.error("No 2FA code provided or timeout")
                        return False, "Two-factor authentication failed: No code provided or timeout"
                    
                    try:
                        # Use the two-factor login method from context
                        self.logger.info("Attempting to complete two-factor authentication")
                        L.context.two_factor_login(self.two_factor_code)
                        self.logger.info("2FA login successful")
                        
                        # Save session after successful 2FA login
                        if self.config.get('save_session', True):
                            self._save_session(L, self.config['username'])
                            
                        return True, "Two-factor authentication successful!"
                    except Exception as e:
                        self.logger.error(f"Error during 2FA login: {e}")
                        return False, f"Two-factor authentication failed: {e}"
                except instaloader.exceptions.BadCredentialsException as e:
                    self.logger.error(f"Bad credentials: {e}")
                    return False, f"Bad credentials: {e}"
                except Exception as e:
                    self.logger.error(f"Login error: {e}")
                    return False, f"Login error: {e}"
        except Exception as e:
            self.logger.error(f"Authentication failed: {str(e)}")
            self.logger.error(traceback.format_exc())
            return False, f"Authentication failed: {e}"

    def _save_session(self, L, username):
        """Save session file after successful login"""
        try:
            # Determine the default session directory
            if os.name == 'nt':  # Windows
                session_dir = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Instaloader')
            else:  # Linux/Mac
                session_dir = os.path.expanduser('~/.config/instaloader')
                
            # Create the directory if it doesn't exist
            os.makedirs(session_dir, exist_ok=True)
            
            # Build the session file path
            session_file = os.path.join(session_dir, f"session-{username}")
            
            # Save the session - Fixed method call to match Instaloader's API
            self.logger.info(f"Saving session file to {session_file}")
            L.save_session_to_file(session_file)  # Changed: removed username parameter
            self.log_signal.emit(f"Session saved to {session_file}", "INFO")
            
            # Emit signal with session file path to update UI
            self.session_saved_signal.emit(session_file)
            
            return True
        except Exception as e:
            self.logger.error(f"Failed to save session: {str(e)}")
            self.log_signal.emit(f"Warning: Could not save session file: {str(e)}", "WARNING")
            return False

    def set_two_factor_code(self, code):
        """Set the 2FA code received from the GUI"""
        self.logger.info(f"Received 2FA code from GUI")
        self.two_factor_code = code
        self.code_received = True

    def download_profile_picture(self, L, profile, target_dir):
        """
        Download profile picture for a given Instagram profile.

        Creates a dedicated directory for profile pictures and implements
        file existence checking to avoid duplicates.

        Args:
            L: Authenticated Instaloader instance
            profile: Instagram profile object
            target_dir: Base directory for downloads

        Returns:
            tuple: (success: bool, message: str)
        """
        try:
            # Create a dedicated directory for profile pictures
            profile_pic_dir = os.path.join(target_dir, "profile_pic")
            os.makedirs(profile_pic_dir, exist_ok=True)
            
            # Check if profile picture already exists
            if self.config.get('skip_existing', True):
                # Profile picture typically uses the profile ID in filename
                existing_files = glob.glob(os.path.join(profile_pic_dir, f"{profile.userid}_*"))
                if existing_files:
                    # Even if skipping, we should emit the existing file for preview
                    for file in existing_files:
                        if file.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
                            self.file_downloaded_signal.emit(file)
                    self.log_signal.emit(f"Skipping existing profile picture", "INFO")
                    return True, "Profile picture already exists"
            
            # Set the directory for this operation
            L.dirname_pattern = profile_pic_dir

            # Capture the list of files before download
            before_files = set(os.listdir(profile_pic_dir))
            
            # Download the profile picture
            L.download_profile(profile, profile_pic_only=True)
            
            # Capture the list of files after download
            after_files = set(os.listdir(profile_pic_dir))
            
            # Find new files by comparing before and after
            new_files = after_files - before_files
            
            # Emit signal for any new files
            for filename in new_files:
                file_path = os.path.join(profile_pic_dir, filename)
                if file_path.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
                    self.file_downloaded_signal.emit(file_path)
                    self.log_signal.emit(f"Successfully downloaded profile picture", "INFO")
            
            return True, "Profile picture downloaded successfully!"
        except Exception as e:
            return False, f"Error downloading profile picture: {e}"

    def calculate_total_items(self, profile, L):
        """Calculate total items to download based on config."""
        total = 0
        downloads = []
        
        # Initialize date range variables first
        since_date = self.config['since_date']
        until_date = self.config['until_date']
        if isinstance(since_date, str):
            since_date = datetime.strptime(since_date, "%Y-%m-%d")
        elif hasattr(since_date, 'timetuple'):
            since_date = datetime.combine(since_date, datetime.min.time())
            
        if isinstance(until_date, str):
            until_date = datetime.strptime(until_date, "%Y-%m-%d")
        elif hasattr(until_date, 'timetuple'):
            until_date = datetime.combine(until_date, datetime.max.time())
        
        # Calculate posts count if enabled
        if not self.config.get('only_stories', False) and not self.config.get('only_highlights', False):
            if self.config.get('ignore_date_range', False):
                # Use post limit or profile mediacount when ignoring date range
                posts_count = min(
                    self.config.get('max_posts', profile.mediacount) or profile.mediacount,
                    profile.mediacount
                )
                total += posts_count
                downloads.append(f"Posts (up to {posts_count})")
            else:
                # For date-filtered downloads, use number of days in range for progress tracking
                total_days = (until_date - since_date).days + 1
                total += total_days
                downloads.append(f"Posts (covering {total_days} days from {since_date.date()} to {until_date.date()})")
                self.log_signal.emit(
                    "Using date range for progress tracking",
                    "INFO"
                )

        # Calculate highlights count if enabled
        if self.config['download_highlights']:
            try:
                highlights = L.get_highlights(profile)
                highlight_count = 0
                highlight_items = 0
                
                for highlight in highlights:
                    highlight_count += 1
                    try:
                        if self.config.get('ignore_date_range', False):
                            # Count all items in highlights
                            items = list(highlight.get_items())
                            highlight_items += len(items)
                        else:
                            # Count items within date range
                            items = list(highlight.get_items())
                            filtered_items = [item for item 
                                              in items if since_date <= item.date <= until_date]
                            highlight_items += len(filtered_items)
                    except Exception as e:
                        self.logger.warning(f"Could not count items in highlight {highlight.title}: {e}")
                        continue
                
                if highlight_items > 0:
                    total += highlight_items
                    downloads.append(f"Highlights ({highlight_items} items from {highlight_count} highlights)")
            except Exception as e:
                self.logger.warning(f"Could not pre-count highlights: {e}")

        # Calculate stories count if enabled and not only_highlights
        if self.config['download_stories'] and not self.config.get('only_highlights', False):
            try:
                stories = L.get_stories([profile.userid])
                story_items = 0
                for story in stories:
                    items = list(story.get_items())
                    story_items += len(items)
                if story_items > 0:
                    # Add story items to total
                    total += story_items
                    downloads.append(f"Stories ({story_items})")
                    self.log_signal.emit(f"Found {story_items} story items to download", "INFO")
            except Exception as e:
                self.logger.warning(f"Could not pre-count stories: {e}")

        # Ensure we have at least 1 total to avoid division by zero
        total = max(1, total)

        # Log what will be downloaded
        if downloads:
            self.log_signal.emit(
                f"Will download: {', '.join(downloads)}. Total estimated items: {total}", 
                "INFO"
            )
        else:
            self.log_signal.emit(
                "No items found to download in the specified criteria", 
                "WARNING"
            )
            
        return total

    def update_progress(self, current, total, type_='overall'):
        """
        Safely update progress signals avoiding division by zero
        """
        if total <= 0:
            total = 1  # Prevent division by zero
            
        # Ensure we don't exceed 100%
        current = min(current, total)
        
        if type_ == 'overall':
            self.progress_signal.emit(current, total, 'overall')
        else:
            self.progress_signal.emit(current, total, 'current')

    def download_posts(self, L, profile, target_dir):
        """
        Download posts from an Instagram profile with date filtering.
        Uses single-pass approach when date filtering is enabled.
        """
        # Create a dedicated directory for posts
        posts_dir = os.path.join(target_dir, "posts")
        os.makedirs(posts_dir, exist_ok=True)
        
        # Set the download path for this operation
        L.dirname_pattern = posts_dir
        
        # Get configuration settings
        ignore_date = self.config.get('ignore_date_range', False)
        since_date = self.config['since_date']
        until_date = self.config['until_date']
        post_limit = self.config.get('max_posts', 0) if self.config.get('limit_posts', False) else 0
        
        # Convert datetime.date objects to datetime.datetime objects
        if isinstance(since_date, str):
            since_date = datetime.strptime(since_date, "%Y-%m-%d")
        elif hasattr(since_date, 'timetuple'):
            since_date = datetime.combine(since_date, datetime.min.time())
            
        if isinstance(until_date, str):
            until_date = datetime.strptime(until_date, "%Y-%m-%d")
        elif hasattr(until_date, 'timetuple'):
            until_date = datetime.combine(until_date, datetime.max.time())
        
        # Initialize counters
        total_found = 0
        downloaded = 0
        skipped = 0
        last_update_time = time.time()
        update_interval = 2.0  # Update UI every 2 seconds
        
        self.log_signal.emit("Starting to download posts matching criteria...", "INFO")
        
        if ignore_date:
            # More efficient approach: Process posts as they come in when ignoring date range
            posts = profile.get_posts()
            post_count = 0
            
            # Initial step - try to estimate the total post count for the progress bar
            # If post_limit is set, use that as our target
            # Otherwise, first attempt to get the post count from the profile
            target_posts = post_limit if post_limit > 0 else profile.mediacount
            if target_posts <= 0:
                target_posts = 100  # Default to 100 if we can't determine count
                self.log_signal.emit(f"Unable to determine total post count, using default value", "INFO")
            else:
                self.log_signal.emit(f"Estimated total posts: {target_posts}", "INFO")
            
            # Set initial progress to 0
            self.progress_signal.emit(0, target_posts, 'overall')
                
            for post in posts:
                if not self.is_running:
                    return False, "Download cancelled"
                
                self.pause_lock.wait()  # Will block if paused
                if not self.is_running:
                    break
                
                total_found += 1
                
                # Update discovery progress periodically
                current_time = time.time()
                if current_time - last_update_time >= update_interval:
                    self.log_signal.emit(f"Found {total_found} posts so far...", "INFO")
                    last_update_time = current_time
                    
                    # If we've exceeded our estimated target, update the target
                    if total_found > target_posts and post_limit <= 0:
                        # Increase by 20% to avoid frequent updates
                        target_posts = int(total_found * 1.2)
                        self.log_signal.emit(f"Adjusting estimated total to {target_posts} posts", "INFO")
                
                # Apply post limit if specified
                if post_limit > 0 and post_count >= post_limit:
                    self.log_signal.emit(f"Reached the maximum number of posts limit ({post_limit}), stopping discovery", "INFO")
                    break
                
                # Check if post already exists before downloading
                post_files_pattern = f"{post.date:%Y-%m-%d_%H-%M-%S}_UTC*"
                existing_files = glob.glob(os.path.join(posts_dir, post_files_pattern))
                
                if existing_files and self.config.get('skip_existing', True):
                    self.log_signal.emit(f"Skipping existing post from {post.date}", "INFO")
                    skipped += 1
                    post_count += 1
                    # Update progress for skipped posts
                    self.progress_signal.emit(post_count, target_posts if post_limit > 0 else target_posts, 'overall')
                    continue
                
                # Download the post
                delay = self.BASE_DELAY + random.uniform(0, self.JITTER)
                self.log_signal.emit(f"Processing post {post_count+1} from {post.date}", "INFO")
                time.sleep(delay)
                
                # Add retry logic
                retry_count = 0
                max_retries = 3
                success = False
                
                while retry_count < max_retries and not success:
                    try:
                        L.download_post(post, target=posts_dir)
                        
                        # Emit signal for any new files
                        pattern = f"{post.date:%Y-%m-%d_%H-%M-%S}_UTC*"
                        for file in glob.glob(os.path.join(posts_dir, pattern)):
                            if file.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.mp4')):
                                self.file_downloaded_signal.emit(file)
                        
                        self.log_signal.emit(f"Successfully downloaded post from {post.date}", "INFO")
                        downloaded += 1
                        success = True
                    except instaloader.exceptions.ConnectionException as e:
                        retry_count += 1
                        wait_time = self.BASE_DELAY * (retry_count * 2)  # Exponential backoff
                        self.log_signal.emit(f"Connection error: {e}. Retrying in {wait_time}s (Attempt {retry_count}/{max_retries})", "WARNING")
                        time.sleep(wait_time)
                    except instaloader.exceptions.TooManyRequestsException:
                        self.log_signal.emit("Rate limited by Instagram! Taking a longer break...", "WARNING")
                        time.sleep(self.CRITICAL_WAIT * 2)  # Double the critical wait time
                        retry_count += 1
                    except Exception as e:
                        self.log_signal.emit(f"Error downloading post: {e}", "ERROR")
                        time.sleep(self.CRITICAL_WAIT)
                        retry_count = max_retries  # Skip to next post after one attempt for other errors
                
                if retry_count == max_retries and not success:
                    self.log_signal.emit(f"Failed to download post after {max_retries} attempts, skipping", "ERROR")
                
                # Add random longer pauses for safety
                if post_count % 5 == 0 and random.random() < self.LONG_SESSION_CHANCE:
                    extra_delay = 20 + random.uniform(0, 10)
                    self.log_signal.emit(f"Long session safety delay: {extra_delay:.1f}s", "INFO")
                    time.sleep(extra_delay)
                
                post_count += 1
                # Update progress using our adjusted target
                if post_limit > 0:
                    # If we have a post limit, use that as denominator
                    self.progress_signal.emit(post_count, post_limit, 'overall')
                else:
                    # Otherwise use our estimated target, but cap at 100%
                    progress_value = min(post_count, target_posts)
                    self.progress_signal.emit(progress_value, target_posts, 'overall')
            
            # Final summary message
            self.log_signal.emit(
                f"Posts download completed: {downloaded} downloaded, {skipped} skipped, {total_found} total found" +
                (f" (limited to {post_limit})" if post_limit > 0 and total_found > post_limit else ""),
                "INFO"
            )
            
            # Set the progress to 100% when complete
            final_target = post_limit if post_limit > 0 else target_posts
            self.progress_signal.emit(final_target, final_target, 'overall')
            
        else:
            # Single-pass approach for date-filtered downloads
            posts = profile.get_posts()
            
            # For date-filtered downloads, use days as progress denominator
            total_days = (until_date - since_date).days + 1
            last_post_date = None
            matching_posts = 0
            downloaded = 0
            skipped = 0
            processed_days_set = set()  # Track which days we've processed posts from
            
            self.log_signal.emit(f"Processing posts in date range: {since_date.date()} to {until_date.date()}", "INFO")
            self.progress_signal.emit(0, total_days, 'overall')  # Start at 0%
            
            for post in posts:
                # Update discovery progress periodically
                current_time = time.time()
                if current_time - last_update_time >= update_interval:
                    self.log_signal.emit(
                        f"Processing posts... ({matching_posts} match criteria so far)", 
                        "INFO"
                    )
                    last_update_time = current_time
                
                # Check if past the date range (optimization for chronological order)
                if post.date < since_date:
                    self.log_signal.emit("Reached posts older than the specified date range, stopping", "INFO")
                    # Ensure we show 100% progress when we've processed all dates
                    self.progress_signal.emit(total_days, total_days, 'overall')
                    break
                
                # Check if within date range
                if since_date <= post.date <= until_date:
                    matching_posts += 1
                    
                    # Update day-based progress whenever we see a post from a new day
                    if post.date.date() not in processed_days_set:
                        processed_days_set.add(post.date.date())
                        days_processed = len(processed_days_set)
                        # Update overall progress
                        self.progress_signal.emit(min(days_processed, total_days), total_days, 'overall')
                        last_post_date = post.date.date()
                    
                    # Process the post
                    if not self.is_running:
                        return False, "Download cancelled"
                        
                    self.pause_lock.wait()  # Will block if paused
                    if not self.is_running:
                        break
                    
                    # Check if post already exists
                    post_files_pattern = f"{post.date:%Y-%m-%d_%H-%M-%S}_UTC*"
                    existing_files = glob.glob(os.path.join(posts_dir, post_files_pattern))
                    
                    if existing_files and self.config.get('skip_existing', True):
                        self.log_signal.emit(f"Skipping existing post from {post.date}", "INFO")
                        skipped += 1
                        self.progress_signal.emit(100, 100, 'current')  # Show 100% for skipped
                        continue

                    # Download the post with existing retry logic
                    delay = self.BASE_DELAY + random.uniform(0, self.JITTER)
                    self.log_signal.emit(f"Processing post {matching_posts} from {post.date}", "INFO")
                    time.sleep(delay)
                    
                    # Reset current progress for new download
                    self.progress_signal.emit(0, 100, 'current')
                    
                    # Existing retry logic
                    retry_count = 0
                    max_retries = 3
                    success = False
                    
                    while retry_count < max_retries and not success:
                        try:
                            # Show download in progress
                            self.progress_signal.emit(25, 100, 'current')
                            L.download_post(post, target=posts_dir)
                            self.progress_signal.emit(75, 100, 'current')
                            
                            # Emit signal for any new files
                            pattern = f"{post.date:%Y-%m-%d_%H-%M-%S}_UTC*"
                            for file in glob.glob(os.path.join(posts_dir, pattern)):
                                if file.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.mp4')):
                                    self.file_downloaded_signal.emit(file)
                            
                            self.progress_signal.emit(100, 100, 'current')
                            self.log_signal.emit(f"Successfully downloaded post from {post.date}", "INFO")
                            downloaded += 1
                            success = True
                            
                        except instaloader.exceptions.ConnectionException as e:
                            retry_count += 1
                            wait_time = self.BASE_DELAY * (retry_count * 2)  # Exponential backoff
                            self.log_signal.emit(
                                f"Connection error: {e}. Retrying in {wait_time}s (Attempt {retry_count}/{max_retries})", 
                                "WARNING"
                            )
                            time.sleep(wait_time)
                        except instaloader.exceptions.TooManyRequestsException:
                            self.log_signal.emit("Rate limited by Instagram! Taking a longer break...", "WARNING")
                            time.sleep(self.CRITICAL_WAIT * 2)  # Double the critical wait time
                            retry_count += 1
                        except Exception as e:
                            self.log_signal.emit(f"Error downloading post: {e}", "ERROR")
                            time.sleep(self.CRITICAL_WAIT)
                            retry_count = max_retries  # Skip to next post after one attempt for other errors
                    
                    # Add random longer pauses for safety
                    if matching_posts % 5 == 0 and random.random() < self.LONG_SESSION_CHANCE:
                        extra_delay = 20 + random.uniform(0, 10)
                        self.log_signal.emit(f"Long session safety delay: {extra_delay:.1f}s", "INFO")
                        time.sleep(extra_delay)
                    
                    # Check post limit
                    if post_limit > 0 and matching_posts >= post_limit:
                        self.log_signal.emit(f"Reached the maximum number of posts limit ({post_limit})", "INFO")
                        break
            
            # Ensure we show 100% progress at the end
            self.progress_signal.emit(total_days, total_days, 'overall')
            
            # Final summary message
            self.log_signal.emit(
                f"Posts download completed: {downloaded} downloaded, {skipped} skipped, {matching_posts} total in date range" +
                (f" (limited to {post_limit})" if post_limit > 0 and matching_posts > post_limit else ""),
                "INFO"
            )
        
        return True, "Posts download completed"

    def download_stories_and_highlights(self, L, profile, target_dir):
        """
        Download stories and highlights from an Instagram profile.

        Handles both regular stories and story highlights with:
        - Separate directory structure for each type
        - Date filtering support
        - Progress tracking per highlight/story
        - Anti-detection timing system

        Args:
            L: Authenticated Instaloader instance
            profile: Instagram profile object
            target_dir: Base directory for downloads

        Returns:
            tuple: (success: bool, message: str)
        """
        # Get date range parameters - need these for filtering highlight items
        ignore_date = self.config.get('ignore_date_range', False)
        since_date = self.config['since_date']
        until_date = self.config['until_date']
        
        # Convert datetime.date objects to datetime.datetime objects
        # This fixes the comparison with item.date which is a datetime.datetime
        if isinstance(since_date, str):
            since_date = datetime.strptime(since_date, "%Y-%m-%d")
        elif hasattr(since_date, 'timetuple'):  # Check if it's a date object
            since_date = datetime.combine(since_date, datetime.min.time())
            
        if isinstance(until_date, str):
            until_date = datetime.strptime(until_date, "%Y-%m-%d")
        elif hasattr(until_date, 'timetuple'):  # Check if it's a date object
            until_date = datetime.combine(until_date, datetime.max.time())  # Use end of day
        
        if self.config['download_highlights']:
            highlights_dir = os.path.join(target_dir, "highlights")
            os.makedirs(highlights_dir, exist_ok=True)
            try:
                # Materialize iterator once to avoid double API call
                highlights = list(L.get_highlights(profile))
                highlight_count = len(highlights)
                
                self.log_signal.emit(
                    f"Found {highlight_count} highlights to download", 
                    "INFO"
                )
                
                for idx, highlight in enumerate(highlights):
                    if not self.is_running:
                        return False, "Download cancelled"

                    self.pause_lock.wait()  # Will block if paused
                    if not self.is_running:
                        break

                    # Reset current progress for each highlight
                    self.progress_signal.emit(0, 100, 'current')
                    
                    self.log_signal.emit(
                        f"Processing highlight {idx+1}/{highlight_count}: {highlight.title}", 
                        "INFO"
                    )
                    highlight_target = os.path.join(highlights_dir, highlight.title)
                    highlight_target = os.path.abspath(highlight_target)
                    os.makedirs(highlight_target, exist_ok=True)
                    
                    # Set the directory pattern specifically for this highlight
                    L.dirname_pattern = highlight_target
                    
                    # More efficient approach when ignoring date range - process items as we go
                    if ignore_date:
                        items_iterator = highlight.get_items()
                        processed_count = 0
                        total_items = 0
                        
                        for item in items_iterator:
                            if not self.is_running:
                                return False, "Download cancelled"
                            
                            self.pause_lock.wait()  # Will block if paused
                            if not self.is_running:
                                break
                            
                            total_items += 1
                                
                            # Check if highlight item already exists
                            item_files_pattern = f"{item.date:%Y-%m-%d_%H-%M-%S}_UTC*"
                            existing_files = glob.glob(os.path.join(highlight_target, item_files_pattern))
                            
                            if existing_files and self.config.get('skip_existing', True):
                                self.log_signal.emit(f"Skipping existing highlight item from {item.date}", "INFO")
                                processed_count += 1
                                self.completed_items += 1
                                self.progress_signal.emit(self.completed_items, self.total_items, 'overall')
                                self.progress_signal.emit(100, 100, 'current')
                                continue

                            story_delay = self.BASE_DELAY * self.STORY_MULTIPLIER + random.uniform(1, 3)
                            time.sleep(story_delay)
                            
                            try:
                                L.download_storyitem(item, target=highlight_target)
                                
                                # Emit signal for any new files
                                pattern = f"{item.date:%Y-%m-%d_%H-%M-%S}_UTC*"
                                for file in glob.glob(os.path.join(highlight_target, pattern)):
                                    if file.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.mp4')):
                                        self.file_downloaded_signal.emit(file)
                                
                                self.log_signal.emit(f"Successfully downloaded highlight item from {item.date}", "INFO")
                                processed_count += 1
                                self.completed_items += 1
                                self.progress_signal.emit(self.completed_items, self.total_items, 'overall')
                            except Exception as e:
                                self.log_signal.emit(f"Error downloading highlight item: {e}", "ERROR")
                            
                            self.progress_signal.emit(processed_count, total_items, 'current')
                        
                        self.log_signal.emit(f"Downloaded {processed_count} highlight items", "INFO")
                    else:
                        # Original approach with date filtering
                        items = list(highlight.get_items())
                        
                        # Apply date filtering to highlight items
                        filtered_items = [item for item in items if since_date <= item.date <= until_date]
                        if len(filtered_items) < len(items):
                            self.log_signal.emit(
                                f"Filtered {len(items) - len(filtered_items)} items outside date range", 
                                "INFO"
                            )
                        items = filtered_items
                        
                        self.log_signal.emit(f"Found {len(items)} items in this highlight within date range", "INFO")
                        
                        for item_idx, item in enumerate(items):
                            if not self.is_running:
                                return False, "Download cancelled"
                                
                            self.pause_lock.wait()  # Will block if paused
                            if not self.is_running:
                                break
                            
                            # Check if highlight item already exists
                            item_files_pattern = f"{item.date:%Y-%m-%d_%H-%M-%S}_UTC*"
                            existing_files = glob.glob(os.path.join(highlight_target, item_files_pattern))
                            
                            if existing_files and self.config.get('skip_existing', True):
                                self.log_signal.emit(f"Skipping existing highlight item from {item.date}", "INFO")
                                self.completed_items += 1
                                self.progress_signal.emit(self.completed_items, self.total_items, 'overall')
                                self.progress_signal.emit(100, 100, 'current')
                                continue

                            story_delay = self.BASE_DELAY * self.STORY_MULTIPLIER + random.uniform(1, 3)
                            time.sleep(story_delay)
                            try:
                                L.download_storyitem(item, target=highlight_target)
                                
                                # Emit signal for any new files
                                pattern = f"{item.date:%Y-%m-%d_%H-%M-%S}_UTC*"
                                for file in glob.glob(os.path.join(highlight_target, pattern)):
                                    if file.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.mp4')):
                                        self.file_downloaded_signal.emit(file)
                                
                                self.log_signal.emit(f"Successfully downloaded highlight item from {item.date}", "INFO")
                                self.completed_items += 1
                                self.progress_signal.emit(self.completed_items, self.total_items, 'overall')
                            except Exception as e:
                                self.log_signal.emit(f"Error downloading highlight item: {e}", "ERROR")
                            
                            self.progress_signal.emit(item_idx+1, len(items), 'current')
                    
                    # One more check for stop after each highlight
                    if not self.is_running:
                        return False, "Download cancelled"
                        
                    self.progress_signal.emit(idx+1, highlight_count, 'overall')
            except Exception as e:
                self.log_signal.emit(f"Error downloading highlights: {e}", "ERROR")
        
        # Only download stories if not only_highlights
        if self.config['download_stories'] and not self.config.get('only_highlights', False):
            stories_dir = os.path.join(target_dir, "stories")
            stories_dir = os.path.abspath(stories_dir)
            os.makedirs(stories_dir, exist_ok=True)
            
            # Set the directory pattern specifically for stories
            L.dirname_pattern = stories_dir
            
            try:
                # Materialize stories and their items in one pass to avoid double API call
                stories_data = []
                total_story_items = 0
                total_processed = 0
                
                for story in L.get_stories([profile.userid]):
                    items = list(story.get_items())
                    stories_data.append(items)
                    total_story_items += len(items)
                
                self.log_signal.emit(f"Found {total_story_items} total story items", "INFO")
                
                for items in stories_data:
                    for idx, item in enumerate(items):
                        if not self.is_running:
                            return False, "Download cancelled"
                            
                        self.pause_lock.wait()  # Will block if paused
                        if not self.is_running:
                            break
                            
                        # Check if story item already exists
                        item_files_pattern = f"{item.date:%Y-%m-%d_%H-%M-%S}_UTC*"
                        existing_files = glob.glob(os.path.join(stories_dir, item_files_pattern))
                        
                        if existing_files and self.config.get('skip_existing', True):
                            self.log_signal.emit(f"Skipping existing story item from {item.date}", "INFO")
                            self.completed_items += 1
                            total_processed += 1
                            # Update both progress bars
                            self.progress_signal.emit(self.completed_items, self.total_items, 'overall')
                            self.progress_signal.emit(total_processed, total_story_items, 'current')
                            continue
                            
                        story_delay = self.BASE_DELAY * self.STORY_MULTIPLIER + random.uniform(2, 5)
                        self.log_signal.emit(
                            f"Processing story item {total_processed + 1}/{total_story_items} from {item.date}", 
                            "INFO"
                        )
                        time.sleep(story_delay)
                        
                        try:
                            L.download_storyitem(item, target=stories_dir)
                            
                            # Emit signal for any new files
                            pattern = f"{item.date:%Y-%m-%d_%H-%M-%S}_UTC*"
                            for file in glob.glob(os.path.join(stories_dir, pattern)):
                                if file.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.mp4')):
                                    self.file_downloaded_signal.emit(file)
                            
                            self.log_signal.emit(f"Successfully downloaded story item from {item.date}", "INFO")
                            total_processed += 1
                            self.completed_items += 1
                            # Update both progress bars
                            self.progress_signal.emit(self.completed_items, self.total_items, 'overall')
                            self.progress_signal.emit(total_processed, total_story_items, 'current')
                        except Exception as e:
                            self.log_signal.emit(f"Error downloading story item: {e}", "ERROR")
                    
                self.log_signal.emit(f"Downloaded {total_processed} of {total_story_items} story items", "INFO")

                # Ensure we set progress to 100% if all items are processed
                if total_processed == total_story_items:
                    self.progress_signal.emit(self.total_items, self.total_items, 'overall')
                    self.progress_signal.emit(total_story_items, total_story_items, 'current')

            except instaloader.exceptions.QueryReturnedBadRequestException:
                self.log_signal.emit("Story download blocked - likely rate limited", "WARNING")
            except Exception as e:
                self.log_signal.emit(f"Error accessing stories: {e}", "ERROR")
        
        return True, "Stories and highlights download completed"

    def sanitize_path(self, path):
        """
        Sanitize file paths to ensure cross-platform compatibility.

        Handles:
        - Unicode character normalization
        - Path separator standardization
        - Duplicate separator removal
        - Drive letter normalization (Windows)

        Args:
            path (str): Raw file path to sanitize

        Returns:
            str: Sanitized path string compatible with current OS
        """
        if path is None:
            return None
        
        # Replace Unicode variants of path separators with standard ones
        path = path.replace('：', ':')  # Replace full-width colon
        path = path.replace('﹨', os.path.sep)  # Replace small backslash
        path = path.replace('／', os.path.sep)  # Replace full-width slash
        path = path.replace('\\', os.path.sep)  # Normalize backslashes
        path = path.replace('/', os.path.sep)  # Normalize forward slashes
        
        # Remove duplicate path separators
        while os.path.sep * 2 in path:
            path = path.replace(os.path.sep * 2, os.path.sep)
        
        # Handle repeated path prefixes (like D:\path\D:\path)
        drive_pattern = re.compile(r'^([a-zA-Z]:' + re.escape(os.path.sep) + r'.*?)' + 
                                  re.escape(os.path.sep) + r'\1', re.IGNORECASE)
        match = drive_pattern.match(path)
        if match:
            path = match.group(1)
        
        return os.path.normpath(path)

    def download_single_post(self, L, post_id, target_dir):
        """Download a single post by its shortcode/ID"""
        try:
            # Get the post object using the post ID
            self.log_signal.emit(f"Fetching post with ID: {post_id}", "INFO")
            post = instaloader.Post.from_shortcode(L.context, post_id)
            
            # Get profile name for better organization
            profile_name = post.owner_username
            self.log_signal.emit(f"Post belongs to user: {profile_name}", "INFO")
            
            # Use the proper directory structure based on profile name
            proper_target_dir = os.path.join(target_dir, profile_name)  # Removed "downloads" from path
            os.makedirs(proper_target_dir, exist_ok=True)
            
            # Create posts directory under the profile name
            posts_dir = os.path.join(proper_target_dir, "posts")
            os.makedirs(posts_dir, exist_ok=True)
            
            # Set the download path for this operation
            L.dirname_pattern = posts_dir
            
            # Check if post already exists before downloading
            post_files_pattern = f"{post.date:%Y-%m-%d_%H-%M-%S}_UTC*"
            existing_files = glob.glob(os.path.join(posts_dir, post_files_pattern))
            
            if existing_files and self.config.get('skip_existing', True):
                self.log_signal.emit(f"Skipping existing post from {post.date}", "INFO")
                return True, "Post already exists"
            
            # Download the post
            self.log_signal.emit(f"Downloading post from {post.date}", "INFO")
            L.download_post(post, target=posts_dir)
            
            # Emit signal for any new files
            pattern = f"{post.date:%Y-%m-%d_%H-%M-%S}_UTC*"
            for file in glob.glob(os.path.join(posts_dir, pattern)):
                if file.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.mp4')):
                    self.file_downloaded_signal.emit(file)
            
            self.log_signal.emit(f"Successfully downloaded post from {post.date}", "INFO")
            return True, "Post downloaded successfully"
            
        except instaloader.exceptions.InstaloaderException as e:
            self.log_signal.emit(f"Error fetching post: {e}", "ERROR")
            return False, f"Error: {str(e)}"
            
        except Exception as e:
            self.logger.error(f"Error in download_single_post: {str(e)}")
            self.logger.error(traceback.format_exc())
            self.log_signal.emit(f"Error: {str(e)}", "ERROR")
            return False, f"Error: {str(e)}"

    def download_single_reel(self, L, post_id, target_dir):
        """Download a single reel (treated same as post since reels and posts are interconnected)"""
        try:
            # Reels are technically posts with a different URL format
            self.log_signal.emit(f"Fetching reel with ID: {post_id}", "INFO")
            reel = instaloader.Post.from_shortcode(L.context, post_id)
            
            # Get profile name for better organization
            profile_name = reel.owner_username
            self.log_signal.emit(f"Reel belongs to user: {profile_name}", "INFO")
            
            # Use the proper directory structure based on profile name
            proper_target_dir = os.path.join(target_dir, profile_name)  # Removed "downloads" from path
            os.makedirs(proper_target_dir, exist_ok=True)
            
            # Store reels in the posts directory since they're interconnected with regular posts
            posts_dir = os.path.join(proper_target_dir, "posts")
            os.makedirs(posts_dir, exist_ok=True)
            
            # Set the download path for this operation
            L.dirname_pattern = posts_dir
            
            # Check if reel already exists
            reel_files_pattern = f"{reel.date:%Y-%m-%d_%H-%M-%S}_UTC*"
            existing_files = glob.glob(os.path.join(posts_dir, reel_files_pattern))
            
            if existing_files and self.config.get('skip_existing', True):
                self.log_signal.emit(f"Skipping existing reel from {reel.date}", "INFO")
                return True, "Reel already exists"
            
            # Download the reel
            self.log_signal.emit(f"Downloading reel from {reel.date}", "INFO")
            L.download_post(reel, target=posts_dir)
            
            # Emit signal for any new files
            pattern = f"{reel.date:%Y-%m-%d_%H-%M-%S}_UTC*"
            for file in glob.glob(os.path.join(posts_dir, pattern)):
                if file.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.mp4')):
                    self.file_downloaded_signal.emit(file)
            
            self.log_signal.emit(f"Successfully downloaded reel from {reel.date}", "INFO")
            return True, "Reel downloaded successfully"
            
        except instaloader.exceptions.InstaloaderException as e:
            self.log_signal.emit(f"Error fetching reel: {e}", "ERROR")
            return False, f"Error: {str(e)}"
            
        except Exception as e:
            self.logger.error(f"Error in download_single_reel: {str(e)}")
            self.logger.error(traceback.format_exc())
            self.log_signal.emit(f"Error: {str(e)}", "ERROR")
            return False, f"Error: {str(e)}"

    def download_single_story(self, L, identifier, target_dir):
        """Download a single story by username_storyid"""
        try:
            # Parse username and story ID from the combined identifier
            # Fix for usernames containing underscores and other special characters
            parts = identifier.split('_')
            if len(parts) < 2:
                return False, "Invalid story identifier format"
                
            # The last part is the story ID, everything else is the username with any special chars preserved
            story_id = parts[-1]
            username = '_'.join(parts[:-1])  # Reconstruct username with any underscores
            
            # Log the parsed components for debugging
            self.logger.debug(f"Parsed story identifier: username='{username}', story_id='{story_id}'")
            self.log_signal.emit(f"Fetching story from user {username} with ID: {story_id}", "INFO")
            
            # Use the proper directory structure based on username
            proper_target_dir = os.path.join(target_dir, username)  # Removed "downloads" from path
            os.makedirs(proper_target_dir, exist_ok=True)
            
            # Create stories directory under the profile name
            stories_dir = os.path.join(proper_target_dir, "stories")
            os.makedirs(stories_dir, exist_ok=True)
            
            # Set the download path for this operation
            L.dirname_pattern = stories_dir
            
            # Get the profile first
            try:
                profile = instaloader.Profile.from_username(L.context, username)
            except instaloader.exceptions.ProfileNotExistsException:
                return False, f"Profile '{username}' doesn't exist or is private"
            
            # Get the stories for this profile
            stories = L.get_stories([profile.userid])
            found = False
            
            # Look for the specific story by ID
            for story in stories:
                for item in story.get_items():
                    if str(item.mediaid) == story_id:
                        found = True
                        self.log_signal.emit(f"Found story with ID {story_id}, downloading...", "INFO")
                        L.download_storyitem(item, target=stories_dir)
                        
                        # Emit signal for any new files
                        pattern = f"{item.date:%Y-%m-%d_%H-%M-%S}_UTC*"
                        for file in glob.glob(os.path.join(stories_dir, pattern)):
                            if file.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.mp4')):
                                self.file_downloaded_signal.emit(file)
                        
                        self.log_signal.emit(f"Successfully downloaded story from {item.date}", "INFO")
                        return True, "Story downloaded successfully"
            
            if not found:
                self.log_signal.emit("Story not found. It may be expired or private.", "ERROR")
                return False, ("Story not found. Instagram stories normally expire after 24 hours, "
                              "or this story may only be visible to logged-in followers.")
                
        except instaloader.exceptions.InstaloaderException as e:
            self.log_signal.emit(f"Error fetching story: {e}", "ERROR")
            return False, f"Error: {str(e)}"
            
        except Exception as e:
            self.logger.error(f"Error in download_single_story: {str(e)}")
            self.logger.error(traceback.format_exc())
            self.log_signal.emit(f"Error: {str(e)}", "ERROR")
            return False, f"Error: {str(e)}"

    def download_single_highlight(self, L, highlight_id, target_dir):
        """Download a single highlight by its ID"""
        try:
            # Get profile name through simpler means
            profile_name = None
            
            # Get date range settings
            ignore_date = self.config.get('ignore_date_range', False)
            since_date = self.config.get('since_date')
            until_date = self.config.get('until_date')
            
            # Convert date objects if needed
            if isinstance(since_date, str):
                since_date = datetime.strptime(since_date, "%Y-%m-%d")
            elif hasattr(since_date, 'timetuple'):
                since_date = datetime.combine(since_date, datetime.min.time())
                
            if isinstance(until_date, str):
                until_date = datetime.strptime(until_date, "%Y-%m-%d")
            elif hasattr(until_date, 'timetuple'):
                until_date = datetime.combine(until_date, datetime.max.time())

            # Clean up highlight ID
            highlight_id = highlight_id.replace('highlights_', '')
            
            # 1. Get username from URL or config
            if 'post_url' in self.config:
                url = self.config['post_url']
                # Handle usernames with underscores in the URL
                owner_match = re.search(r'instagram\.com/([^/]+)/stories/highlights', url)
                if owner_match:
                    profile_name = owner_match.group(1)
                    self.log_signal.emit(f"Got profile name from URL: {profile_name}", "INFO")
            
            # 2. Try config provided highlight owner
            if not profile_name and self.config.get('highlight_owner'):
                profile_name = self.config['highlight_owner']
                self.log_signal.emit(f"Using provided highlight owner: {profile_name}", "INFO")
                
            # 3. Use logged in username as last resort
            if not profile_name:
                profile_name = self.config.get('username')
                if not profile_name:
                    return False, "For highlight: Use this URL pattern https://www.instagram.com/USERNAME/stories/highlights/12345678991234567/."
                self.log_signal.emit(f"Using logged in username: {profile_name}", "INFO")

            # Create standard directory structure
            profile_dir = os.path.join(target_dir, profile_name)  # Removed "downloads" from path
            highlights_dir = os.path.join(profile_dir, "highlights")
            os.makedirs(highlights_dir, exist_ok=True)

            # Get profile and download highlight
            profile = instaloader.Profile.from_username(L.context, profile_name)
            highlights = L.get_highlights(profile)
            
            for highlight in highlights:
                if str(highlight.unique_id) == highlight_id:
                    highlight_dir = os.path.join(highlights_dir, highlight.title)
                    os.makedirs(highlight_dir, exist_ok=True)
                    L.dirname_pattern = highlight_dir

                    items = list(highlight.get_items())
                    
                    # Apply date filtering if enabled
                    if not ignore_date:
                        filtered_items = [item for item in items if since_date <= item.date <= until_date]
                        if len(filtered_items) < len(items):
                            self.log_signal.emit(
                                f"Filtered {len(items) - len(filtered_items)} items outside date range", 
                                "INFO"
                            )
                        items = filtered_items
                    
                    self.log_signal.emit(f"Downloading {len(items)} items from highlight '{highlight.title}'", "INFO")
                    
                    for idx, item in enumerate(items):
                        if not self.is_running:
                            return False, "Download cancelled"

                        self.pause_lock.wait()  # Will block if paused
                        if not self.is_running:
                            break

                        self.progress_signal.emit(idx+1, len(items), 'current')
                        
                        try:
                            L.download_storyitem(item, target=highlight_dir)
                            
                            pattern = f"{item.date:%Y-%m-%d_%H-%M-%S}_UTC*"
                            for file in glob.glob(os.path.join(highlight_dir, pattern)):
                                if file.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.mp4')):
                                    self.file_downloaded_signal.emit(file)
                                    
                            time.sleep(self.BASE_DELAY + random.uniform(0, self.JITTER))
                        except Exception as e:
                            self.log_signal.emit(f"Error downloading item {idx+1}: {str(e)}", "WARNING")
                            continue

                    return True, f"Downloaded highlight: {len(items)} items"
                    
            return False, f"Could not find highlight with ID: {highlight_id}"

        except instaloader.exceptions.InstaloaderException as e:
            return False, f"Instagram error: {str(e)}"
        except Exception as e:
            self.logger.error(traceback.format_exc())
            return False, f"Error: {str(e)}"

    def run(self):
        """
        Main execution method for the download thread.

        Orchestrates the entire download process:
        1. Directory setup and path sanitization
        2. Authentication and session management
        3. Content type detection and routing
        4. Progress tracking and logging
        5. Error handling and recovery

        The method handles both single-item downloads (post/story/reel)
        and complete profile downloads based on configuration.
        """
        logger = self.logger
        original_cwd = os.getcwd()
        
        try:
            if not self.is_running:
                # If thread was stopped before starting, emit stopped signal and finish
                if self.is_stopped:
                    self.stopped_signal.emit()
                self.finished.emit()
                return
                
            # Create target directory - Sanitize and fix path issues
            download_dir = self.sanitize_path(self.config['download_dir'])
            download_dir = os.path.abspath(download_dir)
            
            # Create downloads directory
            downloads_dir = os.path.join(download_dir, "downloads")
            os.makedirs(downloads_dir, exist_ok=True)
            
            # Determine if we're downloading a single post or a profile
            is_single_post = self.config.get('download_single_post', False)
            
            # For single posts, use downloads_dir directly
            # The download methods will create profile-based subdirectory
            if is_single_post:
                # Use downloads_dir directly - actual directory based on post owner
                target_dir = downloads_dir
            else:
                # For profiles, use the profile name as before
                target_dir = os.path.join(downloads_dir, self.config['target_profile'])
                
            target_dir = os.path.abspath(target_dir)
            
            # Create the directory
            os.makedirs(target_dir, exist_ok=True)
            logger.info(f"Download directory created at: {target_dir}")
            self.log_signal.emit(f"Downloading to {target_dir}", "INFO")
                
            # Initialize standard instaloader (no custom class)
            L = instaloader.Instaloader(
                sleep=True,
                max_connection_attempts=3,
                request_timeout=self.config.get('request_timeout', 300),
                resume_prefix=f"resume_{self.config['target_profile']}",
                download_pictures=True,
                download_videos=True,
                download_video_thumbnails=True,
                download_geotags=False,
                download_comments=False,
                save_metadata=True
            )
            
            # Set current working directory to the sanitized path
            os.chdir(download_dir)
            
            # Authentication with 2FA support
            success, message = self.handle_authentication(L)
            
            if not success:
                self.log_signal.emit(message, "ERROR")
                os.chdir(original_cwd)
                self.finished.emit()
                return
                
            self.log_signal.emit(message, "INFO")
            
            # Check if we're still running after authentication
            if not self.is_running:
                if self.is_stopped:
                    self.stopped_signal.emit()
                self.finished.emit()
                os.chdir(original_cwd)
                return
                
            # Handle different download types
            if is_single_post:
                # Single post download mode
                post_id = self.config.get('post_id', '')
                post_url = self.config.get('post_url', '')
                
                # Extract highlight owner if present in URL (new enhancement)
                highlight_owner = None
                if '/stories/highlights/' in post_url:
                    # Try to extract username from URL format like instagram.com/username/highlights/ID
                    owner_match = re.search(r'instagram\.com/([^/]+)/stories/highlights', post_url) 
                    if owner_match:
                        highlight_owner = owner_match.group(1)
                        self.config['highlight_owner'] = highlight_owner
                        self.log_signal.emit(f"Extracted highlight owner from URL: {highlight_owner}", "INFO")
                
                if not post_id:
                    self.log_signal.emit("Error: Could not extract post ID from URL", "ERROR")
                    os.chdir(original_cwd)
                    self.finished.emit()
                    return
                
                self.log_signal.emit(f"Processing single item URL: {post_url}", "INFO")
                
                # Determine the type of post and use appropriate download method
                # Each method will manage its own directory structure
                if '/p/' in post_url:
                    # Regular post
                    success, message = self.download_single_post(L, post_id, target_dir)
                elif '/reel/' in post_url:
                    # Reel
                    success, message = self.download_single_reel(L, post_id, target_dir)
                elif '/stories/' in post_url:
                    if '/highlights/' in post_url:
                        # Highlight
                        success, message = self.download_single_highlight(L, post_id, target_dir)
                    else:
                        # Story
                        success, message = self.download_single_story(L, post_id, target_dir)
                else:
                    self.log_signal.emit("Unrecognized URL format", "ERROR")
                    success = False
                    message = "URL format not supported"
                
                # Log the result
                self.log_signal.emit(message, "INFO" if success else "ERROR")
                
                # Add final completion message for single downloads
                if success:
                    self.log_signal.emit(f"Single item download completed successfully!", "INFO")
                else:
                    self.log_signal.emit(f"Single item download failed.", "ERROR")
                
                # Clean up temporary directory if empty
                try:
                    os.rmdir(target_dir)
                except OSError:
                    pass # Ignore if not empty or can't delete
                
            else:
                # Regular profile download mode - use existing code
                try:
                    profile = instaloader.Profile.from_username(L.context, self.config['target_profile'])
                    self.log_signal.emit(
                        f"Starting download for profile: {self.config['target_profile']}", 
                        "INFO"
                    )
                    
                    # Add information about whether date filtering is being applied
                    if self.config.get('ignore_date_range', False):
                        self.log_signal.emit(
                            "Date range is being ignored - all content (posts, highlights, stories) will be downloaded without date filtering", 
                            "INFO"
                        )
                        
                        # Add specific message about post limits if enabled
                        if self.config.get('limit_posts', False) and self.config.get('max_posts', 0) > 0:
                            self.log_signal.emit(
                                f"Post limit is set to {self.config.get('max_posts')} - only the most recent posts will be downloaded", 
                                "INFO"
                            )
                    else:
                        since_date = self.config['since_date']
                        until_date = self.config['until_date']
                        self.log_signal.emit(
                            f"Date filtering is active - only content from {since_date} to {until_date} will be downloaded", 
                            "INFO"
                        )
                    
                    # Calculate total items and initialize progress tracking
                    self.total_items = self.calculate_total_items(profile, L)
                    self.completed_items = 0
                    
                    # Initialize progress bars
                    self.progress_signal.emit(0, self.total_items, 'overall')
                    self.progress_signal.emit(0, 100, 'current')
                    
                    # Profile picture only download
                    if self.config.get('profile_pic_only', False):
                        success, message = self.download_profile_picture(L, profile, target_dir)
                        self.log_signal.emit(message, "INFO" if success else "ERROR")
                        os.chdir(original_cwd)  # Restore working directory
                        self.finished.emit()
                        return
                    
                    # Download posts if not only_stories and not only_highlights
                    if not self.config.get('only_stories', False) and not self.config.get('only_highlights', False):
                        # Always download profile picture first when downloading posts
                        success, message = self.download_profile_picture(L, profile, target_dir)
                        self.log_signal.emit(message, "INFO" if success else "ERROR")
                        
                        # Check if user stopped the download
                        if not self.is_running:
                            if self.is_stopped:
                                self.stopped_signal.emit()
                            os.chdir(original_cwd)
                            self.finished.emit()
                            return
                            
                        success, message = self.download_posts(L, profile, target_dir)
                        if not success:
                            self.log_signal.emit(message, "ERROR")
                            os.chdir(original_cwd)  # Restore working directory
                            # Check if it was due to cancellation
                            if not self.is_running and self.is_stopped:
                                self.stopped_signal.emit()
                            self.finished.emit()
                            return
                    else:
                        if self.config.get('only_stories', False):
                            self.log_signal.emit(
                                "Skipping posts download as 'Only Download Stories' is enabled", 
                                "INFO"
                            )
                        elif self.config.get('only_highlights', False):
                            self.log_signal.emit(
                                "Skipping posts download as 'Only Download Highlights' is enabled", 
                                "INFO"
                            )
                    
                    # Check if user stopped the download
                    if not self.is_running:
                        if self.is_stopped:
                            self.stopped_signal.emit()
                        os.chdir(original_cwd)
                        self.finished.emit()
                        return
                        
                    # If only_highlights is true, we should only download highlights
                    if self.config.get('only_highlights', False):
                        # Override download_stories to False when only_highlights is True    
                        temp_config = self.config.copy()
                        temp_config['download_stories'] = False
                        temp_config['download_highlights'] = True
                        
                        # Save the original config
                        original_config = self.config
                        # Use the temporary config
                        self.config = temp_config
                        
                        success, message = self.download_stories_and_highlights(L, profile, target_dir)
                        
                        # Restore original config
                        self.config = original_config
                        
                        self.log_signal.emit(message, "INFO" if success else "ERROR")
                    else:
                        # Regular download of stories and highlights based on checkboxes
                        success, message = self.download_stories_and_highlights(L, profile, target_dir)
                        self.log_signal.emit(message, "INFO" if success else "ERROR")
                        
                except instaloader.exceptions.ProfileNotExistsException:
                    self.log_signal.emit(
                        f"Profile {self.config['target_profile']} does not exist or is private", 
                        "ERROR"
                    )
                except Exception as e:
                    logger.error(f"Error in profile download: {str(e)}")
                    logger.error(traceback.format_exc())
                    self.log_signal.emit(f"Error: {str(e)}", "ERROR")
                
        except Exception as e:
            logger.error(f"Fatal error in downloader thread: {str(e)}")
            logger.error(traceback.format_exc())
            self.log_signal.emit(f"Error: {str(e)}", "ERROR")
        finally:
            if 'original_cwd' in locals():
                os.chdir(original_cwd)
            logger.info("Download thread finished execution")
            # Always emit the stopped signal if it was manually stopped
            if self.is_stopped:
                self.stopped_signal.emit()
            # Always emit finished to ensure proper UI update
            self.finished.emit()



class ProfileCheckThread(QThread):
    """
    Thread for asynchronously verifying Instagram profile existence.

    This thread performs a lightweight check to verify if an Instagram profile
    exists and retrieves basic profile information without downloading content.

    Signals:
        result_signal (bool, str): Emits (exists, name/error_message)
            - exists: True if profile exists
            - name: Profile's full name if exists, error message if not

    Attributes:
        username (str): Instagram username to check
    """
    result_signal = pyqtSignal(bool, str)
    
    def __init__(self, username):
        super().__init__()
        self.username = username
        self.logger = get_logger()  # Get logger instance
        
    def run(self):
        try:
            self.logger.info(f"Checking profile name for: {self.username}")
            # Create a temporary Instaloader instance
            L = instaloader.Instaloader(quiet=True, download_pictures=False, download_videos=False)
            
            # Try to get the profile
            profile = instaloader.Profile.from_username(L.context, self.username)
            
            # If we get here, the profile exists. Get the full name
            full_name = profile.full_name if profile.full_name else "No name provided"
            self.logger.info(f"Profile found: {self.username} ({full_name})")
            
            # Success - emit the signal with the result
            self.result_signal.emit(True, full_name)
            
        except instaloader.exceptions.ProfileNotExistsException:
            self.logger.error(f"Profile doesn't exist: {self.username}")
            self.result_signal.emit(False, "Profile doesn't exist")
        except instaloader.exceptions.ConnectionException:
            self.logger.error(f"Connection error while checking profile: {self.username}")
            self.result_signal.emit(False, "Connection error")
        except instaloader.exceptions.QueryReturnedNotFoundException:
            self.logger.error(f"Profile not found: {self.username}")
            self.result_signal.emit(False, "Profile not found")
        except instaloader.exceptions.LoginRequiredException:
            self.logger.error(f"Login required to check profile: {self.username}")
            self.result_signal.emit(False, "Login required to check")
        except Exception as e:
            self.logger.error(f"Error checking profile {self.username}: {str(e)}")
            self.result_signal.emit(False, f"Error: {str(e)[:30]}")
