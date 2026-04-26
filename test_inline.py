import os
import httpx
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
client = genai.Client(api_key=os.environ.get("GOOGLE_API_KEY"))

# Create a dummy tiny PDF
pdf_data = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>\nendobj\n4 0 obj\n<< /Length 21 >>\nstream\nBT\n/F1 12 Tf\n10 700 Td\n(Hello) Tj\nET\nendstream\nendobj\nxref\n0 5\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n0000000213 00000 n \ntrailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n285\n%%EOF\n"

with open("dummy.pdf", "wb") as f:
    f.write(pdf_data)

try:
    with open("dummy.pdf", "rb") as f:
        doc_data = f.read()
    
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=[
            types.Part.from_bytes(data=doc_data, mime_type='application/pdf'),
            "What does this document say?"
        ]
    )
    print("SUCCESS:", response.text)
except Exception as e:
    print("ERROR:", str(e))
