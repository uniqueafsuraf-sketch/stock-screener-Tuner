# Put StocksTunerStation on a FREE website

## Fastest (5 minutes) — free public link today

**Double-click `GO_LIVE_INSTANT.bat`** in this folder.

It starts the app and gives you a free link like `https://xxxx.trycloudflare.com` you can share immediately. Keep both black windows open.

---

## Permanent (free) — `https://stockstunerstation.onrender.com`

**Double-click `DEPLOY_NOW.bat`** — it creates a ZIP, opens GitHub + Render, and shows the guide.

No Git install needed (upload ZIP on GitHub website).

---

## Manual steps (Render.com)

Free HTTPS URL like **`https://stockstunerstation.onrender.com`**

No credit card on the free tier. You can add your own domain later (often ~$10/year from Namecheap, Cloudflare, etc.).

---

## Before you start

1. A **GitHub** account (free): https://github.com/signup  
2. **Git** on your PC (optional but easiest): https://git-scm.com/download/win  

---

## Step 1 — Put the project on GitHub

1. On GitHub, click **New repository**  
2. Name it `stockstunerstation` (or any name) → **Create**  
3. On your PC, open **PowerShell** in the `stock-screener` folder:

```powershell
cd "c:\Users\Pauly\Documents\projects cursor\stock-screener"
git init
git add .
git commit -m "StocksTunerStation initial deploy"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/stockstunerstation.git
git push -u origin main
```

Replace `YOUR_USERNAME` with your GitHub username.

> If `git` is not installed, you can upload the folder with GitHub Desktop: https://desktop.github.com/

---

## Step 2 — Deploy on Render (free)

1. Go to https://render.com and sign up (use **Sign in with GitHub**).  
2. Click **New +** → **Web Service**.  
3. Connect your GitHub repo `stockstunerstation`.  
4. Settings:
   - **Name:** `stockstunerstation` (this becomes part of your URL)
   - **Region:** pick closest to you
   - **Branch:** `main`
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:**  
     `gunicorn wsgi:application --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 180`
   - **Plan:** Free  
5. Click **Advanced** → add environment variable (optional):
   - `STS_PUBLIC_URL` = `https://stockstunerstation.onrender.com`  
     (use your real Render URL after the first deploy)
6. Click **Create Web Service**.  
7. Wait 5–10 minutes for the first build.  
8. Open your live site: **https://stockstunerstation.onrender.com**  
   (Render shows the exact URL on the dashboard)

Health check: `https://YOUR-URL.onrender.com/api/health` should return JSON with `"site": "StocksTunerStation"`.

---

## Step 3 — First use on the live site

1. Open your Render URL in the browser.  
2. Click **Refresh scan** and wait 2–5 minutes (first scan is slow).  
3. The **TOP % MOVERS** tape and tables fill in after data loads.

---

## Free tier notes (important)

| Topic | What to expect |
|--------|----------------|
| **Sleep** | Free Render apps **sleep after ~15 min** with no visitors. First visit after sleep takes **30–60 sec** to wake. |
| **Speed** | Scans are slower than on your PC. |
| **Data** | Alerts/cache reset when Render redeploys (disk is temporary on free tier). |
| **Yahoo data** | Still free/delayed quotes, not real-time tick data. |

To reduce sleep: upgrade to Render paid plan, or use a $5/mo VPS (see `DEPLOY.md`).

---

## Use your own domain (optional, not fully free)

1. Buy a domain (e.g. `stockstunerstation.com`) from Namecheap, Cloudflare, Google Domains, etc.  
2. In Render → your service → **Settings** → **Custom Domains** → add the domain.  
3. At your domain registrar, add the **CNAME** record Render shows you.  
4. Render enables **HTTPS** automatically.

---

## Alternative: PythonAnywhere (free subdomain)

1. https://www.pythonanywhere.com/ — create a **Beginner** account (free).  
2. Upload the `stock-screener` folder (Files tab).  
3. Open a **Bash** console:

```bash
cd stock-screener
pip install -r requirements.txt
```

4. **Web** tab → **Manual configuration** → WSGI file, set:

```python
import sys
path = '/home/YOUR_USERNAME/stock-screener'
if path not in sys.path:
    sys.path.insert(0, path)
from wsgi import application
```

5. Reload the web app. Your URL: **`https://YOUR_USERNAME.pythonanywhere.com`**

---

## Need help?

- Render docs: https://render.com/docs/deploy-flask  
- Local test still works: double-click **`START.bat`** on your PC  
