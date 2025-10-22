import os
import hmac
import hashlib
import json
from typing import Dict
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import asyncio

app = FastAPI()

ROOT = Path(__file__).resolve().parent
app.mount('/static', StaticFiles(directory=ROOT), name='static')


def verify_telegram_webapp(auth_data: Dict[str, str]) -> bool:
    # Telegram Web App auth: build data-check-string and compare HMAC-SHA256 with secret key derived from bot token
    token = os.environ.get('TELEGRAM_TOKEN')
    if not token:
        return False
    secret_key = hashlib.sha256(token.encode()).digest()
    items = []
    for k in sorted(auth_data.keys()):
        if k == 'hash':
            continue
        items.append(f"{k}={auth_data[k]}")
    data_check_string = '\n'.join(items)
    hmac_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return hmac_hash == auth_data.get('hash')


class CreditRequest(BaseModel):
    user_id: int
    amount: int
    auth: Dict[str, str] | None = None


@app.get('/webapp/')
async def index():
    html = ROOT / 'index.html'
    if not html.exists():
        raise HTTPException(404)
    return FileResponse(html)


@app.post('/api/credit')
async def credit(req: CreditRequest):
    # require Telegram WebApp auth payload to validate user
    if not req.auth or not verify_telegram_webapp(req.auth):
        raise HTTPException(status_code=403, detail='invalid auth')
    uid = req.user_id
    amt = req.amount
    db = str(Path(__file__).resolve().parents[1] / 'oneworld.db')
    import sqlite3
    try:
        conn = sqlite3.connect(db)
        cur = conn.cursor()
        cur.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amt, uid))
        conn.commit()
        conn.close()
        return {'ok': True, 'credited': amt}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Simple in-memory lobby manager using WebSockets
lobbies: Dict[str, Dict] = {}
lobbies_lock = asyncio.Lock()


@app.websocket('/ws/lobby/{lobby_id}')
async def ws_lobby(websocket: WebSocket, lobby_id: str):
    await websocket.accept()
    async with lobbies_lock:
        if lobby_id not in lobbies:
            lobbies[lobby_id] = {'players': [], 'sockets': []}
        lobbies[lobby_id]['sockets'].append(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # broadcast to lobby
            async with lobbies_lock:
                sockets = list(lobbies[lobby_id]['sockets'])
            for s in sockets:
                try:
                    await s.send_text(data)
                except Exception:
                    pass
    except WebSocketDisconnect:
        async with lobbies_lock:
            if lobby_id in lobbies and websocket in lobbies[lobby_id]['sockets']:
                lobbies[lobby_id]['sockets'].remove(websocket)
