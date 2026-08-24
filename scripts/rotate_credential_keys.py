"""Re-encrypt stored credentials under a newly prepended encryption key.

Procedure:
  1. Generate a new key:  python -m scripts.generate_keys
  2. Set CREDENTIAL_ENCRYPTION_KEYS="<new>,<old>" and redeploy.
  3. Run this script.
  4. Once it reports 0 remaining, drop <old> from the variable and redeploy.
"""

from __future__ import annotations

import sys

from app.core.database import SessionLocal
from app.services.credential_service import rotate_encryption


def main() -> int:
    db = SessionLocal()
    try:
        total = 0
        while True:
            rotated = rotate_encryption(db, batch_size=500)
            total += rotated
            if rotated == 0:
                break
        print(f"Re-encrypted {total} credential(s). Remaining under old keys: 0")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
