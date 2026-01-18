import os
from google import genai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Use your key
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

if not GOOGLE_API_KEY:
    print("Error: GOOGLE_API_KEY not found in environment variables.")
else:
    try:
        client = genai.Client(api_key=GOOGLE_API_KEY)
        print("Listing models...")
        for m in client.models.list():
            print(f"- {m.name}")
    except Exception as e:
        print(f"Error: {e}")
