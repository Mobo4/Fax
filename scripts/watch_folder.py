#!/usr/bin/env python3
"""
Hot Folder Watcher for Faxing

Monitors a directory for PDF files with phone numbers as filenames.
When a file is detected (e.g., "+15551234567.pdf"), it:
1. Validates the filename as a phone number
2. Moves it to 'processing'
3. Sends via Telnyx
4. Archives to 'sent' or 'errors'

Usage:
    python scripts/watch_folder.py --watch data/fax_drop_box
"""

import os
import sys
import shutil
import time
import argparse
import re
from pathlib import Path
from datetime import datetime
import structlog
from dotenv import load_dotenv

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load environment variables
load_dotenv(PROJECT_ROOT / ".env")

# Configure logging
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer()
    ],
)
logger = structlog.get_logger()

def sanitize_phone_number(filename_stem: str) -> str:
    """
    Extracts cleaner phone number from filename.
    Allowed: +15551234567.pdf -> +15551234567
    Allowed: 15551234567.pdf -> +15551234567
    Allowed: 555-123-4567.pdf -> +15551234567 (Assumes US +1)
    """
    # Remove all non-digits
    digits = re.sub(r"\D", "", filename_stem)
    
    # Check length
    if len(digits) == 10:
        return f"+1{digits}"
    elif len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    else:
        raise ValueError(f"Invalid phone number length: {len(digits)} digits")

def move_file(src: Path, dest_dir: Path) -> Path:
    """Move file to destination, handling collisions."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / src.name
    
    # Handle collision
    if dest_path.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest_path = dest_dir / f"{src.stem}_{timestamp}{src.suffix}"
        
    shutil.move(src, dest_path)
    return dest_path

def process_file(file_path: Path):
    """Process a single file found in the drop box."""
    logger.info("file_detected", file=file_path.name)
    
    # Directories
    processing_dir = PROJECT_ROOT / "data" / "processing"
    sent_dir = PROJECT_ROOT / "data" / "outbox" / "sent"
    error_dir = PROJECT_ROOT / "data" / "errors"
    
    # 1. Move to processing (lock the file)
    try:
        working_path = move_file(file_path, processing_dir)
    except Exception as e:
        logger.error("file_move_failed", error=str(e))
        return

    # 2. Extract number
    try:
        to_number = sanitize_phone_number(file_path.stem)
        logger.info("number_extracted", number=to_number)
    except ValueError as e:
        logger.error("invalid_filename", error=str(e))
        move_file(working_path, error_dir)
        return

    # 3. Send Fax
    try:
        from scripts.send_fax import send_fax_telnyx
        
        # Check if dry run (can be toggled via env if needed, defaulting to real send)
        # Assuming this script is for production use
        
        result = send_fax_telnyx(to_number, working_path)
        logger.info("fax_sent_successfully", fax_id=result.get("fax_id"))
        
        # 4. Archive
        move_file(working_path, sent_dir)
        
    except Exception as e:
        logger.error("fax_send_failed", error=str(e))
        move_file(working_path, error_dir)

def watch_loop(watch_dir: Path):
    """Poll directory for new files."""
    logger.info("watcher_started", directory=str(watch_dir))
    
    while True:
        try:
            # List PDF files
            files = [f for f in watch_dir.iterdir() if f.is_file() and f.suffix.lower() == ".pdf"]
            
            for f in files:
                # Wait a moment to ensure write is complete (basic debounce)
                time.sleep(1) 
                process_file(f)
                
            time.sleep(5)  # Poll interval
            
        except KeyboardInterrupt:
            logger.info("watcher_stopped")
            break
        except Exception as e:
            logger.error("loop_error", error=str(e))
            time.sleep(5)

def main():
    parser = argparse.ArgumentParser(description="Watch Folder Fax Sender")
    parser.add_argument("--watch", default="data/fax_drop_box", help="Directory to watch")
    args = parser.parse_args()
    
    watch_dir = PROJECT_ROOT / args.watch
    watch_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"👀 Watching folder: {watch_dir}")
    print("👉 Drop PDF files named like '17145551234.pdf' to send immediately.")
    print("❌ Press Ctrl+C to stop.")
    
    watch_loop(watch_dir)

if __name__ == "__main__":
    main()
