
import os
import glob
import zipfile
import tempfile
import csv
import time
import shutil
from shipping_logic import extract_shipping_details_llm, compare_three_documents

# Configuration
INPUT_FOLDER = "batch_input"
OUTPUT_FILE = "batch_results.csv"
BATCH_LIMIT = 10  # User requested limit for testing
API_DELAY_SECONDS = 5 # To avoid rate limits

def run_batch_process():
    # 1. Setup
    if not os.path.exists(INPUT_FOLDER):
        os.makedirs(INPUT_FOLDER)
        print(f"Created '{INPUT_FOLDER}'. Please put ZIP files in there and run again.")
        return

    zip_files = glob.glob(os.path.join(INPUT_FOLDER, "*.zip"))
    
    if not zip_files:
        print(f"No ZIP files found in '{INPUT_FOLDER}'.")
        return

    print(f"Found {len(zip_files)} ZIP files. Processing first {BATCH_LIMIT}...")
    zip_files = zip_files[:BATCH_LIMIT]

    results = []

    # 2. Iterate Files
    for i, zip_path in enumerate(zip_files):
        zip_name = os.path.basename(zip_path)
        print(f"\n[{i+1}/{len(zip_files)}] Processing {zip_name}...")
        
        row = {'Zip_Filename': zip_name, 'Status': '', 'Error_Message': ''}
        
        temp_dir = tempfile.mkdtemp()
        
        try:
            # Unzip
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)
            
            # Find PDFs
            pdfs = glob.glob(os.path.join(temp_dir, "**", "*.pdf"), recursive=True)
            pdfs = [p for p in pdfs if not os.path.basename(p).startswith('.')] # Ignore hidden files
            
            if len(pdfs) < 2:
                row['Status'] = 'Skipped'
                row['Error_Message'] = f"Found only {len(pdfs)} PDFs (Need at least 2)"
                results.append(row)
                continue
            
            # Take first 3
            selected_pdfs = pdfs[:3]
            doc_keys = ['doc_a', 'doc_b', 'doc_c']
            extracted_docs = {'doc_a': {}, 'doc_b': {}, 'doc_c': {}}
            
            # Extract Data
            for idx, pdf_file in enumerate(selected_pdfs):
                key = doc_keys[idx]
                row[f'{key}_Name'] = os.path.basename(pdf_file)
                
                try:
                    print(f"  - Extracting {os.path.basename(pdf_file)}...")
                    details = extract_shipping_details_llm(pdf_file)
                    extracted_docs[key] = {'details': details}
                    
                    # Store Raw Values in CSV for debug
                    if details:
                         row[f'{key}_Cartons'] = details.get('cartons', {}).get('value')
                         row[f'{key}_Weight'] = details.get('gross_weight', {}).get('value')
                         row[f'{key}_Volume'] = details.get('cbm', {}).get('value')

                    # Rate Limit Delay
                    time.sleep(API_DELAY_SECONDS)
                    
                except Exception as e:
                    print(f"    Error extracting {pdf_file}: {e}")
                    row['Error_Message'] += f"[{key} Error: {str(e)}] "
            
            # Compare
            comp_res = compare_three_documents(
                extracted_docs['doc_a'].get('details', {}),
                extracted_docs['doc_b'].get('details', {}),
                extracted_docs['doc_c'].get('details', {})
            )
            
            all_match = comp_res.get('all_match', False)
            row['Status'] = 'MATCH' if all_match else 'MISMATCH'
            
            # Add comparison notes
            for comp in comp_res.get('comparisons', []):
                 if comp['status'] != 'success':
                     row['Error_Message'] += f"{comp['field']} {comp['status']}; "

        except Exception as e:
            row['Status'] = 'Error'
            row['Error_Message'] = str(e)
            print(f"  Failed: {e}")
        finally:
            shutil.rmtree(temp_dir)
            results.append(row)

    # 3. Write Report
    write_csv_report(results)
    print(f"\nDone! Report saved to {OUTPUT_FILE}")

def write_csv_report(results):
    with open(OUTPUT_FILE, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        
        # Main Title
        writer.writerow(["SHIPPING DOCUMENT BATCH REPORT"])
        writer.writerow([])
        
        for i, r in enumerate(results):
            # 1. Header Info for this ZIP
            writer.writerow(["--------------------------------------------------------------------------------"])
            writer.writerow(["ZIP FILE", r.get('Zip_Filename')])
            writer.writerow(["STATUS", r.get('Status')])
            if r.get('Error_Message'):
                writer.writerow(["ERRORS", r.get('Error_Message')])
            writer.writerow([])
            
            # 2. Table Header imitating the UI
            # We want headers to show the actual filenames if possible
            doc_a_name = r.get('doc_a_Name', 'Doc A')
            doc_b_name = r.get('doc_b_Name', 'Doc B')
            doc_c_name = r.get('doc_c_Name', 'Doc C')
            
            writer.writerow(["FIELD", f"OBL/PKL ({doc_a_name})", f"INVOICE ({doc_b_name})", f"PACKING LIST ({doc_c_name})", "MATCH?"])
            
            # 3. Data Rows
            # Helper to get value or '--'
            def get_val(key): return str(r.get(key) or '--')
            
            # Cartons
            c_a = get_val('doc_a_Cartons')
            c_b = get_val('doc_b_Cartons')
            c_c = get_val('doc_c_Cartons')
            # Check match for specific row logic is hard since we flattened it, 
            # but we can infer roughly or just leave match column simple
            # Let's just output the values.
            writer.writerow(["Cartons", c_a, c_b, c_c, ""])
            
            # Weight
            w_a = get_val('doc_a_Weight')
            w_b = get_val('doc_b_Weight')
            w_c = get_val('doc_c_Weight')
            writer.writerow(["Gross Weight", w_a, w_b, w_c, ""])
            
            # Volume
            v_a = get_val('doc_a_Volume')
            v_b = get_val('doc_b_Volume')
            v_c = get_val('doc_c_Volume')
            writer.writerow(["Volume (CBM)", v_a, v_b, v_c, ""])
            
            writer.writerow([])
            writer.writerow([])

if __name__ == "__main__":
    run_batch_process()
