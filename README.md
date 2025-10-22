# OneWorldBot

This repository contains OneWorld Telegram bot, WebApp game hub and dev/prod scaffolding.

Quick start (development):

1. Create a `.env` with TELEGRAM_TOKEN and optionally BSC_RPC, TREASURY_ADDRESS, WEBAPP_SHARED_SECRET.
2. Run the bot (it will start a dev webapp server on port 8081):

```bash
python3 bot.py
```

3. Open the Game Hub (dev) in your browser or from Telegram WebApp button:

```
http://<server-ip>:8081/webapp/
```

Production notes:
- Use the `webapp/prod_app.py` FastAPI app behind uvicorn/gunicorn and Nginx with HTTPS.
- Protect `WEBAPP_SHARED_SECRET` and use Telegram WebApp auth to verify users instead of a shared secret.

