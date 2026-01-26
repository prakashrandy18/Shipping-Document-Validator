
import os
import glob
import zipfile
import tempfile
import csv
import time
import shutil
from shipping_logic import extract_shipping_details_llm, compare_three_documents, classify_document

# ... (Configuration stays similar)

def run_batch_process():
    # ... (Setup code stays same) ...
    # ... (After finding PDFs) ...
    
    # Ensure Renamed BLs output dir
    renamed_bls_dir = os.path.join(os.getcwd(), "renamed_bls")
    os.makedirs(renamed_bls_dir, exist_ok=True)

            # Smart Sort PDFs into slots
            assigned_docs = {'doc_a': None, 'doc_b': None, 'doc_c': None}
            remaining_pdfs = []

            # 1. Try to classify
            for pdf_path in pdfs:
                filename = os.path.basename(pdf_path)
                doc_type = classify_document(filename)
                
                if doc_type and assigned_docs[doc_type] is None:
                    assigned_docs[doc_type] = pdf_path
                else:
                    remaining_pdfs.append(pdf_path) # Duplicate type or unknown
            
            # 2. Fill empty slots with remaining files
            for key in ['doc_a', 'doc_b', 'doc_c']:
                if assigned_docs[key] is None and remaining_pdfs:
                    assigned_docs[key] = remaining_pdfs.pop(0)

            # 3. Check if we have enough
            valid_docs = {k: v for k, v in assigned_docs.items() if v}
            if len(valid_docs) < 3:
                 # If we have < 3, we can still proceed but might miss some comparisons
                 # But sticking to previous logic:
                 if len(pdfs) < 2: # Keep original hard check
                     row['Status'] = 'Skipped'
                     row['Error_Message'] = f"Found {len(pdfs)} PDFs (Need 2+)"
                     results.append(row)
                     continue

            extracted_docs = {'doc_a': {}, 'doc_b': {}, 'doc_c': {}}
            
            # Extract Data
            doc_keys = ['doc_a', 'doc_b', 'doc_c']
            for key in doc_keys:
                pdf_file = assigned_docs.get(key)
                if not pdf_file:
                    continue # Skip if missing
                
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

                         # CLI Renaming Logic
                         if key == 'doc_a' and details.get('bl_number'):
                             try:
                                bl_num = "".join(c for c in details.get('bl_number') if c.isalnum() or c in ('-','_'))
                                if bl_num:
                                    ext = os.path.splitext(pdf_file)[1]
                                    new_name = f"{bl_num}{ext}"
                                    shutil.copy2(pdf_file, os.path.join(renamed_bls_dir, new_name))
                                    print(f"    -> Saved renamed BL: {new_name}")
                             except Exception as e:
                                 print(f"    Failed to rename BL: {e}")

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
