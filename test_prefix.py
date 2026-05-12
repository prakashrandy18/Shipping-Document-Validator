import os
from google import genai
from dotenv import load_dotenv

load_dotenv()
client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

model_names = ['gemini-2.0-flash', 'models/gemini-2.0-flash']

for name in model_names:
    try:
        print(f"Testing name: {name}")
        response = client.models.generate_content(
            model=name,
            contents="Say hello"
        )
        print(f"SUCCESS with {name}")
    except Exception as e:
        print(f"ERROR with {name}: {e}")
