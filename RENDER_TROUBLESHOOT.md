# Render build failed? — Fix in 5 minutes

Use this when your **new GitHub repo** is connected but Render shows **Build failed**.

---

## Step 1 — Check the error line

In Render → your service → **Logs** → open the latest **Build** log.

| If the log says… | Do this… |
|------------------|----------|
| `requirements.txt not found` | **Root Directory** is wrong (see Step 2) |
| `No module named 'dashboard'` or `wsgi` | Same — wrong folder / missing files on GitHub |
| `Failed to build wheel` / `pandas` / `numpy` | Use Python **3.12.3** (Step 3) |
| Build OK but **Deploy failed** | Check **Start Command** (Step 4) |

Copy the **last 10 lines** of the build log if you need help — that line is the real reason.

---

## Step 2 — Root Directory (most common mistake)

On Render → **Settings** → **Build & Deploy**:

- **Root Directory** must be **empty** (blank).
- Do **not** type `stock-screener` unless your GitHub repo is the *parent* folder and the code lives in a subfolder.

**On GitHub**, when you open your repo, you should see **immediately**:

- `wsgi.py`
- `requirements.txt`
- `render.yaml`
- folders `dashboard/`, `screener/`, `data/`

If you only see a single folder named `stock-screener` and *then* those files inside it:

- Either set Render **Root Directory** to `stock-screener`
- Or re-upload so `wsgi.py` is at the **top level** of the repo (recommended)

---

## Step 3 — Copy these Render settings exactly

| Field | Value |
|--------|--------|
| **Environment** | Python 3 |
| **Branch** | `main` |
| **Root Directory** | *(leave blank)* |
| **Build Command** | `pip install --upgrade pip && pip install -r requirements.txt` |
| **Start Command** | `gunicorn wsgi:application --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 180` |
| **Health Check Path** | `/api/ping` |

**Environment variables** (optional but good):

| Key | Value |
|-----|--------|
| `PYTHON_VERSION` | `3.12.3` |
| `RENDER` | `true` |

Save → **Manual Deploy** → **Clear build cache & deploy**.

---

## Step 4 — Verify GitHub has the full project

On your PC, in PowerShell:

```powershell
cd "c:\Users\Pauly\Documents\projects cursor\stock-screener"
python scripts/check_deploy_ready.py
```

If it says **Ready**, push everything to GitHub:

**GitHub Desktop:** Commit all → Push origin  

**Or Git:**

```powershell
git add .
git commit -m "Fix Render deploy"
git push
```

Make sure these are **not** missing on GitHub:

- `data/seed_bootstrap.json`
- `data/ourbit_stocks.json`
- `data/gold_war_room_seed.json`

---

## Step 5 — Use Blueprint (easiest)

If the repo has `render.yaml` at the root:

1. Render → **New +** → **Blueprint**
2. Connect the same GitHub repo
3. Render reads `render.yaml` automatically

Or keep your Web Service and match the settings in Step 3.

---

## After build is green (Live)

1. Open `https://YOUR-SERVICE.onrender.com/api/health` — should show JSON.
2. Open the main URL — wait 30–60 sec on first visit (free tier wake-up).
3. Click **Refresh scan** once.
4. Sidebar → **Ourbit stocks** (33 symbols).

---

## Still stuck?

Paste from Render logs:

1. Last **build** error (red text)
2. Your GitHub repo URL
3. Screenshot or text of **Root Directory** field

Do **not** deploy the old `stockstunerstation-deploy` folder — use the main `stock-screener` project only.
