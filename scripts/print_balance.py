#!/usr/bin/env python3

import os
import requests

RUNPOD_API_KEY = os.getenv("RUNPOD_API_KEY", "")
API_URL        = "https://api.runpod.io/graphql"

def gq(query, variables=None):
    r = requests.post(
        API_URL,
        json={"query": query, "variables": variables or {}},
        headers={"Authorization": RUNPOD_API_KEY},
        timeout=20
    )
    r.raise_for_status()
    j = r.json()
    if "errors" in j:
        raise RuntimeError(j["errors"])
    return j["data"]

def main():
    query = """query { me { id email accountBalance } }"""
    data  = gq(query)
    me    = data["me"]
    print("RunPod user ID:     ", me["id"])
    print("RunPod user email:  ", me["email"])
    print("RunPod balance:     ", me["accountBalance"])

if __name__ == "__main__":
    if not RUNPOD_API_KEY:
        print("[!] Missing RUNPOD_API_KEY in env.")
    else:
        main()
