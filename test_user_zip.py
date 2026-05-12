import os
import zipfile
import tempfile
import shutil
import glob
from shipping_logic import extract_shipping_details_llm, classify_document

zip_path = "/Users/growmax/Personal/Shipping Docs/BKG_460536_20260512144828811.zip"
temp_dir = tempfile.mkdtemp()

try:
    print(f"Extracting {zip_path}...")
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(temp_dir)
    
    pdfs = glob.glob(os.path.join(temp_dir, "**", "*.[pP][dD][fF]"), recursive=True)
    pdfs = [p for p in pdfs if not os.path.basename(p).startswith('.')]
    
    print(f"Found {len(pdfs)} PDFs: {[os.path.basename(p) for p in pdfs]}")
    
    for p in pdfs:
        doc_type = classify_document(os.path.basename(p))
        print(f"\n--- Processing {os.path.basename(p)} (Type: {doc_type}) ---")
        try:
            results = extract_shipping_details_llm(p)
            if results:
                print(f"SUCCESS! Extracted: Cartons={results.get('cartons', {}).get('value')}, Weight={results.get('gross_weight', {}).get('value')}")
            else:
                print("FAILED: Extraction returned None")
        except Exception as e:
            print(f"ERROR: {e}")

finally:
    shutil.rmtree(temp_dir)
