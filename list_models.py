
import os
from google import genai

# Use your key
GOOGLE_API_KEY = "AIzaSyD0GJQtq7pSRxCwRyi4JDUWWP2p5WCuURw"

try:
    client = genai.Client(api_key=GOOGLE_API_KEY)
    print("Listing models...")
    for m in client.models.list():
        print(f"- {m.name}")
except Exception as e:
    print(f"Error: {e}")
