# How to Set Your Gemini API Key

## Option 1: Set Environment Variable in PowerShell (Recommended for Development)

Open PowerShell and run:
```powershell
$env:GOOGLE_API_KEY="your-gemini-api-key-here"
```

Then start your server:
```powershell
cd C:\Users\Administrator\Desktop\mohamyangular\Mohamy
uvicorn mohamy:app --reload
```

## Option 2: Set Environment Variable Permanently (Windows)

1. Press `Win + X` and select "System"
2. Click on "Advanced system settings"
3. Click "Environment Variables"
4. Under "User variables", click "New"
5. Variable name: `GOOGLE_API_KEY`
6. Variable value: `your-gemini-api-key-here`
7. Click OK
8. **Restart your terminal/IDE** for changes to take effect

## Option 3: Create a .env File (Quick Testing)

Create a file named `.env` in the Mohamy folder:

```bash
GOOGLE_API_KEY=your-gemini-api-key-here
```

Then install python-dotenv:
```bash
pip install python-dotenv
```

And add this to the top of `mohamy.py` (after imports):
```python
from dotenv import load_dotenv
load_dotenv()  # Load environment variables from .env file
```

## Get Your Gemini API Key

1. Go to: https://aistudio.google.com/app/apikey
2. Sign in with your Google account
3. Click "Create API Key"
4. Copy your API key

---

**Current Status:**
- ✅ Database path configured: `C:\Users\Administrator\Desktop\mohamy\law_database.db`
- ⚠️ You need to set `GOOGLE_API_KEY` using one of the methods above
