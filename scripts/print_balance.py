#!/usr/bin/env python3
import os
import requests
import sys

API_URL = "https://rest.runpod.io/account"

def main():
    runpod_api_key = os.getenv("RUNPOD_API_KEY", "")
    if not runpod_api_key:
        sys.exit("[ERROR] RUNPOD_API_KEY is missing or empty.")

    headers = {
        "Authorization": f"Bearer {runpod_api_key}",
        "Content-Type": "application/json",
    }

    resp = requests.get(API_URL, headers=headers, timeout=20)
    if not resp.ok:
        print("[ERROR] GET /account failed.")
        print("Status:", resp.status_code)
        print("Response:", resp.text)
        resp.raise_for_status()

    data = resp.json()  # should contain fields like 'accountType', 'balance', 'email'
    print("[INFO] RunPod Account Info:")
    print("  Email:", data.get("email"))
    print("  Balance:", data.get("balance"))
    print("  Account Type:", data.get("accountType"))
    # Add or remove prints as needed

if __name__ == "__main__":
    main()
