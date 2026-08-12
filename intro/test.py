#!/usr/bin/env python3

import os
import json
from pathlib import Path
import requests

def section(title):
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)

def ok(msg):
    print(f"✅ {msg}")

def bad(msg):
    print(f"❌ {msg}")

def info(msg):
    print(f"   {msg}")

section("OpenShell Demo: Filesystem, Network")

# ---------------------------------------------------------------------
# 1. FILESYSTEM TESTS
# ---------------------------------------------------------------------
section("1. Filesystem controls")

tests = [
    ("write allowed file", "write", "/tmp/openshell_allowed.txt"),
    ("write blocked file", "write", "/app/openshell_should_not_write.txt"),
    ("read likely blocked secret", "read", "/root/.ssh/id_rsa"),
    ("read system file", "read", "/etc/hosts"),
]

for name, op, path in tests:
    try:
        if op == "write":
            Path(path).write_text("OpenShell demo write\n")
            ok(f"{name}: succeeded at {path}")
        else:
            content = Path(path).read_text(errors="ignore")[:120]
            ok(f"{name}: succeeded at {path}")
            info(repr(content))
    except Exception as e:
        bad(f"{name}: blocked/failed at {path}")
        info(f"{type(e).__name__}: {e}")

# ---------------------------------------------------------------------
# 2. NETWORK TESTS
# ---------------------------------------------------------------------
section("2. Network controls")

network_tests = [
    ("allowed GitHub /zen", "GET", "https://api.github.com/zen"),
    ("blocked GitHub different path", "GET", "https://api.github.com/users/octocat"),
    ("blocked unlisted host", "GET", "https://www.google.com"),
]

for name, method, url in network_tests:
    try:
        r = requests.request(method, url, timeout=8)
        ok(f"{name}: HTTP {r.status_code}")
        info(r.text[:250].replace("\n", " "))
    except Exception as e:
        bad(f"{name}: blocked/failed")
        info(f"{type(e).__name__}: {e}")

