"""
Shipping Document Validator - Web Application
==============================================
A modern web application to compare shipping details across THREE PDF documents.
Powered by Google Gemini 1.5 Pro (Multimodal).
"""

from flask import Flask, render_template, request, jsonify
import os
import tempfile
import time
import concurrent.futures
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

if GENAI_AVAILABLE and GOOGLE_API_KEY:
    client = genai.Client(api_key=GOOGLE_API_KEY)
else:
    print("Warning: GOOGLE_API_KEY not found or google-genai missing.")


app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # Max 16MB upload
app.config['UPLOAD_FOLDER'] = tempfile.gettempdir()

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
    
    You must perform a STEP-BY-STEP breakdown to avoid confusing "Assort Qty" with "Cartons".
    
    -------------------------------------
    STEP 1: ANALYZE TABLES
    - Find the main table. Locate the row labeled "TOTAL" or "GRAND TOTAL".
    - In this "TOTAL" row, find the value under "CTN QTY" (or "Cartons"). **This is the Carton Count (e.g., 1218).**
    - In this "TOTAL" row, find the value under "Assort Qty" or "Total Garments". **This is NOT Cartons (e.g., 6).**
    
    STEP 2: ANALYZE SUMMARY SECTIONS
    - Look for a separate "Summary" or "Carton Meas" table, often at the bottom left.
    - Find "CBM" or "Vol" in this summary table. **This is the Volume (e.g., 10.611).**
    - Do NOT sum up values unless there is no Total.
    
    -------------------------------------
    REQUIRED OUTPUT (JSON ONLY):
    {
      "_analysis": "Describe which row you used for Total and where you found CBM.",
      "assort_quantity": Number or null (Value of Assort Qty),
      "cartons": Number or null (The value from CTN QTY column in TOTAL row),
      "gross_weight": Number or null,
      "cbm": Number or null
    }
    -------------------------------------
    """

    models_to_try = [
        'gemini-1.5-pro',
        'gemini-2.0-flash',
        'gemini-1.5-flash-latest'
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
        import json
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


@app.route('/')
def index():
    """Render the main page."""
    return render_template('index.html')


@app.route('/preview', methods=['POST'])
def preview():
    """
    Extract values from uploaded PDFs (AI Only).
    """
    if not GENAI_AVAILABLE or not GOOGLE_API_KEY:
        return jsonify({
            'success': False,
            'error': 'Google Gemini API is not configured.'
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
                
                details = None
                ai_warning = None

                try:
                    print(f"Attempting AI extraction for {doc.filename}...")
                    details = extract_shipping_details_llm(temp_path)
                except Exception as e:
                    print(f"AI Extraction failed for {doc.filename}: {e}")
                    err_str = str(e)
                    ai_warning = f"AI Error: {err_str}"
                    details = None
                
                if not details:
                     return jsonify({
                        'success': False,
                        'error': ai_warning or "AI Extraction Failed"
                     }), 500

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
        
        return jsonify({
            'success': True,
            'documents': results,
            'warning': None
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
    Accepts confirmed values from preview.
    """
    try:
        # Check if this is a JSON request with confirmed values
        if request.is_json:
            data = request.get_json()
            details_a = data.get('doc_a', {})
            details_b = data.get('doc_b', {})
            details_c = data.get('doc_c', {})
        else:
             return jsonify({
                'success': False,
                'error': 'Method not supported. Please use the UI flow.'
            }), 400
        
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


@app.route('/compare_direct', methods=['POST'])
def compare_direct():
    """
    Single-step route: Uploads 3 files, extracts data with AI, AND compares them immediately.
    """
    uploaded_files = {
        'doc_a': request.files.get('doc_a'),
        'doc_b': request.files.get('doc_b'), 
        'doc_c': request.files.get('doc_c')
    }
    
    # 1. Validation
    if not any(uploaded_files.values()):
        return jsonify({'error': 'No files uploaded'}), 400

    start_time = time.time()
    
    # 2. Extract Data (Parallel-ish or sequential)
    extracted_docs = {}
    
    # We use a shared AI meta for the dashboard (taking the longest/last one or summing tokens)
    # For simplicity, we'll just capture the Last detailed meta
    final_meta = {}
    
    # 1. Save all files to temp paths first (Fast IO)
    temp_paths = {}
    for key, f in uploaded_files.items():
        if f and f.filename:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp:
                f.save(temp.name)
                temp_paths[key] = temp.name

    # 2. Define worker for parallel execution
    def process_pdf(key, path):
        try:
            # This calls the AI (Slow)
            details = extract_shipping_details_llm(path)
            
            if details:
                meta = details.get('meta')
                return key, {'details': details}, meta
            else:
                return key, {'error': 'AI returned empty result', 'details': {}}, None
        except Exception as e:
            print(f"Error processing {key}: {e}")
            return key, {'error': str(e), 'details': {}}, None

    # 3. Run AI in Parallel (Significant Speedup)
    print(f"Starting parallel extraction for {len(temp_paths)} documents...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(process_pdf, k, p) for k, p in temp_paths.items()]
        
        for future in concurrent.futures.as_completed(futures):
            key, result, meta = future.result()
            extracted_docs[key] = result
            if meta:
                final_meta = meta # Use the last available meta for the badge

    # Cleanup temp files
    for p in temp_paths.values():
         try:
             if os.path.exists(p):
                 os.remove(p)
         except:
             pass

    # 3. Compare
    comparison_results = compare_three_documents(
        extracted_docs.get('doc_a', {}).get('details', {}),
        extracted_docs.get('doc_b', {}).get('details', {}),
        extracted_docs.get('doc_c', {}).get('details', {})
    )
    
    # 4. Total Duration Update
    total_duration = int((time.time() - start_time) * 1000)
    final_meta['duration_ms'] = total_duration

    return jsonify({
        'success': True,
        'documents': extracted_docs,
        'results': comparison_results,
        'meta': final_meta
    })

if __name__ == '__main__':
    app.run(debug=True, port=5000)
