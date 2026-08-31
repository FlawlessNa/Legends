r"""
Replaced by the profile-driven launcher.

This script used to hold one person's character, map and skills as edited-in
source, which does not survive more than one user. That configuration now lives
in `profiles/<name>.yaml`:

    copy profiles\example.yaml profiles\yourname.yaml
    python -m maple.launchers.run yourname

See docs/FIRST_BOT.md for the walkthrough.
"""

import sys

MESSAGE = __doc__.strip()

if __name__ == "__main__":
    print(MESSAGE, file=sys.stderr)
    raise SystemExit(2)
