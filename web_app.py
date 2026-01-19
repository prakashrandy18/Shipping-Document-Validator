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
from shipping_logic import extract_shipping_details_llm, compare_three_documents, classify_document, GENAI_AVAILABLE, GOOGLE_API_KEY


app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 128 * 1024 * 1024  # Increased to 128MB for large batches
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


# --- Async Job Management ---
import uuid
import threading

# Job Store (In-memory for simplicity)
JOBS = {}


from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side

def process_batch_job(job_id, uploaded_files, app_instance):
    """
    Background worker to process ZIP files and generate Excel report.
    """
    JOBS[job_id]['status'] = 'processing'
    JOBS[job_id]['progress'] = 0
    JOBS[job_id]['total'] = len(uploaded_files)
    
    results = []
    
    # Create temp dir for this job
    job_temp_dir = tempfile.mkdtemp()
    
    try:
        # We can process ZIPs in parallel too! 
        # But to be safe with rate limits, let's do 3 concurrent ZIPs max.
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            future_to_zip = {}
            
            # 1. Submit all Zips
            for f_storage in uploaded_files:
                # Save to disk first so threads can access
                zip_path = os.path.join(job_temp_dir, f_storage['filename'])
                with open(zip_path, 'wb') as zf:
                    zf.write(f_storage['stream'].read())
                
                future_to_zip[executor.submit(process_single_zip, zip_path)] = f_storage['filename']
            
            # 2. Collect Results
            completed_count = 0
            for future in concurrent.futures.as_completed(future_to_zip):
                zip_name = future_to_zip[future]
                try:
                    res = future.result() # Returns a list of rows (usually 1 row per zip)
                    results.extend(res)
                except Exception as e:
                    results.append({'Zip_Filename': zip_name, 'Status': 'Error', 'Error_Message': str(e)})
                
                completed_count += 1
                JOBS[job_id]['progress'] = int((completed_count / len(uploaded_files)) * 100)
        
        # 3. Generate Excel Report using openpyxl
        wb = Workbook()
        ws = wb.active
        ws.title = "Batch Report"

        # Styles
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="4F46E5", end_color="4F46E5", fill_type="solid") # Indigo
        
        error_fill = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid") # Red-ish light
        error_font = Font(color="991B1B") # Dark Red text

        center_align = Alignment(horizontal="center", vertical="center")
        left_align = Alignment(horizontal="left", vertical="center")
        thin_border = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))

        # Header Row
        headers = ["ZIP FILE", "STATUS", "ERRORS", "FIELD", "OBL/PKL (Doc A)", "INVOICE (Doc B)", "PACKING LIST (Doc C)"]
        ws.append(headers)
        
        for cell in ws[1]:
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = center_align
            cell.border = thin_border

        # Data Rows
        row_idx = 2
        for r in results:
            # We want to group by Zip. 
            # Structure: 
            # Row 1: Zip Name | Status | Errors (Merged across?)
            # Row 2-4: Details (Cartons, Weight, Volume)
            
            is_match = r.get('Status') == 'MATCH'
            
            # --- Main Zip Info Row ---
            # Zip Filename
            ws.cell(row=row_idx, column=1, value=r.get('Zip_Filename')).alignment = left_align
            
            # Status
            status_cell = ws.cell(row=row_idx, column=2, value=r.get('Status'))
            status_cell.alignment = center_align
            
            # Error Msg
            error_cell = ws.cell(row=row_idx, column=3, value=r.get('Error_Message', ''))
            error_cell.alignment = left_align
            
            # Apply Highlight if Mismatch
            if not is_match:
                for col in range(1, 8): # Approx columns
                    c = ws.cell(row=row_idx, column=col)
                    c.fill = error_fill
                    c.font = error_font
                    c.border = thin_border
            else:
                 # Standard border
                 for col in range(1, 8):
                    ws.cell(row=row_idx, column=col).border = thin_border

            row_idx += 1

            # --- Detail Rows (Optional, but useful for user to see WHAT failed) ---
            # Using data from r
            doc_a = r.get('doc_a_Name', 'Doc A')
            doc_b = r.get('doc_b_Name', 'Doc B')
            doc_c = r.get('doc_c_Name', 'Doc C')
            
            # Helper to get value
            def g(k): return str(r.get(k) or '--')

            # Fields to show: Cartons, Weight, Volume
            fields = [
                ("Cartons", 'doc_a_Cartons', 'doc_b_Cartons', 'doc_c_Cartons'),
                ("Gross Weight", 'doc_a_Weight', 'doc_b_Weight', 'doc_c_Weight'),
                ("Volume (CBM)", 'doc_a_Volume', 'doc_b_Volume', 'doc_c_Volume'),
            ]

            for label, ka, kb, kc in fields:
                ws.cell(row=row_idx, column=4, value=label).alignment = left_align
                ws.cell(row=row_idx, column=5, value=g(ka)).alignment = center_align
                ws.cell(row=row_idx, column=6, value=g(kb)).alignment = center_align
                ws.cell(row=row_idx, column=7, value=g(kc)).alignment = center_align
                
                # Check consistency for THIS field to maybe highlight specifically? 
                # For now, just inherit the "Red" feel if the whole zip is bad, OR keep it plain. 
                # User asked: "mismatch field to hghlight on red". 
                # So if this specific field has mismatch, we should highlight it.
                # However, our 'res' object doesn't explicitly flag WHICH field failed in a distinct key for easy access here (it's in 'comparisons' inside the parallel worker which is flattened to 'r').
                # We have 'Error_Message' containing text like "Gross Weight (KGS) error;". We can fuzzy check.
                
                field_error = label.split(' ')[0] in (r.get('Error_Message') or '') # Simple heuristic
                if not is_match and field_error:
                     for col in range(4, 8):
                        c = ws.cell(row=row_idx, column=col)
                        c.fill = error_fill
                        c.font = error_font
                
                # Borders
                for col in range(1, 8):
                    ws.cell(row=row_idx, column=col).border = thin_border
                
                row_idx += 1
            
            # Empty spacer row
            row_idx += 1

        # Adjust Columns
        ws.column_dimensions['A'].width = 30
        ws.column_dimensions['B'].width = 15
        ws.column_dimensions['C'].width = 40
        ws.column_dimensions['D'].width = 20
        ws.column_dimensions['E'].width = 20
        ws.column_dimensions['F'].width = 20
        ws.column_dimensions['G'].width = 20

        # Save to Buffer
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        # Store Result
        JOBS[job_id]['xlsx_data'] = output.getvalue()
        JOBS[job_id]['results'] = results  # Store detailed results for UI
        JOBS[job_id]['status'] = 'completed'
        
    except Exception as e:
        JOBS[job_id]['status'] = 'failed'
        JOBS[job_id]['error'] = str(e)
        print(f"Job {job_id} failed: {e}")
    finally:
        shutil.rmtree(job_temp_dir)

def process_single_zip(zip_path):
    """
    Helper to process ONE zip file. Returns a list of result rows (usually 1).
    """
    row = {'Zip_Filename': os.path.basename(zip_path), 'Status': '', 'Error_Message': ''}
    temp_extract_dir = tempfile.mkdtemp()
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_extract_dir)
        
        pdfs = glob.glob(os.path.join(temp_extract_dir, "**", "*.[pP][dD][fF]"), recursive=True)
        pdfs = [p for p in pdfs if not os.path.basename(p).startswith('.')]
        
        if len(pdfs) < 2:
            row['Status'] = 'Skipped'
            row['Error_Message'] = f"Found {len(pdfs)} PDFs (Need 2+)"
            return [row]
        
        # Classification
        assigned_docs = {'doc_a': None, 'doc_b': None, 'doc_c': None}
        remaining_pdfs = []
        for p in pdfs:
            doc_type = classify_document(os.path.basename(p))
            if doc_type and assigned_docs[doc_type] is None:
                assigned_docs[doc_type] = p
            else:
                remaining_pdfs.append(p)
        for key in ['doc_a', 'doc_b', 'doc_c']:
            if assigned_docs[key] is None and remaining_pdfs:
                assigned_docs[key] = remaining_pdfs.pop(0)

        extracted_docs = {}
        # Extract Loop
        for key in ['doc_a', 'doc_b', 'doc_c']:
            pdf_file = assigned_docs.get(key)
            if not pdf_file: continue
            
            row[f'{key}_Name'] = os.path.basename(pdf_file)
            try:
                details = extract_shipping_details_llm(pdf_file)
                extracted_docs[key] = {'details': details}
                if details:
                        row[f'{key}_Cartons'] = details.get('cartons', {}).get('value')
                        row[f'{key}_Weight'] = details.get('gross_weight', {}).get('value')
                        row[f'{key}_Volume'] = details.get('cbm', {}).get('value')
            except Exception as e:
                row['Error_Message'] += f"[{key} Err: {str(e)}] "
        
        # Compare
        comp_res = compare_three_documents(
            extracted_docs.get('doc_a', {}).get('details', {}),
            extracted_docs.get('doc_b', {}).get('details', {}),
            extracted_docs.get('doc_c', {}).get('details', {})
        )
        row['Status'] = 'MATCH' if comp_res.get('all_match') else 'MISMATCH'
        for comp in comp_res.get('comparisons', []):
                if comp['status'] != 'success':
                    row['Error_Message'] += f"{comp['field']} {comp['status']}; "
        
        return [row]

    except Exception as e:
        row['Status'] = 'Error'
        row['Error_Message'] = str(e)
        return [row]
    finally:
        shutil.rmtree(temp_extract_dir)


@app.route('/batch_process', methods=['POST'])
def batch_process():
    uploaded_files = request.files.getlist('zip_files')
    if not uploaded_files: return jsonify({'error': 'No files'}), 400

    # Read files into memory/buffers to pass to thread
    # (Flask file objects are not thread safe if request ends, so we read them)
    files_data = []
    for f in uploaded_files:
        if f.filename.endswith('.zip'):
            # Store name and content stream
            files_data.append({
                'filename': f.filename,
                'stream': io.BytesIO(f.read())
            })

    job_id = str(uuid.uuid4())
    JOBS[job_id] = {'status': 'queued', 'progress': 0}
    
    # Start Thread
    thread = threading.Thread(target=process_batch_job, args=(job_id, files_data, app))
    thread.daemon = True
    thread.start()
    
    return jsonify({'success': True, 'job_id': job_id})

@app.route('/batch_status/<job_id>', methods=['GET'])
def batch_status(job_id):
    job = JOBS.get(job_id)
    if not job: return jsonify({'error': 'Job not found'}), 404
    
    # Return a clean copy without binary data (bytes not proper for JSON)
    job_response = job.copy()
    job_response.pop('csv_data', None)
    job_response.pop('xlsx_data', None)
    
    return jsonify(job_response)

@app.route('/batch_download/<job_id>', methods=['GET'])
def batch_download(job_id):
    job = JOBS.get(job_id)
    if not job or job['status'] != 'completed': return jsonify({'error': 'Not ready'}), 400
    
    if 'xlsx_data' in job:
        mem = io.BytesIO(job['xlsx_data'])
        mem.seek(0)
        return send_file(
            mem,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name='batch_report.xlsx'
        )
    
    # Fallback/Legacy
    if 'csv_data' in job:
        mem = io.BytesIO()
        mem.write(job['csv_data'].encode('utf-8'))
        mem.seek(0)
        return send_file(
            mem,
            mimetype='text/csv',
            as_attachment=True,
            download_name='batch_report.csv'
        )
    
    return jsonify({'error': 'No report data'}), 404


if __name__ == '__main__':
    app.run(debug=True, port=5000)
