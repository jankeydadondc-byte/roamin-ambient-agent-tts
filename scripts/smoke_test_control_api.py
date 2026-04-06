import json
import time

import requests

base = "http://127.0.0.1:8765"


def show(title, obj):
    print("---", title)
    print(json.dumps(obj, indent=2))


resp = requests.get(base + "/status")
show("status", resp.json())

resp = requests.post(base + "/plugins/install", json={"id": "test.plugin", "name": "Test Plugin"})
print("install:", resp.status_code, resp.text)

# wait for background install to complete
time.sleep(1.5)

resp = requests.get(base + "/plugins")
show("plugins", resp.json())

resp = requests.post(base + "/plugins/test.plugin/action", json={"action": "disable"})
print("action disable:", resp.status_code, resp.text)

resp = requests.post(base + "/plugins/test.plugin/action", json={"action": "enable"})
print("action enable:", resp.status_code, resp.text)

resp = requests.get(base + "/task-history")
show("tasks", resp.json())
