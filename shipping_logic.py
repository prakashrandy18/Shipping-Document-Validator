import os
import time
import json
import csv
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure Gemini Client
try:
    from google import genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False
    print("Warning: google-genai not installed.")

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

def classify_document(filename):
    """
    Classify document type based on filename patterns provided by the user.
    Returns: 'doc_a' (BL), 'doc_b' (Invoice), 'doc_c' (Packing List), or None
    """
    name = filename.lower()
    
    # 1. Invoice (doc_b)
    if name.endswith('inv.pdf'): return 'doc_b'
    if name.startswith(('invoice', 'inv', 'in ', 'td inv')): return 'doc_b'
    
    # 2. Bill of Lading (doc_a)
    if name.startswith(('obl', 'bl')): return 'doc_a'
    
    # 3. Packing List (doc_c)
    if name.startswith(('pl', 'plist', 'packing', 'pack')): return 'doc_c'
    
    # -- Loose Contains Checks (Lower Priority) --
    if 'inv' in name or 'invoice' in name: return 'doc_b'
    if 'bl' in name or 'obl' in name: return 'doc_a'
    if 'pl' in name or 'plist' in name or 'packing' in name: return 'doc_c'
    
    return None

client = None
if GENAI_AVAILABLE and GOOGLE_API_KEY:
    client = genai.Client(api_key=GOOGLE_API_KEY)
else:
    print("Warning: GOOGLE_API_KEY not found or google-genai missing.")


# ============================================================================
# CONFIGURATION - Fields to Extract & Compare
# ============================================================================

FIELD_CONFIG = {
    'cartons': {
        'label': 'Cartons (CTN)',
    },
    'gross_weight': {
        'label': 'Gross Weight (KGS)',
    },
    'cbm': {
        'label': 'Volume (CBM)',
    },
}


def load_rules(filename):
    """
    Load specific rules from rules.csv if the filename matches a pattern.
    """
    context = ""
    try:
        csv_path = os.path.join(os.path.dirname(__file__), 'rules.csv')
        if not os.path.exists(csv_path):
            return ""

        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            rules = []
            for row in reader:
                # If keyword is in filename (case-insensitive)
                if row['Keyword'].lower() in filename.lower():
                    rules.append(f"- RULE: For field '{row['Field']}', {row['Action']} '{row['Value']}'")
            
            if rules:
                context = "\n    APPLICABLE RULES FROM KNOWLEDGE BASE:\n    " + "\n    ".join(rules)
    except Exception as e:
        print(f"Error loading rules: {e}")
    
    return context
def extract_shipping_details_llm(file_path):
    """
    Extract shipping details using Google Gemini 1.5 Flash (Multimodal).
    Uploads the PDF directly so the model can 'see' the layout.
    """
    if not GENAI_AVAILABLE:
        raise ImportError("google-genai library not available")
    
    if not client:
        raise ValueError("Gemini Client not initialized. Check API Key.")

    print(f"Uploading file to Gemini: {file_path}")
    
    # 1. Upload the file
    uploaded_file = None
    try:
        uploaded_file = client.files.upload(file=file_path)
        print(f"File uploaded: {uploaded_file.name}")
    except Exception as e:
        raise Exception(f"Failed to upload file to Gemini: {e}")

    # 2. Get Rulebook Context (Safe Add-on)
    rulebook_context = load_rules(os.path.basename(file_path))

    # 3. Define the Prompt (Standard + Rules)
    prompt = f"""
    You are an expert Shipping Document Analyst. 
    Analyze the visual layout of this document to extract shipping details.
    
    {rulebook_context}
    
    -------------------------------------
    CRITICAL RULE: DISTINGUISH "CARTONS" FROM "PIECES" / "GARMENTS"
    - Documents often list "Total PCS", "Total Garments Quantity", and "Total CTNS".
    - You MUST select the **CARTON** count (Unit: CTN, Cartons, PKGS).
    - You MUST IGNORE:
      - "Total PCS"
      - "Total Garments Quantity"
      - "Total Assort Quantity"
      - "Total Qty" (unless it explicitly says Cartons)
    
    STEP 1: LOCATE TOTALS
    - First, look for the column header **"CTN QTY"**, **"CTNS"**, or **"CARTONS"**.
    - Find the value in the **TOTAL** row that corresponds to this column.
    - Example: If the table has "CTN QTY" (2195) and "TOTAL GARMENTS QUANTITY" (13170), YOU MUST PICK 2195.
    
    STEP 2: CHECK SUMMARY TABLES
    - Often there is a small "CARTON MEAS" table at the bottom.
    - It usually lists "CTN" (e.g. 2195) and "CBM". Use this to Cross-Verify.
    
    -------------------------------------
    
    -------------------------------------
    CRITICAL PATTERN RECOGNITION RULES (FOR LEVI'S / SUMMARY TABLES):

    1. **"NUMBER OF PACKING UNITS" (Levi's Style)**:
       - If you see the text "Outer Packing Method" and "Number Of Packing Units", the value under "Number Of Packing Units" IS THE CARTON COUNT.
       - Example:
         Outer Packing Method: Carton
         Number Of Packing Units: 16
         -> Cartons = 16.

    2. **SUMMARY TABLES ("GROSS" / "VOL")**:
       - In "PO Summary" or "Equipment Summary" tables:
       - Column "Gross" = Gross Weight (KGS).
       - Column "Vol" = Volume (CBM).
       - Use these values if specific "Total Gross Weight" headers are missing.

    3. **OBL "PALLET" vs "CARTON" RULE**:
       - If the "No. of Pkgs" column says "1 PALLET" (or Skid), DO NOT return 1.
       - You MUST look in the Description field for "STC" (Said To Contain) or "CTNS".
       - Example: "1 PALLET ... STC 16 CTNS". -> Cartons = 16.
    -------------------------------------
    
    STEP 2: LOCATE GROSS WEIGHT (CRITICAL)
    - You must find the **GROSS WEIGHT**.
    - IGNORE "Net Weight", "N.W.", or "LBS" if "KGS" is present.
    - LOOK FOR HEADERS: "GROSS WEIGHT", "G.W.", "TTL GROSS WT.", "GR.WT.".
    - If you see "TTL NET WT." and "TTL GROSS WT.", YOU MUST PICK "TTL GROSS WT.".
    - Example: Net Wt: 449.25, Gross Wt: 590.47 -> You MUST pick 590.47.

    STEP 3: ANALYZE SUMMARY SECTIONS
    - Look for a separate "Summary" or "Carton Meas" table, often at the bottom left.
    - Find "CBM" or "Vol" in this summary table. **This is the Volume (e.g., 10.611).**
    
    -------------------------------------
    REQUIRED OUTPUT (JSON ONLY):
    {{
      "_analysis": "Explain why you chose value X over Y. Mention if you saw 'Total PCS' vs 'Total CTNS'.",
      "bl_number": "String or null (The Bill of Lading Number / Waybill Number)",
      "assort_quantity": Number or null (Ignored, but note if confusing),
      "cartons": Number or null (The CARTON count. Do NOT pick PCS),
      "gross_weight": Number or null,
      "cbm": Number or null
    }}
    -------------------------------------
    """

    models_to_try = [
        'gemini-2.0-flash',
        'gemini-2.0-flash-lite-preview-02-05',
    ]

    start_time = time.time()
    response = None
    last_error = None
    used_model = None

    for model_name in models_to_try:
        try:
            print(f"Analyzing with model: {model_name}")
            response = client.models.generate_content(
                model=model_name,
                contents=[uploaded_file, prompt]
            )
            if response:
                print(f"Success with {model_name}")
                used_model = model_name
                break
        except Exception as e:
            print(f"Model {model_name} failed: {e}")
            last_error = e
    
    end_time = time.time()
    duration_ms = int((end_time - start_time) * 1000)

    if not response:
        error_msg = str(last_error) if last_error else "Unknown error"
        if "Quota" in error_msg or "429" in error_msg:
             raise Exception("Google Gemini API Quota Exceeded. Please wait a few minutes.")
        raise Exception(f"All Gemini models failed. Last error: {error_msg}")

    try:    
        # Clean response text
        response_text = response.text.replace('```json', '').replace('```', '').strip()
        data = json.loads(response_text)
        
        # --- HEURISTIC VALIDATION ---
        # 1. Cartons vs Weight Sanity Check
        # If we have heavy goods (>500kg) but only <50 cartons, it's highly likely we picked "Assort Qty" (e.g. 6) instead of Cartons.
        try:
            c_val = float(data.get('cartons')) if data.get('cartons') else 0
            w_val = float(data.get('gross_weight')) if data.get('gross_weight') else 0
            
            if c_val > 0 and c_val < 50 and w_val > 500:
                print(f"Heuristic Triggered: Cartons ({c_val}) is suspicious for Weight ({w_val}). Values might be mismatched. Preferring Null over wrong value.")
                data['cartons'] = None # Invalidating it forces user to check or allows 'partial' match state
        except:
            pass
        # -----------------------------
        
        # Extract Token Usage if available
        usage = {}
        if hasattr(response, 'usage_metadata'):
            usage = {
                'input_tokens': response.usage_metadata.prompt_token_count,
                'output_tokens': response.usage_metadata.candidates_token_count,
                'total_tokens': response.usage_metadata.total_token_count
            }

        # Map to App's structure
        results = {
            'meta': {
                'model': used_model,
                'duration_ms': duration_ms,
                'usage': usage
            }
        }
        
        # BL Number (New)
        if data.get('bl_number'):
            results['bl_number'] = str(data.get('bl_number')).strip()
        
        results['cartons'] = {
            'label': 'Cartons (CTN)',
            'value': data.get('cartons'),
            'confidence': 1.0,
            'needs_user_input': data.get('cartons') is None,
            'source': 'gemini_vision'
        }
        
        results['gross_weight'] = {
            'label': 'Gross Weight (KGS)',
            'value': data.get('gross_weight'),
            'confidence': 1.0,
            'needs_user_input': data.get('gross_weight') is None,
            'source': 'gemini_vision'
        }
        
        results['cbm'] = {
            'label': 'Volume (CBM)',
            'value': data.get('cbm'),
            'confidence': 1.0,
            'needs_user_input': data.get('cbm') is None,
            'source': 'gemini_vision'
        }

        print(f"Vision Extraction Results: {json.dumps(data)}")
        return results
        
    except Exception as e:
        print(f"Parsing failed: {e}")
        return None



def compare_three_documents(details_a, details_b, details_c):
    """Compare shipping details from three documents."""
    results = {
        'all_match': True,
        'comparisons': []
    }
    
    for field_key in FIELD_CONFIG.keys():
        val_a = details_a.get(field_key, {}).get('value')
        val_b = details_b.get(field_key, {}).get('value')
        val_c = details_c.get(field_key, {}).get('value')
        
        label = FIELD_CONFIG[field_key]['label']
        
        # Normalize values for comparison
        values = [val_a, val_b, val_c]
        non_null_values = [v for v in values if v is not None]
        
        if len(non_null_values) == 0:
            # All missing
            comparison = {
                'field': label,
                'field_key': field_key,
                'status': 'warning',
                'message': 'No values found in any document',
                'values': {'doc_a': None, 'doc_b': None, 'doc_c': None}
            }
        elif len(set(str(v) for v in non_null_values)) == 1:
            # All matching (ignoring None)
            missing_docs = []
            if val_a is None:
                missing_docs.append('A')
            if val_b is None:
                missing_docs.append('B')
            if val_c is None:
                missing_docs.append('C')
            
            if missing_docs:
                results['all_match'] = False
                comparison = {
                    'field': label,
                    'field_key': field_key,
                    'status': 'partial',
                    'message': f'Match (Doc {", ".join(missing_docs)} missing)',
                    'matched_value': non_null_values[0],
                    'values': {'doc_a': val_a, 'doc_b': val_b, 'doc_c': val_c}
                }
            else:
                comparison = {
                    'field': label,
                    'field_key': field_key,
                    'status': 'success',
                    'matched_value': val_a,
                    'values': {'doc_a': val_a, 'doc_b': val_b, 'doc_c': val_c}
                }
        else:
            # Mismatch
            results['all_match'] = False
            comparison = {
                'field': label,
                'field_key': field_key,
                'status': 'error',
                'values': {'doc_a': val_a, 'doc_b': val_b, 'doc_c': val_c}
            }
        
        results['comparisons'].append(comparison)
    
    return results


def extract_combined_shipping_details_llm(file_path):
    """
    Extract shipping details from a COMBINED PDF (containing OBL, Invoice, Packing List).
    Uses Gemini to 'logically split' the document and extract 3 sets of data.
    """
    if not GENAI_AVAILABLE:
        raise ImportError("google-genai library not available")
    
    if not client:
        raise ValueError("Gemini Client not initialized. Check API Key.")

    print(f"Uploading COMBINED file to Gemini: {file_path}")
    
    # 1. Upload
    uploaded_file = None
    try:
        uploaded_file = client.files.upload(file=file_path)
        print(f"File uploaded: {uploaded_file.name}")
    except Exception as e:
        raise Exception(f"Failed to upload to Gemini: {e}")

    # 2. Prompt
    prompt = """
    You are an expert Shipping Document Analyst.
    This PDF file contains THREE DISTINCT DOCUMENTS merged together:
    1. Bill of Lading (OBL or Waybill)
    2. Commercial Invoice (Inv)
    3. Packing List (PKL or P/L)

    YOUR TASK:
    Logically identify the pages belonging to each document type and extract the following fields for EACH document:
    - Cartons (CTN / Packages)
    - Gross Weight (KGS)
    - Volume (CBM)
    - **Document Number** (Specifically BL Number for the BL)

    *** CHAIN OF THOUGHT REQUIRED ***
    For each document, you must internally:
    1. Identify the document type.
    2. Scan for "Total" rows in main tables.
    3. Scan for "Summary" tables (often at the bottom).
    4. Apply the Critical Rules below.

    CRITICAL RULES - READ CAREFULLY:

    1. **INVOICE SEARCH STRATEGY**:
       - **Cartons**: Look for "Number Of Packing Units". If found, THAT IS THE CARTON COUNT.
         - *Levi's Pattern*: "Outer Packing Method: Carton" -> "Number Of Packing Units: 16". Pick 16.
       - **Weight**: Look for "Gross Weight", "GR.WT", or "Total Gross Weight".

    2. **PACKING LIST SEARCH STRATEGY**:
       - **Cartons**: Look for "Total Ctns", "Total Cartons".
       - **Weight**: Check the "Totals" row or "Summary" table.
         - **Header "Gross"**: If a column header is just "Gross" (e.g. in 'PO Summary' or 'Equipment Summary'), use the Total value from that column.
       - **Volume**: Check for "Vol" or "CBM" or "M3".
         - **Header "Vol"**: If a column header is just "Vol", use the Total value from that column.

    3. **BILL OF LADING STRATEGY**:
       - Usually clearly labeled "No. of Pkgs" (Cartons) and "Gross Weight".
       - **CRITICAL**: If "No. of Pkgs" says "1 PALLET", **IGNORE IT**.
         - Look for "STC" (Said To Contain) in the description.
         - Text: "1 PALLET ... STC 16 CTNS". Result: 16.
         - Text: "1 SKID ... STC 500 PCS". Result: 500 (if no other Carton count exists).

    4. **GENERAL**: 
       - If a value is missing in the main table, LOOK AT THE BOTTOM SUMMARY.
       - Do not cross-contaminate data between documents.

    OUTPUT JSON FORMAT:
    {
      "doc_a": { "_type": "Bill of Lading", "_thought": "Found text '...', chose X", "bl_number": "String/null", "cartons": Number/null, "gross_weight": Number/null, "cbm": Number/null },
      "doc_b": { "_type": "Invoice",        "_thought": "Found 'Number Of Packing Units'...", "cartons": Number/null, "gross_weight": Number/null, "cbm": Number/null },
      "doc_c": { "_type": "Packing List",   "_thought": "Found 'PO Summary' table...", "cartons": Number/null, "gross_weight": Number/null, "cbm": Number/null }
    }
    """

    models_to_try = [
        'gemini-2.0-flash',
        'gemini-2.0-flash-lite-preview-02-05',
    ]

    response = None
    last_error = None
    used_model = None

    for model_name in models_to_try:
        try:
            print(f"Analyzing Combined PDF with: {model_name}")
            response = client.models.generate_content(
                model=model_name,
                contents=[uploaded_file, prompt]
            )
            if response:
                used_model = model_name
                break
        except Exception as e:
            print(f"Model {model_name} failed: {e}")
            last_error = e

    if not response:
        raise Exception(f"Gemini Analysis Failed: {last_error}")

    try:
        # Parse JSON
        text = response.text.replace('```json', '').replace('```', '').strip()
        data = json.loads(text)
        
        # Convert to App Standard Format (normalized)
        results = {}
        for key in ['doc_a', 'doc_b', 'doc_c']:
            raw = data.get(key, {})
            # Extract BL Number if it's doc_a
            bl_num = raw.get('bl_number') if key == 'doc_a' else None
            
            results[key] = {
                'details': {
                    'cartons': {'value': raw.get('cartons'), 'label': 'Cartons'},
                    'gross_weight': {'value': raw.get('gross_weight'), 'label': 'Gross Weight'},
                    'cbm': {'value': raw.get('cbm'), 'label': 'Volume'}
                }
            }
            if bl_num:
                results[key]['details']['bl_number'] = str(bl_num).strip()
        
        return results

    except Exception as e:
        print(f"JSON Parse Error: {e} | Text: {response.text}")
        raise Exception("Failed to parse AI response")
