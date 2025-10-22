from flask import Flask, request, jsonify, send_from_directory, abort
import threading, os, sqlite3
from pathlib import Path

app = Flask(__name__, static_folder='.', static_url_path='')

@app.route('/webapp/<path:filename>')
def static_files(filename):
    root = os.path.join(os.path.dirname(__file__))
    return send_from_directory(root, filename)

@app.route('/webapp/')
def index():
    root = os.path.join(os.path.dirname(__file__))
    return send_from_directory(root, 'index.html')

@app.route('/api/credit', methods=['POST'])
def credit():
    data = request.get_json() or {}
    secret = os.environ.get('WEBAPP_SHARED_SECRET', 'WEBAPP_SHARED_SECRET')
    if data.get('secret') != secret:
        return jsonify({'ok': False, 'error': 'forbidden'}), 403
    uid = int(data.get('user_id'))
    amt = int(data.get('amount', 0))
    db = str(Path(__file__).resolve().parents[1] / 'oneworld.db')
    try:
        conn = sqlite3.connect(db)
        cur = conn.cursor()
        cur.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amt, uid))
        conn.commit()
        conn.close()
        return jsonify({'ok': True, 'credited': amt})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

if __name__ == '__main__':
    host = os.environ.get('WEBAPP_HOST', '0.0.0.0')
    port = int(os.environ.get('WEBAPP_PORT', '8082'))
    print('Starting flask webapp on', host, port)
    app.run(host=host, port=port)
