#!/usr/bin/env python3
"""Wake the NUC's native Msgvault discovery worker; this runner does no AI work.

The owner credential is read in memory. Jev credentials, messages and provider
requests remain inside the native daemon. Journal output contains counts only.
"""
import json
from pathlib import Path
import re
import sys
import urllib.error
import urllib.request

CONFIG = Path("/var/lib/msgvault/config.toml")
ORIGIN = "http://127.0.0.1:8096"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def owner_key():
    # Ubuntu's /usr/bin/python3 predates tomllib. Read only the known native
    # hexadecimal owner-key field; do not source a shell file or install a
    # second runtime for a loopback wake-up. Support native TOML single quotes.
    section = re.search(r"(?ms)^[ \t]*\[server\][^\n]*\n(.*?)(?=^[ \t]*\[|\Z)",
                        CONFIG.read_text())
    if section is None:
        raise RuntimeError("Expected the native server configuration")
    keys = re.findall(r"(?m)^[ \t]*api_key[ \t]*=[ \t]*([\"'])([0-9a-f]{64})\1[ \t]*$",
                      section.group(1))
    if len(keys) != 1:
        raise RuntimeError("Expected one native owner credential")
    return keys[0][1]


def run():
    key = owner_key()
    request = urllib.request.Request(
        ORIGIN + "/api/v1/identity/discovery/run",
        data=b'{"limit":8}',
        headers={"Authorization": "Bearer " + key,
                 "Content-Type": "application/json",
                 "User-Agent": "msgvault-mailbox-timer/1"},
    )
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=540) as response:
        result = json.loads(response.read(1 << 20))
    counts = {name: result[name] for name in
              ("scanned_messages", "candidates", "provider_requests", "next_cursor",
               "signed_message_changes", "briefs_generated")}
    counts["saved_results"] = len(result["results"])
    counts["shared"] = sum(item["status"] == "shared" for item in result["results"])
    counts["error"] = result.get("error", "")
    print(json.dumps(counts, sort_keys=True))
    if counts["error"]:
        raise RuntimeError("native discovery stopped: " + counts["error"])


if __name__ == "__main__":
    try:
        run()
    except urllib.error.HTTPError as error:
        print("Native discovery returned HTTP " + str(error.code), file=sys.stderr)
        sys.exit(1)
    except (OSError, ValueError, KeyError, RuntimeError):
        # Avoid exceptions containing a request, a config line or private input.
        print("Native discovery unavailable; check its authenticated status/history", file=sys.stderr)
        sys.exit(1)
