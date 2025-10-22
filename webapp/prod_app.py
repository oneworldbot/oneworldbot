import os
import hmac
import hashlib
import json
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import sqlite3
from typing import Dict

app = FastAPI()

# mount static webapp files
static_dir = Path(__file__).parent
app.mount('/webapp', StaticFiles(directory=str(static_dir)), name='webapp')

DB_PATH = str(Path(__file__).resolve().parents[1] / 'oneworld.db')


def verify_telegram_init_data(init_data: Dict[str, str], bot_token: str) -> bool:
    # Telegram Web App verification as documented
    data = dict(init_data)
    received_hash = data.pop('hash', None)
    if not received_hash:
        return False
    data_check_arr = []
    for k in sorted(data.keys()):
        data_check_arr.append(f"{k}={data[k]}")
    data_check_string = '\n'.join(data_check_arr)
    secret_key = hashlib.sha256(bot_token.encode()).digest()
    hmac_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(hmac_hash, received_hash)


@app.post('/api/verify_init')
async def api_verify_init(request: Request):
    payload = await request.json()
    init_data = payload.get('init_data') or {}
    token = os.environ.get('TELEGRAM_TOKEN')
    if not token:
        raise HTTPException(status_code=500, detail='bot token not configured')
    ok = verify_telegram_init_data(init_data, token)
    return JSONResponse({'ok': ok})


@app.post('/api/credit')
async def api_credit(request: Request):
    payload = await request.json()
    # Expect either verified init payload or server-side shared secret
    secret = os.environ.get('WEBAPP_SHARED_SECRET')
    if secret and payload.get('secret') != secret:
        # allow Telegram WebApp signed verification instead
        init_data = payload.get('init_data')
        if not init_data or not verify_telegram_init_data(init_data, os.environ.get('TELEGRAM_TOKEN','')):
            raise HTTPException(status_code=403, detail='forbidden')
    user_id = int(payload.get('user_id'))
    amount = int(payload.get('amount', 0))
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, user_id))
        conn.commit()
        conn.close()
        return JSONResponse({'ok': True, 'credited': amount})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Simple in-memory websocket lobby manager (dev)
lobbies: Dict[str, Dict] = {}

@app.websocket('/ws/lobby/{lobby_id}')
async def ws_lobby(websocket: WebSocket, lobby_id: str):
    await websocket.accept()
    lobby = lobbies.setdefault(lobby_id, {'clients': set()})
    lobby['clients'].add(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # broadcast
            for ws in list(lobby['clients']):
                try:
                    await ws.send_text(data)
                except Exception:
                    pass
    except WebSocketDisconnect:
        lobby['clients'].discard(websocket)


@app.get('/webapp/index.html')
async def web_index():
    path = static_dir / 'index.html'
    return FileResponse(str(path))
