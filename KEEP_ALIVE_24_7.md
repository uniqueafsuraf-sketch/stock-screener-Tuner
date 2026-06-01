# Keep StocksTunerStation online 24/7

Render **free** web services sleep after ~15 minutes without traffic. The app already re-scans gold agents every **45 seconds** while awake.

## Option A — Free external ping (recommended)

1. Create a free monitor at [UptimeRobot](https://uptimerobot.com) or [cron-job.org](https://cron-job.org).
2. URL to ping every **5–10 minutes**:
   - `https://stock-screener-tuner-1.onrender.com/api/ping`
   - or `/api/health`
3. That wakes the server so agents, scalping, and performance logging keep running.

## Option B — PC script (Windows)

```powershell
cd stock-screener
.\scripts\render_keep_alive.ps1
```

Schedule it in **Task Scheduler** → repeat every 10 minutes (or leave the script running).

## Option C — Render paid plan

Upgrade the web service to a **paid** plan in the Render dashboard for always-on with no sleep (no external ping needed).

## Performance log file

Every agent scan and scalp setup is appended to:

`data/gold_war_room_history.json`

On Render free tier this file persists on the running instance but may reset on **redeploy**. For permanent logs, add a Render **disk** or external database later.
