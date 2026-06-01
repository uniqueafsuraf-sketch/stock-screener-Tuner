# Deploy StocksTunerStation to your domain

## 1. Point your domain

At your DNS provider, add an **A record** for your domain (e.g. `stockstunerstation.com`) to your server’s public IP.

## 2. Run the app on the server

On the VPS (Linux example):

```bash
cd stock-screener
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export STS_HOST=0.0.0.0
export STS_PORT=5050
export STS_PUBLIC_URL=https://stockstunerstation.com
python start_dashboard.py --no-browser
```

On Windows, use **`start_production.bat`** and set `STS_PUBLIC_URL` before running if your domain differs.

## 3. Reverse proxy (recommended)

Put **nginx** or **Caddy** in front of Flask so you get HTTPS on port 443.

### nginx example

```nginx
server {
    listen 80;
    server_name stockstunerstation.com www.stockstunerstation.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name stockstunerstation.com www.stockstunerstation.com;

    ssl_certificate     /etc/letsencrypt/live/stockstunerstation.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/stockstunerstation.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:5050;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
    }
}
```

Get a free certificate with [Certbot](https://certbot.eff.org/).

## 4. Keep it running

Use **systemd**, **PM2**, or a process manager so the app restarts after reboot.

## Environment variables

| Variable | Example | Purpose |
|----------|---------|---------|
| `STS_HOST` | `0.0.0.0` | Listen on all interfaces (required on a VPS) |
| `STS_PORT` | `5050` | App port (proxy targets this) |
| `STS_PUBLIC_URL` | `https://stockstunerstation.com` | Written to `data/dashboard.url` |

## Health check

`https://stockstunerstation.com/api/health` should return JSON with `"version": "2.0"`.
