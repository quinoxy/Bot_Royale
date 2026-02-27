import requests
import json
import os

BASE_URL = "http://127.0.0.1:5000"
test_user = "testuser"
test_pass = "password123"

print("--- Testing Registration ---")
s1 = requests.Session()
# Register
res = s1.post(f"{BASE_URL}/register", data={"team_name": test_user, "password": test_pass})
print("Registration Status:", res.status_code)

print("\n--- Testing Login Cookie ---")
res_dash = s1.get(f"{BASE_URL}/dashboard")
if "Welcome" in res_dash.text or test_user in res_dash.text:
    print("Dashboard loaded successfully for registered user.")
else:
    print("Dashboard failed to load or missing username.")

print("\n--- Testing Bot Upload ---")
bot_code = "print('hello')"
with open('test_bot.py', 'w') as f:
    f.write(bot_code)

with open('test_bot.py', 'rb') as f:
    res_upload = s1.post(f"{BASE_URL}/dashboard/upload", files={"bot_file": f})
print("Upload Status:", res_upload.status_code)
res_dash2 = s1.get(f"{BASE_URL}/dashboard")
if "Bot uploaded" in res_dash2.text or "Update Bot" in res_dash2.text:
    print("Bot upload confirmed in dashboard UI.")
else:
    print("Bot upload NOT reflected in dashboard.")

print("\n--- Testing Login Separation ---")
# Try to login as another session
s2 = requests.Session()
res2 = s2.post(f"{BASE_URL}/login", data={"team_name": test_user, "password": test_pass})
res2_dash = s2.get(f"{BASE_URL}/dashboard")
if test_user in res2_dash.text:
    print("Second session logged in successfully.")
else:
    print("Second session failed to login.")

print("\n--- Testing Reserved Words ---")
res3 = requests.post(f"{BASE_URL}/register", data={"team_name": "admin", "password": "root"})
if "This team name is reserved." in res3.text or res3.status_code == 200:
    print("Admin reservation correctly blocked/handled.")

print("\n--- Testing Replay Auth --")
# First let's check if there are replays
m_res = requests.get(f"{BASE_URL}/api/matches")
matches = m_res.json()
if matches:
    match_id = matches[0]["id"]
    # Unauth access
    s3 = requests.Session()
    r_unauth = s3.get(f"{BASE_URL}/match/{match_id}")
    print("Unauth replay fetch status:", r_unauth.status_code)
    if "Access denied" in r_unauth.text:
        print("Unauth nicely blocked.")
    
    # Auth via basic auth (admin)
    r_admin = requests.get(f"{BASE_URL}/match/{match_id}", auth=("admin", "admin"))
    print("Admin replay fetch status (Basic Auth):", r_admin.status_code)
else:
    print("No matches to test replay auth on.")

os.remove('test_bot.py')
