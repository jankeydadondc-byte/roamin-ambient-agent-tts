import time

import websocket

url = "ws://127.0.0.1:8765/ws/events"
print("connecting to", url)
ws = websocket.WebSocket()
try:
    ws.connect(url)
    print("connected")
    start = time.time()
    while time.time() - start < 5:
        try:
            msg = ws.recv()
            print("RECV:", msg)
        except Exception as e:
            print("recv error", e)
            break
finally:
    try:
        ws.close()
    except Exception:
        pass
