"""
Test: BL.pdf specifically with files.upload + wait for ACTIVE state + different models
"""
import os, zipfile, tempfile, glob, shutil, time
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()
client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

# Extract the BL.pdf
zip_path = "/Users/growmax/Personal/Shipping Docs/BKG_460536_20260512144828811.zip"
temp_dir = tempfile.mkdtemp()
with zipfile.ZipFile(zip_path, 'r') as z:
    z.extractall(temp_dir)

bl_path = os.path.join(temp_dir, "BL.pdf")
print(f"BL.pdf size: {os.path.getsize(bl_path)} bytes")

prompt = "Extract the cartons count, gross weight in KGS, and CBM volume from this shipping document. Return JSON only."

# --- Test 1: files.upload with proper wait ---
print("\n=== Test 1: files.upload + wait for ACTIVE ===")
try:
    uploaded = client.files.upload(file=bl_path)
    print(f"Upload done. name={uploaded.name}, state={uploaded.state}")
    
    # Wait until the file is fully processed
    while uploaded.state.name == "PROCESSING":
        print("  Waiting for file processing...")
        time.sleep(3)
        uploaded = client.files.get(name=uploaded.name)
    
    print(f"File ready. state={uploaded.state}")
    
    for model in ['gemini-2.0-flash', 'gemini-2.5-flash', 'gemini-2.0-flash-lite']:
        print(f"\n  Trying {model}...")
        try:
            resp = client.models.generate_content(
                model=model,
                contents=[uploaded, prompt]
            )
            print(f"  SUCCESS with {model}: {resp.text[:200]}")
            break
        except Exception as e:
            print(f"  FAILED with {model}: {e}")
except Exception as e:
    print(f"Upload FAILED: {e}")

# --- Test 2: Part.from_bytes with explicit config ---
print("\n=== Test 2: Part.from_bytes with generation config ===")
try:
    with open(bl_path, "rb") as f:
        data = f.read()
    
    # Check if the PDF might be too large for inline
    print(f"PDF size: {len(data)} bytes ({len(data)/1024/1024:.1f} MB)")
    
    part = types.Part.from_bytes(data=data, mime_type="application/pdf")
    
    config = types.GenerateContentConfig(
        temperature=0.1,
        max_output_tokens=2048,
    )
    
    resp = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=[part, prompt],
        config=config
    )
    print(f"SUCCESS: {resp.text[:200]}")
except Exception as e:
    print(f"FAILED: {e}")

# --- Test 3: Part.from_uri using the uploaded file reference ---
print("\n=== Test 3: Part.from_uri ===")
try:
    uploaded = client.files.upload(file=bl_path)
    while uploaded.state.name == "PROCESSING":
        time.sleep(2)
        uploaded = client.files.get(name=uploaded.name)
    
    part = types.Part.from_uri(file_uri=uploaded.uri, mime_type=uploaded.mime_type)
    
    resp = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=[part, prompt]
    )
    print(f"SUCCESS: {resp.text[:200]}")
except Exception as e:
    print(f"FAILED: {e}")

shutil.rmtree(temp_dir)
