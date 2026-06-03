#!/usr/bin/env python3
"""
Google Drive Sync for Fax Archive

Upload faxes to Google Drive for archival and sharing.

Usage:
    # Sync archive folder to Google Drive
    python scripts/sync_gdrive.py --local data/archive --drive-folder incoming_faxes
    
    # Upload single file
    python scripts/sync_gdrive.py --file data/inbox/fax_123.pdf --drive-folder incoming_faxes
"""

import os
import sys
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
import structlog

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


def get_drive_service():
    """Initialize Google Drive API service."""
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError:
        raise ImportError("Install google-api-python-client and google-auth packages")
    
    # Check for credentials
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    creds_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    
    if creds_path and Path(creds_path).exists():
        credentials = service_account.Credentials.from_service_account_file(
            creds_path,
            scopes=["https://www.googleapis.com/auth/drive"]
        )
    elif creds_json:
        import json
        creds_info = json.loads(creds_json)
        credentials = service_account.Credentials.from_service_account_info(
            creds_info,
            scopes=["https://www.googleapis.com/auth/drive"]
        )
    else:
        raise ValueError(
            "Google credentials not found. Set GOOGLE_APPLICATION_CREDENTIALS "
            "or GOOGLE_SERVICE_ACCOUNT_JSON in .env"
        )
    
    return build("drive", "v3", credentials=credentials)


def find_or_create_folder(service, folder_name: str, parent_id: Optional[str] = None) -> str:
    """Find existing folder or create new one."""
    # Search for existing folder
    query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    if parent_id:
        query += f" and '{parent_id}' in parents"
    
    results = service.files().list(
        q=query,
        spaces="drive",
        fields="files(id, name)"
    ).execute()
    
    files = results.get("files", [])
    if files:
        return files[0]["id"]
    
    # Create folder
    file_metadata = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder"
    }
    if parent_id:
        file_metadata["parents"] = [parent_id]
    
    folder = service.files().create(
        body=file_metadata,
        fields="id"
    ).execute()
    
    logger.info("folder_created", name=folder_name, id=folder["id"])
    return folder["id"]


def upload_file(service, file_path: Path, folder_id: str) -> dict:
    """Upload a file to Google Drive."""
    from googleapiclient.http import MediaFileUpload
    
    file_metadata = {
        "name": file_path.name,
        "parents": [folder_id]
    }
    
    # Determine MIME type
    mime_types = {
        ".pdf": "application/pdf",
        ".tiff": "image/tiff",
        ".tif": "image/tiff",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".json": "application/json",
        ".txt": "text/plain",
        ".md": "text/markdown"
    }
    mime_type = mime_types.get(file_path.suffix.lower(), "application/octet-stream")
    
    media = MediaFileUpload(str(file_path), mimetype=mime_type, resumable=True)
    
    file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id, name, webViewLink"
    ).execute()
    
    logger.info("file_uploaded", name=file["name"], id=file["id"])
    
    return {
        "id": file["id"],
        "name": file["name"],
        "link": file.get("webViewLink")
    }


def sync_directory(service, local_dir: Path, folder_id: str, extensions: tuple) -> list:
    """Sync all files from local directory to Google Drive."""
    uploaded = []
    
    # Get list of existing files in Drive folder
    results = service.files().list(
        q=f"'{folder_id}' in parents and trashed=false",
        spaces="drive",
        fields="files(id, name)"
    ).execute()
    existing_files = {f["name"] for f in results.get("files", [])}
    
    # Upload new files
    for file_path in local_dir.iterdir():
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() not in extensions:
            continue
        if file_path.name in existing_files:
            logger.debug("file_exists_skipping", name=file_path.name)
            continue
        
        try:
            result = upload_file(service, file_path, folder_id)
            uploaded.append(result)
        except Exception as e:
            logger.error("upload_failed", file=file_path.name, error=str(e))
    
    return uploaded


def main():
    parser = argparse.ArgumentParser(description="Sync faxes to Google Drive")
    parser.add_argument("--local", help="Local directory to sync")
    parser.add_argument("--file", help="Single file to upload")
    parser.add_argument("--drive-folder", required=True, help="Google Drive folder name")
    parser.add_argument("--parent-folder-id", help="Parent folder ID in Drive")
    parser.add_argument("--extensions", default=".pdf,.tiff,.tif,.json",
                       help="File extensions to sync")
    args = parser.parse_args()
    
    if not args.local and not args.file:
        print("❌ Specify --local directory or --file to upload")
        sys.exit(1)
    
    try:
        service = get_drive_service()
    except Exception as e:
        print(f"❌ Failed to connect to Google Drive: {e}")
        sys.exit(1)
    
    # Find or create destination folder
    parent_id = args.parent_folder_id or os.getenv("GDRIVE_INCOMING_FOLDER_ID")
    folder_id = find_or_create_folder(service, args.drive_folder, parent_id)
    print(f"📁 Target folder: {args.drive_folder} (ID: {folder_id})")
    
    uploaded = []
    
    if args.file:
        file_path = Path(args.file)
        if not file_path.exists():
            print(f"❌ File not found: {file_path}")
            sys.exit(1)
        
        result = upload_file(service, file_path, folder_id)
        uploaded.append(result)
        
    elif args.local:
        local_dir = Path(args.local)
        if not local_dir.is_dir():
            print(f"❌ Directory not found: {local_dir}")
            sys.exit(1)
        
        extensions = tuple(args.extensions.split(","))
        uploaded = sync_directory(service, local_dir, folder_id, extensions)
    
    # Summary
    print(f"\n{'='*60}")
    print(f"✅ Uploaded {len(uploaded)} file(s)")
    
    for item in uploaded:
        print(f"   📄 {item['name']}")
        if item.get("link"):
            print(f"      🔗 {item['link']}")


if __name__ == "__main__":
    main()
