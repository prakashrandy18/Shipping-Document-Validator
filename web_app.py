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
import zipfile
import glob
import shutil
import csv
import io
from flask import Flask, render_template, request, jsonify, send_file
from dotenv import load_dotenv
from shipping_logic import extract_shipping_details_llm, compare_three_documents, GENAI_AVAILABLE, GOOGLE_API_KEY

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # Max 16MB upload
app.config['UPLOAD_FOLDER'] = tempfile.gettempdir()


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


@app.route('/batch_process', methods=['POST'])
def batch_process():
    """
    Process multiple ZIP files and return a CSV report.
    """
    uploaded_files = request.files.getlist('zip_files')
    
    if not uploaded_files:
         return jsonify({'error': 'No files uploaded'}), 400

    # Create a wrapper temp dir
    batch_temp_dir = tempfile.mkdtemp()
    results = []
    
    try:
        for f in uploaded_files:
            if not f.filename.endswith('.zip'):
                continue
                
            zip_path = os.path.join(batch_temp_dir, f.filename)
            f.save(zip_path)
            
            # --- Per Zip Logic (Copied/Adapted from batch_run.py) ---
            row = {'Zip_Filename': f.filename, 'Status': '', 'Error_Message': ''}
            temp_extract_dir = tempfile.mkdtemp()
            
            try:
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(temp_extract_dir)
                
                pdfs = glob.glob(os.path.join(temp_extract_dir, "**", "*.pdf"), recursive=True)
                pdfs = [p for p in pdfs if not os.path.basename(p).startswith('.')]
                
                if len(pdfs) < 2:
                    row['Status'] = 'Skipped'
                    row['Error_Message'] = f"Found {len(pdfs)} PDFs (Need 2+)"
                    results.append(row)
                    continue
                
                # Take first 3
                selected_pdfs = pdfs[:3]
                doc_keys = ['doc_a', 'doc_b', 'doc_c']
                extracted_docs = {'doc_a': {}, 'doc_b': {}, 'doc_c': {}}
                
                # Extract
                for idx, pdf_file in enumerate(selected_pdfs):
                    key = doc_keys[idx]
                    row[f'{key}_Name'] = os.path.basename(pdf_file)
                    try:
                        details = extract_shipping_details_llm(pdf_file)
                        extracted_docs[key] = {'details': details}
                        if details:
                             row[f'{key}_Cartons'] = details.get('cartons', {}).get('value')
                             row[f'{key}_Weight'] = details.get('gross_weight', {}).get('value')
                             row[f'{key}_Volume'] = details.get('cbm', {}).get('value')
                        
                        # Small delay to be kind to API if running many
                        time.sleep(2) 
                    except Exception as e:
                        row['Error_Message'] += f"[{key} Err: {str(e)}] "
                
                # Compare
                comp_res = compare_three_documents(
                    extracted_docs['doc_a'].get('details', {}),
                    extracted_docs['doc_b'].get('details', {}),
                    extracted_docs['doc_c'].get('details', {})
                )
                
                all_match = comp_res.get('all_match', False)
                row['Status'] = 'MATCH' if all_match else 'MISMATCH'
                for comp in comp_res.get('comparisons', []):
                     if comp['status'] != 'success':
                         row['Error_Message'] += f"{comp['field']} {comp['status']}; "
            
            except Exception as e:
                row['Status'] = 'Error'
                row['Error_Message'] = str(e)
            finally:
                shutil.rmtree(temp_extract_dir)
                results.append(row)
    
    finally:
        shutil.rmtree(batch_temp_dir)
        
    # Generate CSV (Vertical Report Format)
    output = io.StringIO()
    writer = csv.writer(output)
    
    writer.writerow(["SHIPPING DOCUMENT BATCH REPORT"])
    writer.writerow([])
    
    for r in results:
        writer.writerow(["--------------------------------------------------------------------------------"])
        writer.writerow(["ZIP FILE", r.get('Zip_Filename')])
        writer.writerow(["STATUS", r.get('Status')])
        if r.get('Error_Message'):
            writer.writerow(["ERRORS", r.get('Error_Message')])
        writer.writerow([])
        
        # Table Header
        doc_a = r.get('doc_a_Name', 'Doc A')
        doc_b = r.get('doc_b_Name', 'Doc B')
        doc_c = r.get('doc_c_Name', 'Doc C')
        
        writer.writerow(["FIELD", f"OBL/PKL ({doc_a})", f"INVOICE ({doc_b})", f"PACKING LIST ({doc_c})"])
        
        # Helper stringifier
        def g(k): return str(r.get(k) or '--')
        
        writer.writerow(["Cartons", g('doc_a_Cartons'), g('doc_b_Cartons'), g('doc_c_Cartons')])
        writer.writerow(["Gross Weight", g('doc_a_Weight'), g('doc_b_Weight'), g('doc_c_Weight')])
        writer.writerow(["Volume (CBM)", g('doc_a_Volume'), g('doc_b_Volume'), g('doc_c_Volume')])
        
        writer.writerow([])
        writer.writerow([])
        
    # Send as file
    mem = io.BytesIO()
    mem.write(output.getvalue().encode('utf-8'))
    mem.seek(0)
    
    return send_file(
        mem,
        mimetype='text/csv',
        as_attachment=True,
        download_name='batch_report.csv'
    )


if __name__ == '__main__':
    app.run(debug=True, port=5000)
