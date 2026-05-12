import os
import time
import json
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
client = genai.Client(api_key=GOOGLE_API_KEY)

# Use the actual prompt from shipping_logic.py
prompt = """
You are an expert Shipping Document Analyst. 
Analyze the visual layout of this document to extract shipping details.

-------------------------------------
CRITICAL RULE: DISTINGUISH "CARTONS" FROM "PIECES" / "GARMENTS"
- Documents often list "Total PCS", "Total Garments Quantity", and "Total CTNS".
- You MUST select the **CARTON** count (Unit: CTN, Cartons, PKGS).

REQUIRED OUTPUT (JSON ONLY):
{
  "_analysis": "...",
  "bl_number": "...",
  "cartons": 123,
  "gross_weight": 456,
  "cbm": 7.89
}
-------------------------------------
"""

# Dummy PDF data
pdf_data = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>\nendobj\n4 0 obj\n<< /Length 21 >>\nstream\nBT\n/F1 12 Tf\n10 700 Td\n(Hello) Tj\nET\nendstream\nendobj\nxref\n0 5\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n0000000213 00000 n \ntrailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n285\n%%EOF\n"

pdf_part = types.Part.from_bytes(data=pdf_data, mime_type='application/pdf')

models = [
    'gemini-2.5-flash',
    'gemini-2.0-flash',
    'gemini-2.5-pro'
]

for model in models:
    try:
        print(f"Testing model: {model}")
        response = client.models.generate_content(
            model=model,
            contents=[pdf_part, prompt]
        )
        print(f"SUCCESS with {model}")
    except Exception as e:
        print(f"ERROR with {model}: {e}")
