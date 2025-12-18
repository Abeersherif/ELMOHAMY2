import google.generativeai as genai
import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    print("No API Key found in environment variables.")
    print("Please set GOOGLE_API_KEY or create a .env file.")
    # Attempt to read from user input if interactive? No, let's just exit.
    exit(1)

genai.configure(api_key=api_key)

print("Listing available models...")
for m in genai.list_models():
    if 'generateContent' in m.supported_generation_methods:
        print(f"- {m.name}")
