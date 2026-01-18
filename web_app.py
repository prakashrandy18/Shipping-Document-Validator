"""
Shipping Document Validator - Web Application
==============================================
A modern web application to compare shipping details across THREE PDF documents.
Supports smart extraction with robust regex pattern recognition.
"""

from flask import Flask, render_template, request, jsonify
import os
import re
import tempfile

# Try to import pdfplumber for PDF text extraction
try:
    import pdfplumber
    PDF_LIBRARY_AVAILABLE = True
except ImportError:
    PDF_LIBRARY_AVAILABLE = False

try:
    from google import genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False
    print("Warning: google-genai not installed.")

# Configure Gemini Client
GOOGLE_API_KEY = "AIzaSyCd8ol3dDo1YenSNbJ0SqkuRJcdRlZUz-I" # Hardcoded
if GENAI_AVAILABLE:
    client = genai.Client(api_key=GOOGLE_API_KEY)
    try:
        print("Available Gemini Models:")
        for m in client.models.list():
            print(f" - {m.name}")
    except Exception as e:
        print(f"Failed to list models: {e}")


app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # Max 16MB upload
app.config['UPLOAD_FOLDER'] = tempfile.gettempdir()

# ============================================================================
# EXTRACTION PATTERNS - Robust Regex for specific formats
# ============================================================================

EXTRACTION_PATTERNS = {
    'cartons': {
        'label': 'Cartons (CTN)',
        'patterns': [
            # User provided patterns
            (r'TOTAL:\s*PACKED\s+IN:\s*([\d,]+)\s*CARTONS?', 1.0),
            (r'NUMBER\s+AND\s+TYPES?\s+OF\s+PACKAGES?\s*([\d,]+)\s*CARTON\s*\(?S\)?', 1.0),
            (r'CTNS\s+([\d,]+)', 1.0),
            (r'TOTAL:?\s*([\d,]+)', 0.95),  # Matches "TOTAL: 1704" (First number in Total row)
            
            # General fallback patterns (kept for robustness)
            (r'([\d,]+)\s+CARTON\s*\(\s*S\s*\)', 0.95),
            (r'GRAND\s+TOTAL\s+CARTON\s+Q[\'\"]?TY[:\s]*([\d,]+)', 0.95),
            (r'TYPES?\s+OF\s+PACKAGE[:\s]*([\d,]+)', 0.9),
            (r'\(CTN\)[:\s]*([\d,]+(?:\.\d+)?)', 0.9),
            (r'TOTAL[:\s]*([\d,]+)\s*(?:CTNS?|CARTONS?)', 0.9),
            (r'CTN[:\s]+([\d,]+(?:\.\d+)?)', 0.85),
            (r'NUMBER\s+OF\s+CARTONS?[:\s]*([\d,]+)', 0.85),
        ],
        'min_value': 1,
        'max_value': 100000,
    },
    'gross_weight': {
        'label': 'Gross Weight (KGS)',
        'patterns': [
            # User provided patterns for tricky OCR/formatting
            (r'KGS\/GROSS\s*WEIGHT\s*([\d,]+(?:\.\d+)?)', 1.0),
            (r'GROSS\s*WEIGHT\s*\(?KS\)?\s*([\d,]+(?:\.\d+)?)', 1.0),
            (r'G\/W:\s*([\d,]+(?:\.\d+)?)\s*KGS?', 1.0),
            
            # OBL Fix: Mashed characters (e.g. "8264.40oKGS")
            (r'([\d,]+(?:\.\d+)?)[oO]?\s*KGS', 0.95),
            
            # PKL Fix: Columnar TOTAL row (Assume 2nd to last number is Gross Weight)
            # Matches: TOTAL: ... 7071.60 8264.40 48.823
            (r'(?m)TOTAL:.*?\s([\d,.]+)\s+[\d,.]+$', 0.9),

            # General fallback patterns
            (r'G/W:\s*([\d,]+(?:\.\d+)?)\s*KGS?', 0.95),
            (r'GROSS\s+WEIGHT\s*\(\s*KG\s*\)[:\s]*([\d,]+(?:\.\d+)?)', 0.95),
            (r'GRAND\s+TOTAL\s+GR\.?\s*WEIGHT[:\s]*([\d,]+(?:\.\d+)?)', 0.9),
            (r'G\.?\s*W\.?[:\s]*([\d,]+(?:\.\d+)?)\s*(?:KG|KGS)', 0.9),
            (r'GROSS\s*(?:WEIGHT|WT\.?|WGT\.?)[:\s]*([\d,]+(?:\.\d+)?)\s*(?:KG|KGS)?', 0.9),
        ],
        'min_value': 0.1,
        'max_value': 1000000,
    },
    'cbm': {
        'label': 'Volume (CBM)',
        'patterns': [
            # User provided patterns (handling OCR errors like 'lvleasurement')
            (r'lvleasurement\s*\(CBM\)\s*([\d,]+(?:\.\d+)?)', 1.0), 
            (r'CM\*CM\*CM\s*([\d,]+(?:\.\d+)?)', 1.0),
            
            # OBL Fix: Mashed characters (e.g. "48,823OCBM")
            (r'([\d,]+(?:\.\d+)?)[oO]?\s*CBM', 0.95),

            # PKL Fix: Columnar TOTAL row (Assume last number is CBM)
            (r'(?m)TOTAL:.*?\s([\d,.]+)$', 0.9),
            
            # General fallback patterns
            (r'MEASUREMENT\s*\(\s*CBM\s*\)[:\s]*([\d,]+(?:\.\d+)?)', 0.95),
            (r'GRAND\s+TOTAL\s+CBM[:\s]*([\d,]+(?:\.\d+)?)', 0.95),
            (r'\(CBM\)[:\s]*([\d,]+(?:\.\d+)?)', 0.9),
            (r'CBM\)?[:\s]+([\d,]+(?:\.\d+)?)', 0.9),
            (r'([\d,]+(?:\.\d+)?)\s*CBM\b', 0.85),
            (r'VOLUME[:\s]+([\d,]+(?:\.\d+)?)', 0.85),
            (r'([\d,]+(?:\.\d+)?)\s*M[3³]', 0.8),
        ],
        'min_value': 0.01,
        'max_value': 10000,
    },
}


def extract_text_from_pdf(pdf_path):
    """Extract text content from a PDF file."""
    if not PDF_LIBRARY_AVAILABLE:
        raise ImportError("pdfplumber library is not installed")
    
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except Exception as e:
        raise Exception(f"Error reading PDF: {str(e)}")
    
    return text


def extract_value_with_confidence(text, field_config, field_key):
    """
    Extract a value using pure Regex pattern matching with confidence scoring.
    """
    text_upper = text.upper()
    best_match = None
    best_confidence = 0.0
    best_source = ""
    
    for pattern, base_confidence in field_config['patterns']:
        # Use case-insensitive matching
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            # Handle dimension tuples (if any remain)
            if isinstance(match, tuple):
                value = f"{match[0]}x{match[1]}x{match[2]}"
                value = re.sub(r'\s+', '', value).replace('×', 'x').replace('X', 'x')
            else:
                value = match.strip()
            
            # Clean up potential OCR noise from value
            # e.g. "8264.4AA" -> "8264.4"
            # Keep only digits, dots, and commas
            cleaned_value_match = re.match(r'^([\d\.,]+)', value)
            if cleaned_value_match:
                value = cleaned_value_match.group(1)
            
            try:
                # STRATEGY 1: Standard parsing (comma is thousands separator)
                val_1 = float(value.replace(',', ''))
                
                # STRATEGY 2: European parsing (comma is decimal)
                val_2 = float(value.replace(',', '.')) if ',' in value else val_1
                
                min_val = field_config.get('min_value', 0)
                max_val = field_config.get('max_value', float('inf'))
                
                # Choose the interpretation that is within range
                if min_val <= val_1 <= max_val:
                    num_value = val_1
                elif min_val <= val_2 <= max_val:
                    num_value = val_2
                    # Update value string to dot format for consistency
                    value = str(num_value)
                else:
                    # Neither is valid
                    continue
                
                # Adjust confidence based on value reasonableness
                if min_val <= num_value <= max_val:
                    confidence = base_confidence
                else:
                    confidence = base_confidence * 0.5
                    
            except ValueError:
                continue
            
            if confidence > best_confidence:
                best_confidence = confidence
                best_match = value
                best_source = match if isinstance(match, str) else 'x'.join(match)
    
    return {
        'value': best_match,
        'confidence': best_confidence,
        'source_text': best_source,
        'needs_user_input': best_confidence < 0.7 or best_match is None,
        'source': 'regex'
    }


def extract_all_shipping_details(text):
    """Extract all shipping details with confidence scoring."""
    results = {}
    
    for field_key, field_config in EXTRACTION_PATTERNS.items():
        extraction = extract_value_with_confidence(text, field_config, field_key)
        results[field_key] = {
            'label': field_config['label'],
            'value': extraction['value'],
            'confidence': extraction['confidence'],
            'needs_user_input': extraction['needs_user_input'],
            'source': extraction.get('source', 'regex')
        }
    
    return results


def extract_shipping_details_llm(text):
    """
    Extract shipping details using Google Gemini 1.5 Flash.
    Returns a dictionary compatible with the app's structure but populated by AI.
    """
    if not GENAI_AVAILABLE:
        raise ImportError("google-generativeai library not available")

    # Prompt combining User's Invoice needs + App's Shipping needs
    prompt = f"""
    You are an intelligent document understanding AI.
    Your task is to extract structured information from the following shipping document text.

    The content may:
    - Use different names for the same field
    - Have tables or plain text
    - Have inconsistent formatting

    Your goal is to understand the MEANING, not just exact words.

    -------------------------------------
    REQUIRED FIELDS (OUTPUT SCHEMA):

    1. customer_name (String or null)
    2. invoice_number (String or null)
    3. invoice_date (YYYY-MM-DD or null)
    4. total_amount (Number or null)
    5. tax_amount (Number or null)
    6. vendor_name (String or null)
    
    AND SHIPPING SPECIFIC FIELDS (Crucial for comparison):
    
    7. cartons (Number, Integer only. Look for TOTAL CARTONS, CTNS, PACKAGES)
    8. gross_weight (Number. Look for G.W., GROSS WEIGHT, KGS)
    9. cbm (Number. Look for CBM, VOL, MEASUREMENT)
    
    -------------------------------------
    RULES:
    1. Dates must be YYYY-MM-DD.
    2. Amounts/Weights/Measures must be numbers only (no units like 'KGS' in the value).
    3. If a field is missing, return null.
    4. For 'cartons', 'gross_weight', and 'cbm', prioritize the GRAND TOTAL values for the whole shipment.
    5. Output ONLY valid JSON. No markdown formatting.

    -------------------------------------
    DOCUMENT TEXT:
    {text}
    """

    models_to_try = [
        'gemini-1.5-flash-8b', # New lightweight model
        'gemini-2.0-flash-lite-preview-02-05', 
        'gemini-2.0-flash-lite-001',
        'gemini-flash-latest',
        'gemini-2.0-flash',
        'gemini-2.0-flash-exp'
    ]

    last_error = None
    for model_name in models_to_try:
        try:
            print(f"Trying model: {model_name}")
            response = client.models.generate_content(
                model=model_name,
                contents=prompt
            )
            if response:
                print(f"Success with {model_name}")
                break
        except Exception as e:
            print(f"Model {model_name} failed: {e}")
            last_error = e
            response = None

    
    if not response:
        error_msg = str(last_error) if last_error else "Unknown error"
        
        # Check for Quota limits to give a friendly error
        if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg or "quota" in error_msg.lower():
            raise Exception("Google Gemini API Quota Exceeded. Please wait a few minutes and try again.")
            
        raise Exception(f"All Gemini models failed. Last error: {error_msg}")
        
    try:    
        # Clean response text (remove markdown code blocks if present)
        response_text = response.text.replace('```json', '').replace('```', '').strip()
        
        import json
        data = json.loads(response_text)
        
        # Map to App's expected structure
        results = {}
        
        # 1. Cartons
        results['cartons'] = {
            'label': 'Cartons (CTN)',
            'value': data.get('cartons'),
            'confidence': 1.0 if data.get('cartons') is not None else 0.0,
            'needs_user_input': data.get('cartons') is None,
            'source': 'gemini_ai'
        }
        
        # 2. Gross Weight
        results['gross_weight'] = {
            'label': 'Gross Weight (KGS)',
            'value': data.get('gross_weight'),
            'confidence': 1.0 if data.get('gross_weight') is not None else 0.0,
            'needs_user_input': data.get('gross_weight') is None,
            'source': 'gemini_ai'
        }
        
        # 3. CBM
        results['cbm'] = {
            'label': 'Volume (CBM)',
            'value': data.get('cbm'),
            'confidence': 1.0 if data.get('cbm') is not None else 0.0,
            'needs_user_input': data.get('cbm') is None,
            'source': 'gemini_ai'
        }
        
        # Store other invoice fields in a separate 'meta' key if needed, 
        # but for now we stick to the comparison schema.
        # We can print them for debug:
        print(f"Extracted Extra Fields: {data}")

        return results
        
    except Exception as e:
        print(f"LLM Extraction failed: {e}")
        # Fallback will handle it check in caller
        return None



def compare_three_documents(details_a, details_b, details_c):
    """Compare shipping details from three documents."""
    results = {
        'all_match': True,
        'comparisons': []
    }
    
    for field_key in EXTRACTION_PATTERNS.keys():
        val_a = details_a.get(field_key, {}).get('value')
        val_b = details_b.get(field_key, {}).get('value')
        val_c = details_c.get(field_key, {}).get('value')
        
        label = EXTRACTION_PATTERNS[field_key]['label']
        
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


@app.route('/')
def index():
    """Render the main page."""
    return render_template('index.html')


@app.route('/preview', methods=['POST'])
def preview():
    """
    Extract values from uploaded PDFs and return with confidence scores.
    This allows users to review/edit before final comparison.
    """
    if not PDF_LIBRARY_AVAILABLE:
        return jsonify({
            'success': False,
            'error': 'PDF library (pdfplumber) is not installed'
        }), 500
    
    results = {}
    temp_files = []
    
    try:
        for doc_key in ['doc_a', 'doc_b', 'doc_c']:
            if doc_key in request.files and request.files[doc_key].filename:
                doc = request.files[doc_key]
                temp_path = os.path.join(app.config['UPLOAD_FOLDER'], f'temp_{doc_key}.pdf')
                temp_files.append(temp_path)
                doc.save(temp_path)
                
                text = extract_text_from_pdf(temp_path)
                
                # Try LLM Extraction first (Default)
                details = None
                ai_warning = None
                if GENAI_AVAILABLE:
                    try:
                        print(f"Attempting AI extraction for {doc.filename}...")
                        details = extract_shipping_details_llm(text)
                    except Exception as e:
                        print(f"AI Extraction failed for {doc.filename}: {e}")
                        # Clean up error message for UI
                        err_str = str(e)
                        if "Quota Exceeded" in err_str:
                            ai_warning = "AI Quota Exceeded. Please enable billing or wait."
                        else:
                            ai_warning = f"AI Error: {err_str}"
                        
                        # STRICT MODE: No Regex Fallback
                        # Ensure we return an error state if AI fails
                        details = None
                
                if not details and GENAI_AVAILABLE:
                     return jsonify({
                        'success': False,
                        'error': ai_warning or "AI Extraction Failed"
                     }), 500

                # If GenAI not available, we used to fallback, but user wants to remove regex.
                # So if no details, we behave as if it failed? 
                # Or do we keep regex for non-AI setups (if GENAI_AVAILABLE=False)?
                # User guidance: "remove the regex logic, itslef it seems not that robust"
                # So we should probably error out even if GENAI_AVAILABLE is False, 
                # OR just leave it for now but ensuring AI path has no fallback.
                
                results[doc_key] = {
                    'filename': doc.filename,
                    'details': details,
                    'warning': ai_warning
                }
        
        # Check we have at least 2 documents
        uploaded_count = sum(1 for v in results.values() if v is not None)
        if uploaded_count < 2:
            return jsonify({
                'success': False,
                'error': 'Please upload at least 2 PDF documents'
            }), 400
        
        # Collect any warnings
        global_warning = None
        for k, v in results.items():
            if v and v.get('warning'):
                global_warning = v['warning']
                break # Just show one warning to avoid clutter

        return jsonify({
            'success': True,
            'documents': results,
            'warning': global_warning
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
    finally:
        # Clean up temp files
        for temp_file in temp_files:
            if os.path.exists(temp_file):
                os.remove(temp_file)


@app.route('/compare', methods=['POST'])
def compare():
    """
    Compare values across documents.
    Accepts either uploaded files or confirmed values from preview.
    """
    if not PDF_LIBRARY_AVAILABLE:
        return jsonify({
            'success': False,
            'error': 'PDF library (pdfplumber) is not installed'
        }), 500
    
    try:
        # Check if this is a JSON request with confirmed values
        if request.is_json:
            data = request.get_json()
            details_a = data.get('doc_a', {})
            details_b = data.get('doc_b', {})
            details_c = data.get('doc_c', {})
        else:
            # Handle file uploads directly
            temp_files = []
            documents = {}
            
            for doc_key in ['doc_a', 'doc_b', 'doc_c']:
                if doc_key in request.files and request.files[doc_key].filename:
                    doc = request.files[doc_key]
                    temp_path = os.path.join(app.config['UPLOAD_FOLDER'], f'temp_{doc_key}.pdf')
                    temp_files.append(temp_path)
                    doc.save(temp_path)
                    
                    text = extract_text_from_pdf(temp_path)
                    documents[doc_key] = extract_all_shipping_details(text)
            
            # Clean up temp files
            for temp_file in temp_files:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            
            details_a = documents.get('doc_a', {})
            details_b = documents.get('doc_b', {})
            details_c = documents.get('doc_c', {})
        
        # Perform comparison
        comparison_results = compare_three_documents(details_a, details_b, details_c)
        
        return jsonify({
            'success': True,
            'results': comparison_results,
            'details': {
                'doc_a': details_a,
                'doc_b': details_b,
                'doc_c': details_c
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


if __name__ == '__main__':
    app.run(debug=True, port=5000)
