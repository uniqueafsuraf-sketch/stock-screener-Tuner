# Fix https://stockstunerstation.onrender.com not loading

## What we found

Your URL returns **404** with header `x-render-routing: no-server`.

That means **Render has no running app** behind that address (deploy failed, never finished, or service stopped)—not a blank page from Flask.

---

## Fix in 10 minutes

### 1. Open Render dashboard

https://dashboard.render.com/

Click your **stockstunerstation** service.

Check the status at the top:

| Status | Meaning |
|--------|---------|
| **Live** (green) | Should work after redeploy below |
| **Failed** (red) | Open **Logs** tab — read the red error lines |
| **Suspended** | Free tier issue — click resume or redeploy |

### 2. Check these settings (Settings tab)

| Setting | Correct value |
|---------|----------------|
| **Root Directory** | Leave **empty** if your GitHub repo root contains `wsgi.py`. If your repo is the whole `projects cursor` folder, set `stock-screener` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `gunicorn wsgi:application --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 180` |
| **Health Check Path** | `/api/health` |

### 3. Upload the latest code (important)

The app was updated so Render’s health check does not hang.

**If you used GitHub upload (no Git):**

1. Run **`DEPLOY_NOW.bat`** on your PC again (creates new ZIP).
2. On GitHub → your repo → upload/replace files (or delete repo and re-upload).
3. On Render → **Manual Deploy** → **Deploy latest commit**.

**If you use Git:**

```powershell
cd "c:\Users\Pauly\Documents\projects cursor\stock-screener"
git add .
git commit -m "Fix Render deploy health check"
git push
```

Render will auto-redeploy.

### 4. Watch the deploy

Render → **Logs** tab:

- Build should end with `Successfully installed...`
- Start should show `Listening at: http://0.0.0.0:XXXX`
- No `ModuleNotFoundError` or `Application failed to respond`

Wait until status is **Live** (can take 5–10 min on free tier).

### 5. Test

Open: https://stockstunerstation.onrender.com/api/health

You should see JSON like:

```json
{"ok": true, "site": "StocksTunerStation", "version": "2.0"}
```

Then open: https://stockstunerstation.onrender.com

First visit after sleep may take **30–60 seconds** (free tier waking up).

---

## Still broken?

Copy the **last 30 lines** from Render **Logs** (Build + Runtime) and check:

- `No module named 'dashboard'` → Root Directory must be `stock-screener` or repo must contain `dashboard/` folder
- `gunicorn: command not found` → Build Command did not run `pip install -r requirements.txt`
- `Worker timeout` → Start Command must include `--timeout 180`
- `Application failed to respond` → Old code; redeploy with latest `server.py` / `wsgi.py`

---

## Instant link while you fix Render

Double-click **`GO_LIVE_INSTANT.bat`** on your PC for a temporary public URL (works in 2 minutes).
