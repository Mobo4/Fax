#!/usr/bin/env python3
"""
OCR Processor for Incoming Faxes

Process incoming faxes with Google Cloud Vision OCR, extract text,
and optionally match to patient records.

Usage:
    # Process single fax
    python scripts/ocr_processor.py --input data/inbox/fax_123.pdf
    
    # Process all faxes in inbox
    python scripts/ocr_processor.py --input data/inbox --batch
    
    # Process with patient matching
    python scripts/ocr_processor.py --input data/inbox --batch --match-patients
"""

import os
import sys
import json
import argparse
import re
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


def ocr_with_google_vision(file_path: Path) -> str:
    """Extract text from PDF/image using Google Cloud Vision API."""
    try:
        from google.cloud import vision
    except ImportError:
        logger.warning("google_cloud_vision_not_installed")
        return "(OCR requires google-cloud-vision package)"
    
    client = vision.ImageAnnotatorClient()
    
    # Read file
    with open(file_path, "rb") as f:
        content = f.read()
    
    # For PDFs, use document_text_detection
    if file_path.suffix.lower() == ".pdf":
        # Google Vision requires specific handling for PDFs
        # For multi-page PDFs, we'd normally use async batch processing
        # This is simplified for single-page or small PDFs
        image = vision.Image(content=content)
        response = client.document_text_detection(image=image)
        
        if response.error.message:
            raise Exception(f"Vision API error: {response.error.message}")
        
        return response.full_text_annotation.text
    else:
        # For images (TIFF, PNG, etc.)
        image = vision.Image(content=content)
        response = client.text_detection(image=image)
        
        if response.error.message:
            raise Exception(f"Vision API error: {response.error.message}")
        
        texts = response.text_annotations
        return texts[0].description if texts else ""


def ocr_fallback(file_path: Path) -> str:
    """Fallback OCR using pytesseract if Google Vision not available."""
    try:
        import pytesseract
        from pdf2image import convert_from_path
        from PIL import Image
    except ImportError:
        return "(OCR requires pytesseract and pdf2image packages as fallback)"
    
    if file_path.suffix.lower() == ".pdf":
        # Convert PDF to images
        images = convert_from_path(file_path)
        text_parts = []
        for i, image in enumerate(images):
            text = pytesseract.image_to_string(image)
            text_parts.append(f"--- Page {i+1} ---\n{text}")
        return "\n\n".join(text_parts)
    else:
        # Process image directly
        image = Image.open(file_path)
        return pytesseract.image_to_string(image)


def extract_patient_info(text: str) -> dict:
    """Extract patient information from OCR text using pattern matching."""
    info = {
        "patient_name": None,
        "date_of_birth": None,
        "phone": None,
        "mrn": None,
        "insurance": None,
        "referring_provider": None
    }
    
    # Patient name patterns
    name_patterns = [
        r"Patient(?:\s+Name)?[:\s]+([A-Za-z]+(?:\s+[A-Za-z]+)+)",
        r"Name[:\s]+([A-Za-z]+(?:,?\s+[A-Za-z]+)+)",
        r"RE[:\s]+([A-Za-z]+(?:\s+[A-Za-z]+)+)",
    ]
    for pattern in name_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            info["patient_name"] = match.group(1).strip()
            break
    
    # Date of birth patterns
    dob_patterns = [
        r"(?:DOB|Date of Birth|Birth Date)[:\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"(?:DOB|Date of Birth)[:\s]+([A-Za-z]+\s+\d{1,2},?\s+\d{4})",
    ]
    for pattern in dob_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            info["date_of_birth"] = match.group(1).strip()
            break
    
    # Phone number patterns
    phone_patterns = [
        r"(?:Phone|Tel|Telephone)[:\s]+(\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})",
        r"(\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4})",
    ]
    for pattern in phone_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            info["phone"] = match.group(1).strip()
            break
    
    # MRN patterns
    mrn_patterns = [
        r"(?:MRN|Medical Record|Patient ID)[:\s#]+(\d+)",
        r"(?:Chart|Account)[:\s#]+(\d+)",
    ]
    for pattern in mrn_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            info["mrn"] = match.group(1).strip()
            break
    
    # Insurance patterns
    insurance_patterns = [
        r"(?:Insurance|Ins|Carrier)[:\s]+([A-Za-z]+(?:\s+[A-Za-z]+)*)",
    ]
    for pattern in insurance_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            info["insurance"] = match.group(1).strip()
            break
    
    # Referring provider patterns
    referring_patterns = [
        r"(?:Referring|From|Sender)[:\s]+(?:Dr\.?\s+)?([A-Za-z]+(?:\s+[A-Za-z]+)*)",
    ]
    for pattern in referring_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            info["referring_provider"] = match.group(1).strip()
            break
    
    return info


def fuzzy_match_patient(patient_info: dict) -> Optional[dict]:
    """
    Attempt to match extracted info to existing patient records.
    This is a placeholder - integrate with your EHR/CRM system.
    """
    # In a real implementation, this would:
    # 1. Connect to your patient database
    # 2. Use fuzzy matching (RapidFuzz) on name
    # 3. Verify with DOB and/or phone
    # 4. Return matched patient record or None
    
    # Placeholder implementation
    if patient_info.get("patient_name"):
        logger.info("patient_match_attempt", name=patient_info["patient_name"])
        
        # Example: Load from a simple JSON patient database
        patient_db_path = PROJECT_ROOT / "data" / "patients.json"
        if patient_db_path.exists():
            try:
                from rapidfuzz import fuzz
                
                with open(patient_db_path) as f:
                    patients = json.load(f)
                
                # Find best match
                best_match = None
                best_score = 0
                
                for patient in patients:
                    score = fuzz.ratio(
                        patient_info["patient_name"].lower(),
                        patient.get("name", "").lower()
                    )
                    if score > best_score and score >= 80:
                        best_score = score
                        best_match = patient
                
                if best_match:
                    logger.info("patient_matched", 
                               name=best_match["name"], 
                               score=best_score)
                    return {**best_match, "match_score": best_score}
                    
            except ImportError:
                logger.warning("rapidfuzz_not_installed")
            except Exception as e:
                logger.error("patient_matching_error", error=str(e))
    
    return None


def save_ocr_result(
    source_path: Path,
    text: str,
    patient_info: dict,
    matched_patient: Optional[dict]
) -> Path:
    """Save OCR results to staging directory."""
    staging_dir = PROJECT_ROOT / "staging" / "ocr_output"
    staging_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"{timestamp}_{source_path.stem}"
    
    result = {
        "source_file": str(source_path),
        "processed_at": datetime.now().isoformat(),
        "extracted_text": text,
        "text_length": len(text),
        "patient_info": patient_info,
        "matched_patient": matched_patient,
        "status": "matched" if matched_patient else "unmatched"
    }
    
    output_path = staging_dir / f"{base_name}.json"
    output_path.write_text(json.dumps(result, indent=2))
    
    # Also save plain text for easy viewing
    text_path = staging_dir / f"{base_name}.txt"
    text_path.write_text(text)
    
    return output_path


def process_single_fax(file_path: Path, match_patients: bool = False) -> dict:
    """Process a single fax file with OCR."""
    logger.info("processing_fax", path=str(file_path))
    
    # Run OCR
    try:
        text = ocr_with_google_vision(file_path)
    except Exception as e:
        logger.warning("google_vision_failed", error=str(e))
        text = ocr_fallback(file_path)
    
    # Extract patient info
    patient_info = extract_patient_info(text)
    
    # Match to patient if requested
    matched_patient = None
    if match_patients:
        matched_patient = fuzzy_match_patient(patient_info)
    
    # Save results
    output_path = save_ocr_result(
        source_path=file_path,
        text=text,
        patient_info=patient_info,
        matched_patient=matched_patient
    )
    
    return {
        "source": str(file_path),
        "output": str(output_path),
        "patient_info": patient_info,
        "matched": matched_patient is not None,
        "text_preview": text[:200] + "..." if len(text) > 200 else text
    }


def main():
    parser = argparse.ArgumentParser(description="OCR Processor for Incoming Faxes")
    parser.add_argument("--input", required=True, help="Input file or directory")
    parser.add_argument("--batch", action="store_true", help="Process all files in directory")
    parser.add_argument("--match-patients", action="store_true", help="Attempt patient matching")
    parser.add_argument("--extensions", default=".pdf,.tiff,.tif,.png,.jpg", 
                       help="File extensions to process (comma-separated)")
    args = parser.parse_args()
    
    input_path = Path(args.input)
    extensions = tuple(args.extensions.split(","))
    
    if not input_path.exists():
        print(f"❌ Path not found: {input_path}")
        sys.exit(1)
    
    files_to_process = []
    
    if input_path.is_file():
        files_to_process = [input_path]
    elif args.batch:
        files_to_process = [
            f for f in input_path.iterdir()
            if f.is_file() and f.suffix.lower() in extensions
        ]
    else:
        print("❌ Specify --batch to process all files in directory")
        sys.exit(1)
    
    if not files_to_process:
        print("⚠️  No files to process")
        sys.exit(0)
    
    print(f"\n📄 Processing {len(files_to_process)} file(s)...")
    print(f"   Patient matching: {'enabled' if args.match_patients else 'disabled'}\n")
    
    results = []
    
    for i, file_path in enumerate(files_to_process, 1):
        print(f"[{i}/{len(files_to_process)}] {file_path.name}")
        
        try:
            result = process_single_fax(file_path, args.match_patients)
            results.append(result)
            
            status = "✅ Matched" if result["matched"] else "📋 Processed"
            print(f"   {status}: {result['output']}")
            
            if result["patient_info"]["patient_name"]:
                print(f"   Patient: {result['patient_info']['patient_name']}")
                
        except Exception as e:
            logger.exception("processing_error", file=str(file_path))
            print(f"   ❌ Error: {e}")
    
    # Summary
    matched = sum(1 for r in results if r.get("matched"))
    print(f"\n{'='*60}")
    print(f"✅ Processed: {len(results)} file(s)")
    print(f"👤 Matched to patients: {matched}")
    print(f"📁 Output: staging/ocr_output/")


if __name__ == "__main__":
    main()
