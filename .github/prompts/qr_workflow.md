---
mode: "sonnet"
---
# QR Export & Rebuild Workflow

**Agent**: Sonnet (implementer)
**Skills**: `.github/skills/reducer.md`, `.github/skills/validator.md`

End-to-end transfer of `create_budget_full_script.py` to an air-gapped machine via QR codes.

---

## Source Machine

### Step 1 — Reduce (optional but recommended)

Trigger: "reduce this file"

```powershell
python py_reducer.py create_budget_full_script.py
python -m py_compile create_budget_full_script_reduced.py
```

Expected:
- `create_budget_full_script_reduced.py` written.
- Size reduction ~18–20%.
- `py_compile`: no output.

### Step 2 — Export to QR

```powershell
python qr_create_budget_full_script.py
```

Expected:
```
Chunks exported : 30/30
Chunk SHA256s   : OK (all 30 validated)
```

Outputs written to:
```
qr_transfer/
├── qr_codes/     chunk_00.png … chunk_29.png
├── compressed/   chunk_00.txt … chunk_29.txt  (authoritative decoded text)
├── decoded/      (populated in next step)
└── rebuilt/      rebuild_from_qr.py
```

If chunk count changes from 30, re-run — do not proceed with a partial set.

### Step 3 — Decode QR PNGs (on source machine if scanning locally)

```powershell
python decode_qr_to_decoded.py --clear-output
```

Expected:
```
Decoded successfully: 30/30
```

If any chunk fails: copy the authoritative `.txt` files instead:
```powershell
Copy-Item qr_transfer\compressed\chunk_*.txt qr_transfer\decoded\
```

---

## Transfer

### Option A — Phone scan
1. Open each `qr_transfer/qr_codes/chunk_00.png` … `chunk_29.png` in order.
2. Scan with Google Lens, iOS Camera, or any QR app.
3. Save full decoded text (including header + `---`) as `chunk_00.txt` … `chunk_29.txt`.
4. Copy all `.txt` files to `qr_transfer/decoded/` on the target machine.

### Option B — Direct file copy (no scanning)
Copy `qr_transfer/compressed/chunk_*.txt` directly to `qr_transfer/decoded/` on the target machine.

---

## Target Machine

### Step 4 — Rebuild

```powershell
cd qr_transfer\rebuilt
python rebuild_from_qr.py
```

Expected:
```
SHA256 match: PASS
Rebuilt file: rebuilt_create_budget_full_script.py
```

If SHA256 fails:
- One or more chunk files are corrupt/incomplete — re-copy or re-scan those chunks only.
- Check `INDEX:` header in each chunk to identify which ones are missing or wrong.

### Step 5 — Validate rebuilt file

```powershell
python -m py_compile qr_transfer\rebuilt\rebuilt_create_budget_full_script.py
```

Expected: no output (syntax valid).

### Step 6 — Run on target

```powershell
python "C:\path\to\rebuilt_create_budget_full_script.py"
```

Expected: ExitCode=0, workbook written successfully.

---

## Verification summary

| Step | Command | Pass condition |
|---|---|---|
| Reduce | `py_compile create_budget_full_script_reduced.py` | No output |
| Export | `qr_create_budget_full_script.py` | 30/30 chunks, all SHA256 OK |
| Decode | `decode_qr_to_decoded.py --clear-output` | 30/30 decoded |
| Rebuild | `rebuild_from_qr.py` | SHA256 match: PASS |
| Validate rebuilt | `py_compile rebuilt_create_budget_full_script.py` | No output |

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Chunk count ≠ 30 | Source file changed since last export | Re-run `qr_create_budget_full_script.py` |
| SHA256 mismatch on rebuild | Corrupt/missing chunk | Re-copy from `qr_transfer/compressed/` |
| `py_compile` error on rebuilt file | Chunk out of order or truncated | Check `INDEX:` header in each decoded chunk |
| `decode_qr_to_decoded.py` partial failure | Dense QR — OpenCV fallback used pyzbar | Install `pyzbar`: `pip install --user pyzbar pillow` |
| `qrcode[pil]` missing on export | Dep not installed | `pip install --user qrcode[pil]` |
