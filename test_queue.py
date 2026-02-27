import requests
import time
import os

BASE_URL = "http://127.0.0.1:5000"

print("--- Registering/Logging In Test Users ---")
s1 = requests.Session()
s1.post(f"{BASE_URL}/register", data={"team_name": "botA", "password": "pass"})
s1.post(f"{BASE_URL}/login", data={"team_name": "botA", "password": "pass"})

s2 = requests.Session()
s2.post(f"{BASE_URL}/register", data={"team_name": "botB", "password": "pass"})
s2.post(f"{BASE_URL}/login", data={"team_name": "botB", "password": "pass"})

# Create two bots: a fast one and a terribly slow one.
fast_bot = """import sys, json
while True:
    state = json.loads(input())
    print("0 0")
"""

slow_bot = """import sys, json, time
while True:
    state = json.loads(input())
    time.sleep(61)
    print("0 0")
"""

with open("fast.py", "w") as f: f.write(fast_bot)
with open("slow.py", "w") as f: f.write(slow_bot)


print("\n--- Testing Uploads & Quotas ---")
with open("fast.py", "rb") as f:
    s1.post(f"{BASE_URL}/dashboard/upload", files={"bot_file": f})
print("Uploaded botA (fast)")

with open("slow.py", "rb") as f:
    s2.post(f"{BASE_URL}/dashboard/upload", files={"bot_file": f})
print("Uploaded botB (slow). This should enqueue two matches.")

print("\n--- Testing 5-minute Cooldown ---")
with open("fast.py", "rb") as f:
    r = s1.post(f"{BASE_URL}/dashboard/upload", files={"bot_file": f})
if "Please wait" in r.text or "seconds before uploading" in r.text:
    print("[SUCCESS] Cooldown block triggered correctly.")
else:
    print("[FAIL] Cooldown did not trigger.")


print("\n--- Testing API Route Queue Extraction ---")
r_queue = s1.get(f"{BASE_URL}/admin/queue-status", auth=("admin", "password"))
if r_queue.status_code == 200:
    data = r_queue.json()
    print("Queue API Status:", data)
    if data["length"] == 2:
        print("[SUCCESS] Queue contains exactly 2 matches.")
else:
    print("[FAIL] Admin API /queue-status broken or authentication failed.", r_queue.status_code)


print("\n--- Running Timebank Matches ---")

status = s1.get(f"{BASE_URL}/admin/queue-status", auth=("admin", "password")).json()
if status["paused"]:
    r_toggle = s1.post(f"{BASE_URL}/admin/queue-toggle", auth=("admin", "password"))
    print("Queue unpaused", r_toggle.json())
else:
    print("Queue was already running")

time.sleep(1) # Let the background worker pick it up
start_wait = time.time()
while True:
    status = s1.get(f"{BASE_URL}/admin/queue-status", auth=("admin", "password")).json()
    if status["length"] == 0:
        break
    if time.time() - start_wait > 75: # Because slow_bot sleeps 61s, it should finish soon.
        print("Waiting too long for timebank DQ...")
        break
    time.sleep(2)

print("\n--- Checking Match Results ---")
# The matches should record slow_bot as disqualified.
matches = s1.get(f"{BASE_URL}/api/team/botB/matches").json()
for m in matches:
    print(m["result_desc"])
    if "ran out of time" in m["result_desc"] or "DQ" in m["winner"]:
        print("[SUCCESS] 60-second Timebank limit enforced.")

os.remove("fast.py")
os.remove("slow.py")
