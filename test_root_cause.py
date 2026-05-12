"""
Root cause analysis: test each PDF from the ZIP against Gemini individually
"""
import os, zipfile, tempfile, glob, shutil, time
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()
client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

zip_path = "/Users/growmax/Personal/Shipping Docs/BKG_460536_20260512144828811.zip"
temp_dir = tempfile.mkdtemp()

with zipfile.ZipFile(zip_path, 'r') as z:
    z.extractall(temp_dir)

pdfs = glob.glob(os.path.join(temp_dir, "**", "*.[pP][dD][fF]"), recursive=True)
pdfs = [p for p in pdfs if not os.path.basename(p).startswith('.')]

prompt = "Extract the cartons count, gross weight, and CBM from this document. Return JSON."

for pdf_path in pdfs:
    name = os.path.basename(pdf_path)
    size = os.path.getsize(pdf_path)
    print(f"\n{'='*60}")
    print(f"FILE: {name} ({size} bytes)")
    print(f"{'='*60}")
    
    # --- Method 1: Part.from_bytes ---
    print("\n[Method 1] Part.from_bytes:")
    try:
        with open(pdf_path, "rb") as f:
            data = f.read()
        part = types.Part.from_bytes(data=data, mime_type="application/pdf")
        resp = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[part, prompt]
        )
        print(f"  SUCCESS: {resp.text[:100]}...")
    except Exception as e:
        print(f"  FAILED: {e}")
    
    # --- Method 2: files.upload ---
    print("\n[Method 2] files.upload:")
    try:
        uploaded = client.files.upload(file=pdf_path)
        print(f"  Upload OK: name={uploaded.name}, state={uploaded.state}")
        # Wait for processing
        time.sleep(2)
        resp = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[uploaded, prompt]
        )
        print(f"  SUCCESS: {resp.text[:100]}...")
    except Exception as e:
        print(f"  FAILED: {e}")

shutil.rmtree(temp_dir)
