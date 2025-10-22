Deployment steps (development -> production)

1) Prepare .env file with secrets (never commit to git):

TELEGRAM_TOKEN=your_token_here
BSC_RPC=https://bsc-testnet.example
TREASURY_ADDRESS=0x...
WEBAPP_SHARED_SECRET=some_long_random_secret

2) Build and run with docker-compose (recommended):

docker-compose up -d --build

3) Production considerations:
- Use separate containers for bot and webapp (this repo has an example compose).\n- Use HTTPS via reverse proxy (nginx) and obtain certs via Let's Encrypt.\n- Store PRIVATE_KEY and sensitive env vars in the host environment or secret manager (do not commit).\n- Use a managed database (Postgres) for production and Redis for sessions/matchmaking.
Deployment guide (development -> production)

1) Create a `.env` with these values (keep private):

TELEGRAM_TOKEN=your_token_here
WEBAPP_SHARED_SECRET=change_this_secret
WEBAPP_HOST=0.0.0.0
WEBAPP_PORT=8081
BSC_RPC=https://bsc-dataseed.binance.org/
TREASURY_ADDRESS=0x...
ADMIN_IDS=123456

2) Build and run locally (dev):

# run the bot directly
python3 bot.py

# or run the webapp dev server (if using provided flask_app)
python3 webapp/flask_app.py

3) Production
- Use Docker + Nginx reverse proxy, run webapp with uvicorn/gunicorn behind TLS.
- Use Postgres/Redis for persistence and sessions.
- Use Telegram Web App authentication for secure user claims.

Security notes
- Never store PRIVATE_KEY in repo. Use server env variables or a secure vault.
- Use HTTPS for WebApp and API endpoints.
