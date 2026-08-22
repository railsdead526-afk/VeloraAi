"""Generate the secrets a fresh environment needs.

python -m scripts.generate_keys            # print values
python -m scripts.generate_keys --write    # patch a local .env in place
"""

from __future__ import annotations

import argparse
import pathlib
import re
import secrets

from app.core.crypto import generate_key

KEYS = {
    "SECRET_KEY": lambda: secrets.token_urlsafe(48),
    "CREDENTIAL_ENCRYPTION_KEYS": generate_key,
    "METRICS_TOKEN": lambda: secrets.token_urlsafe(24),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="patch ./.env in place")
    args = parser.parse_args()

    generated = {name: factory() for name, factory in KEYS.items()}

    if not args.write:
        for name, value in generated.items():
            print(f"{name}={value}")
        return 0

    env_path = pathlib.Path(".env")
    if not env_path.exists():
        print("No .env found. Copy .env.example to .env first.")
        return 1

    content = env_path.read_text()
    for name, value in generated.items():
        pattern = rf"^{name}=.*$"
        replacement = f"{name}={value}"
        content = (
            re.sub(pattern, replacement, content, flags=re.MULTILINE)
            if re.search(pattern, content, flags=re.MULTILINE)
            else content.rstrip("\n") + f"\n{replacement}\n"
        )
    env_path.write_text(content)
    print(f"Wrote {', '.join(generated)} to {env_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
