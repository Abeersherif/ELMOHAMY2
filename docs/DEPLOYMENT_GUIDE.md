# 🚀 Mohamy Legal Assistant - Deployment Guide

## Overview

This guide explains how to deploy the Mohamy Legal Assistant so it's accessible via a single URL. The application has two parts:
- **Backend (FastAPI)** - Python API running the legal assistant logic
- **Frontend (Angular)** - Web interface for users

---

## 🌐 Deployment Option 1: Render (Recommended - Free Tier Available)

### Step 1: Deploy the Backend API

1. **Go to [Render](https://render.com)** and sign up/login

2. **Click "New +" → "Web Service"**

3. **Connect your GitHub repository:**
   - Select: `basmalaemara/MohamyElMasry`

4. **Configure the service:**
   | Setting | Value |
   |---------|-------|
   | Name | `mohamy-api` |
   | Environment | `Python 3` |
   | Build Command | `pip install -r requirements.txt` |
   | Start Command | `uvicorn mohamy:app --host 0.0.0.0 --port $PORT` |

5. **Add Environment Variable:**
   - Key: `GOOGLE_API_KEY`
   - Value: (Your Gemini API key)

6. **Click "Create Web Service"**

7. **Copy your API URL** (e.g., `https://mohamy-api.onrender.com`)

---

### Step 2: Update Frontend Configuration

1. **Edit `src/environments/environment.prod.ts`:**
   ```typescript
   export const environment = {
     production: true,
     apiUrl: 'https://YOUR-RENDER-API-URL.onrender.com'  // Replace with actual URL
   };
   ```

2. **Commit and push the change:**
   ```bash
   git add .
   git commit -m "Update production API URL"
   git push origin main
   ```

---

### Step 3: Deploy the Frontend

1. **In Render, click "New +" → "Static Site"**

2. **Connect the same GitHub repository**

3. **Configure:**
   | Setting | Value |
   |---------|-------|
   | Name | `mohamy-frontend` |
   | Build Command | `npm install && npm run build` |
   | Publish Directory | `dist/mohamy-masry/browser` |

4. **Click "Create Static Site"**

5. **Your app is now live!** Access it at: `https://mohamy-frontend.onrender.com`

---

## 🌐 Deployment Option 2: Vercel (Frontend) + Railway (Backend)

### Backend on Railway

1. Go to [Railway](https://railway.app)
2. New Project → Deploy from GitHub
3. Select your repository
4. Add environment variable: `GOOGLE_API_KEY`
5. Railway auto-detects Python and deploys

### Frontend on Vercel

1. Go to [Vercel](https://vercel.com)
2. Import your GitHub repository
3. Framework: Angular
4. Build Command: `npm run build`
5. Output Directory: `dist/mohamy-masry/browser`

---

## 🖥️ Running Locally (Development)

### Option 1: Two Terminals (Current Method)

**Terminal 1 - Backend:**
```bash
cd MohamyMasry
set GOOGLE_API_KEY=your_api_key_here
uvicorn mohamy:app --reload
```

**Terminal 2 - Frontend:**
```bash
cd MohamyMasry
ng serve
```

Access at: `http://localhost:4200`

---

### Option 2: Single Command with Concurrently

1. **Install concurrently:**
   ```bash
   npm install concurrently --save-dev
   ```

2. **Update `package.json` scripts:**
   ```json
   "scripts": {
     "start": "ng serve",
     "start:api": "uvicorn mohamy:app --reload",
     "start:all": "concurrently \"npm run start:api\" \"npm run start\""
   }
   ```

3. **Run both with one command:**
   ```bash
   npm run start:all
   ```

---

## 🔧 Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `GOOGLE_API_KEY` | Google Gemini API key | ✅ Yes |
| `PORT` | Server port (auto-set by hosting) | Auto |

---

## 📁 Important Files for Deployment

| File | Purpose |
|------|---------|
| `Procfile` | Heroku/Render process configuration |
| `render.yaml` | Render Blueprint (auto-deploy config) |
| `runtime.txt` | Python version specification |
| `requirements.txt` | Python dependencies |
| `src/environments/` | Angular environment configs |

---

## 🔒 CORS Configuration

The backend is configured to accept requests from any origin (`allow_origins=["*"]`). For production, you may want to restrict this:

```python
# In mohamy.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://your-frontend-url.onrender.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## 🗄️ Database Considerations

The SQLite database (`law_database.db`) is included in the repository. For production:

1. **Option A**: Keep as-is (works for read-only, but resets on each deploy)
2. **Option B**: Use a cloud database service (PostgreSQL on Render/Railway)

---

## ⚠️ Critical: Large Database & Git LFS

The `law_database.db` file is approx **1.4 GB**. Standard Git cannot handle this file size, so we use **Git LFS (Large File Storage)**.

### For Render Deployment
We have updated `render.yaml` to automatically pull the LFS file during build:
```yaml
buildCommand: git lfs install --skip-smudge && git lfs pull && pip install -r requirements.txt
```

### Troubleshooting Database Issues
If you see errors like `sqlite3.DatabaseError: file is not a database` or `no such table`, it means Render only downloaded the **LFS pointer file** (1KB text file) instead of the actual 1.4GB database.

**Fix:**
1. Ensure your Render service is using the updated `render.yaml` configuration.
2. In Render Settings → "Environment", ensure `PYTHON_VERSION` is set.
3. If issues persist, you can manually trigger a deploy with "Clear Cache and Deploy".

---

## ⚠️ Common Issues

### "GOOGLE_API_KEY not set"
- Ensure you've added the environment variable in your hosting dashboard

### "CORS Error"
- Verify the backend URL in `environment.prod.ts` is correct
- Check CORS settings in `mohamy.py`

### "502 Bad Gateway"
- Check Render logs for startup errors
- Ensure all dependencies are in `requirements.txt`

---

## 📞 Support

For issues, check:
1. Render/Railway deployment logs
2. Browser Developer Console (F12)
3. Backend logs for Python errors

---

*Last Updated: December 2024*
