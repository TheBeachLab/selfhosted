#!/usr/bin/env python3
"""Enable one email for signup without sending mail or choosing a master password.

API: https://github.com/dani-garcia/vaultwarden/blob/1.37.4/src/api/admin.rs
"""
import argparse
from http.cookiejar import CookieJar
import json
import os
from pathlib import Path
import re
from urllib.parse import urlencode
from urllib.request import build_opener, HTTPCookieProcessor, Request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('email')
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise SystemExit('Run as root on the NUC.')
    email = args.email.strip().lower()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
        raise SystemExit('Enter a valid email address.')
    # No SMTP host is configured. Never enable mail inside this helper.
    base = 'http://127.0.0.1:18080/admin'
    cookies = CookieJar()
    opener = build_opener(HTTPCookieProcessor(cookies))
    token = Path('/opt/vaultwarden/admin-token').read_text().strip()
    request = Request(base, data=urlencode({'token': token}).encode(),
                      headers={'Content-Type': 'application/x-www-form-urlencoded'})
    with opener.open(request, timeout=15) as response:
        response.read()
    if not any(cookie.name == 'VW_ADMIN' for cookie in cookies):
        raise RuntimeError('Admin authentication failed.')
    request = Request(base + '/invite', data=json.dumps({'email': email}).encode(),
                      headers={'Content-Type': 'application/json'})
    with opener.open(request, timeout=15) as response:
        result = json.load(response)
    if result.get('email', '').lower() != email:
        raise RuntimeError('Invitation readback did not match the requested email.')
    print('Signup enabled for ' + email + '; no email sent.')
    print('Open https://passwords.beachlab.org and sign in through Authentik.')


if __name__ == '__main__':
    main()
