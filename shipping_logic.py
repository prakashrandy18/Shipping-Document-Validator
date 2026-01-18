import os
import time
import json
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
    if name.startswith(('pl', 'plist')): return 'doc_c'
    
    # -- Loose Contains Checks (Lower Priority) --
    if 'inv' in name or 'invoice' in name: return 'doc_b'
    if 'bl' in name: return 'doc_a'
    if 'pl' in name or 'plist' in name: return 'doc_c'
    
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

    # 2. Define the Prompt
    prompt = """
    You are an expert Shipping Document Analyst. 
    Analyze the visual layout of this document to extract shipping details.
    
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
    
    STEP 2: ANALYZE SUMMARY SECTIONS
    - Look for a separate "Summary" or "Carton Meas" table, often at the bottom left.
    - Find "CBM" or "Vol" in this summary table. **This is the Volume (e.g., 10.611).**
    
    -------------------------------------
    REQUIRED OUTPUT (JSON ONLY):
    {
      "_analysis": "Explain why you chose value X over Y. Mention if you saw 'Total PCS' vs 'Total CTNS'.",
      "assort_quantity": Number or null (Ignored, but note if confusing),
      "cartons": Number or null (The CARTON count. Do NOT pick PCS),
      "gross_weight": Number or null,
      "cbm": Number or null
    }
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
