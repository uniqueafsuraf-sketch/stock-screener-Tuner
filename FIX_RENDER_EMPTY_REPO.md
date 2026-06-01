# Fix: "Git repository is empty" on Render

Your code **is on GitHub** — but Render is connected to a **different, empty** repo.

## Your repo (has all the code)

**https://github.com/uniqueafsuraf-sketch/stock-screener-Tuner**

Branch: **main** (3 commits, includes `wsgi.py`, `dashboard/`, `requirements.txt`)

---

## Fix in Render (2 minutes)

1. Open **https://dashboard.render.com**
2. Click your service (**stockstunerstation**)
3. Go to **Settings** (left sidebar)
4. Scroll to **Build & Deploy** → **Repository**
5. Click **Connect a different repository** (or **Change repository**)
6. Choose:
   - **uniqueafsuraf-sketch / stock-screener-Tuner**
   - Branch: **main**
7. Confirm these settings:

| Setting | Value |
|---------|--------|
| **Root Directory** | *(leave empty)* |
| **Branch** | `main` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `gunicorn wsgi:application --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 180` |

8. **Save Changes**
9. **Manual Deploy** → **Deploy latest commit**
10. Wait until status is **Live** (green)

## Test

- https://stockstunerstation.onrender.com/api/health → `"ok": true`
- https://stockstunerstation.onrender.com → dashboard

---

## Why this happened

Render was linked to an **empty** GitHub repo (often created as `stockstunerstation` with no files).  
You published the real app as **stock-screener-Tuner** — Render must use **that** repo.

---

## Optional: rename repo on GitHub

If you want the GitHub name to match Render:

1. GitHub → **stock-screener-Tuner** → **Settings** → **Repository name**
2. Rename to `stockstunerstation`
3. In GitHub Desktop: **Repository** → **Repository settings** → fix remote if needed

Then reconnect Render to the renamed repo.
