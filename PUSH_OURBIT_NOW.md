# Ourbit not showing on Render? — Fix in 3 steps

Your live site was still on **version 3.1** (no Ourbit in the API). You need **one more push** to GitHub, then Render redeploys.

## Step 1 — Push latest code

**GitHub Desktop:**

1. Open repo folder: `stock-screener`
2. Commit message: `Ourbit v3.4 fix`
3. **Commit all files** (especially `dashboard/static/ourbit_stocks.json`, `dashboard.js`, `server.py`)
4. **Push origin**

## Step 2 — Redeploy on Render

1. [dashboard.render.com](https://dashboard.render.com) → your Blueprint service  
2. **Manual Deploy** → **Clear build cache & deploy**  
3. Wait until status is **Live**

## Step 3 — Verify

Open in browser (replace with your URL):

```
https://stock-screener-tuner-1.onrender.com/api/health
```

You want:

```json
"version": "3.4",
"ourbit_listed": 33
```

If you still see `"version": "3.1"` and no `ourbit_listed`, the new code is **not** on GitHub yet.

Then open the app → **Ctrl+Shift+R** → sidebar **Ourbit stocks** (should show **33**).
