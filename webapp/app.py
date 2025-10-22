from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Dict, List
import threading

app = FastAPI()

# mount static webapp files
app.mount("/", StaticFiles(directory="./", html=True), name="webroot")

# in-memory lobbies (dev)
lobbies_lock = threading.Lock()
lobbies: Dict[str, Dict] = {}

class CreditRequest(BaseModel):
    user_id: int
    amount: int
    secret: str | None = None

class CreateLobbyRequest(BaseModel):
    host_id: int
    game: str = "ludo"
    max_players: int = 4

class JoinLobbyRequest(BaseModel):
    lobby_id: str
    user_id: int

@app.post('/api/credit')
async def credit(req: CreditRequest):
    # DEV: use WEBAPP_SHARED_SECRET env var check in production
    import os
    shared = os.environ.get('WEBAPP_SHARED_SECRET', 'WEBAPP_SHARED_SECRET')
    if req.secret != shared:
        raise HTTPException(status_code=403, detail='forbidden')
    # credit user in DB by touching bot module
    try:
        import sqlite3, os as _os
        from pathlib import Path
        db = str(Path(__file__).resolve().parents[1] / 'oneworld.db')
        conn = sqlite3.connect(db)
        cur = conn.cursor()
        cur.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (req.amount, req.user_id))
        conn.commit()
        conn.close()
        return {'ok': True, 'credited': req.amount}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/api/lobby/create')
async def create_lobby(req: CreateLobbyRequest):
    import uuid
    lobby_id = str(uuid.uuid4())[:8]
    with lobbies_lock:
        lobbies[lobby_id] = {
            'id': lobby_id,
            'game': req.game,
            'host': req.host_id,
            'players': [req.host_id],
            'max_players': req.max_players,
            'state': 'waiting'
        }
    return {'ok': True, 'lobby_id': lobby_id}

@app.post('/api/lobby/join')
async def join_lobby(req: JoinLobbyRequest):
    with lobbies_lock:
        lobby = lobbies.get(req.lobby_id)
        if not lobby:
            raise HTTPException(status_code=404, detail='lobby not found')
        if req.user_id in lobby['players']:
            return {'ok': True, 'lobby': lobby}
        if len(lobby['players']) >= lobby['max_players']:
            raise HTTPException(status_code=400, detail='lobby full')
        lobby['players'].append(req.user_id)
    return {'ok': True, 'lobby': lobby}

@app.get('/api/lobby/status/{lobby_id}')
async def lobby_status(lobby_id: str):
    with lobbies_lock:
        lobby = lobbies.get(lobby_id)
        if not lobby:
            raise HTTPException(status_code=404, detail='lobby not found')
    return {'ok': True, 'lobby': lobby}

@app.post('/api/lobby/start/{lobby_id}')
async def lobby_start(lobby_id: str):
    with lobbies_lock:
        lobby = lobbies.get(lobby_id)
        if not lobby:
            raise HTTPException(status_code=404, detail='lobby not found')
        if lobby['state'] != 'waiting':
            raise HTTPException(status_code=400, detail='already started')
        lobby['state'] = 'started'
    return {'ok': True, 'lobby': lobby}
