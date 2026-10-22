#!/usr/bin/env python3
"""Keep arroyo.ing's apex IPv4 on Cloudflare aligned with this NUC.
API reference: https://developers.cloudflare.com/api/resources/dns/subresources/records/
"""
import ipaddress
import json
from pathlib import Path
from urllib.request import Request, urlopen

ZONE = 'acc70087bb85ea5da695e277bf0f2d1d'
NAME = 'arroyo.ing'

def main():
    token = next(line.split('=', 1)[1].strip().strip('\"\x27') for line in Path('/etc/cloudflare-arroyo.env').read_text().splitlines() if line.startswith('CLOUDFLARE_API_TOKEN='))
    def api(path, method='GET', body=None):
        request = Request('https://api.cloudflare.com/client/v4/zones/' + ZONE + path, method=method, data=json.dumps(body).encode() if body is not None else None, headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
        with urlopen(request, timeout=20) as response:
            result = json.load(response)
        if not result.get('success'):
            raise RuntimeError('Cloudflare DNS request failed')
        return result['result']
    with urlopen('https://api.ipify.org', timeout=15) as response:
        ip = response.read().decode().strip()
    address = ipaddress.ip_address(ip)
    if address.version != 4 or not address.is_global:
        raise RuntimeError('Expected a public IPv4')
    route = '/dns_records?type=A&name=' + NAME
    records = api(route)
    if len(records) != 1:
        raise RuntimeError('Expected exactly one existing apex A record')
    record = records[0]
    if record['content'] != ip:
        api('/dns_records/' + record['id'], 'PATCH', {'content': ip})
    readback = api(route)
    if len(readback) != 1 or readback[0]['content'] != ip:
        raise RuntimeError('DNS readback failed')
    print('arroyo.ing IPv4 verified against Cloudflare.')

if __name__ == '__main__':
    main()
