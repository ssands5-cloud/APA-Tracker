"""Encrypt an approved private snapshot for the server-only historical dashboard.

UC_SNAPSHOT_KEY must be a base64-encoded random 32-byte secret provided privately.
This command never provisions authentication, publishes data, or prints key/record values.
"""
from __future__ import annotations
import argparse
import base64
import json
import os
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.repo_boundary import check_no_links, check_repository

FORMAT = 'ultimate-coach-private-snapshot-v1'
OUTPUT = ROOT / 'apps/ultimate-coach-web/private-snapshots/historical.enc.json'


def encrypt_snapshot(source: Path, key: bytes) -> dict:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    check_no_links(source, ROOT, 'private historical snapshot')
    if not source.resolve().is_relative_to((ROOT / 'tmp').resolve()):
        raise ValueError('Plaintext input must remain under ignored tmp/')
    if len(key) != 32:
        raise ValueError('A 32-byte snapshot key is required')
    raw = source.read_bytes()
    document = json.loads(raw)
    if document.get('schema') != 'ultimate-coach-dashboard-snapshot-v1' or document.get('mode') != 'historical-simulation':
        raise ValueError('Unsupported historical snapshot')
    iv = os.urandom(12)
    ciphertext = AESGCM(key).encrypt(iv, raw, FORMAT.encode())
    return {'format': FORMAT, 'iv': base64.b64encode(iv).decode(), 'ciphertext': base64.b64encode(ciphertext).decode()}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=ROOT / 'tmp/uat/protected-historical/snapshot.json')
    args = parser.parse_args(argv)
    check_repository(ROOT)
    try:
        key = base64.b64decode(os.environ.get('UC_SNAPSHOT_KEY', ''), validate=True)
        frame = encrypt_snapshot(args.input, key)
    except (ValueError, TypeError):
        raise SystemExit('Snapshot protection refused: verify private input and server key; nothing published.') from None
    check_no_links(OUTPUT, ROOT, 'encrypted historical snapshot')
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temp = OUTPUT.with_name(OUTPUT.name + '.' + uuid.uuid4().hex + '.tmp')
    check_no_links(temp, ROOT, 'encrypted snapshot temporary file')
    try:
        temp.write_text(json.dumps(frame, indent=2) + '\n', encoding='utf-8')
        os.replace(temp, OUTPUT)
    finally:
        temp.unlink(missing_ok=True)
    print('Encrypted server snapshot prepared. Authentication and authorized access still require verification.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
