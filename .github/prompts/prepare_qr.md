---
mode: "sonnet"
---
# Prepare for QR Export

**Agent**: Sonnet (implementer)
**Trigger**: "prepare for qr export", "reduce this file", "make this smaller"
**Skills**: `.github/skills/reducer.md`, `.github/skills/validator.md`

---

## Rules (always apply)

- No silent changes. State what was removed and why.
- Output must be deterministic: same source always produces the same reduced file.
- No behavior changes except docstring/comment removal. Logic, file paths, function signatures, and command contracts are preserved. (Introspection via `__doc__` / `help()` will differ.)
- If behavior equivalence cannot be confirmed, do not proceed to QR export.

---

## Step 1 — Apply Reducer

```powershell
python py_reducer.py create_budget_full_script.py
```

Expected output:
```
Lines  :    7,124  →     6,042  (saved 1,082)
Chars  :  313,780  →   254,394  (saved ~19%)
Comment lines removed : 985
Docstring lines removed: 56
'pass' statements inserted: 0
```

Output file: `create_budget_full_script_reduced.py` (beside the source).

No changes are made to `create_budget_full_script.py`.

---

## Step 2 — Validate Syntax

```powershell
python -m py_compile create_budget_full_script_reduced.py
```

Expected: no output. Any output is a FAIL — stop and investigate before proceeding.

---

## Step 3 — Verify Semantic Equivalence (excluding docstrings)

Run the docstring-aware AST equivalence check. Removing docstrings changes the raw AST dump
(they are `ast.Expr` nodes), so compare node counts after accounting for removed docstring nodes:

```powershell
python -c "
import ast

def count_docstring_exprs(src):
    tree = ast.parse(src)
    return sum(
        1 for n in ast.walk(tree)
        if isinstance(n, ast.Expr)
        and isinstance(getattr(n, 'value', None), ast.Constant)
        and isinstance(n.value.value, str)
    )

orig_src = open('create_budget_full_script.py', encoding='utf-8-sig').read().lstrip('\ufeff')
red_src  = open('create_budget_full_script_reduced.py', encoding='utf-8').read()

orig_nodes = len(list(ast.walk(ast.parse(orig_src))))
red_nodes  = len(list(ast.walk(ast.parse(red_src))))
orig_docs  = count_docstring_exprs(orig_src)
red_docs   = count_docstring_exprs(red_src)

# Each docstring removed costs 2 AST nodes (Expr + Constant)
expected_delta = (orig_docs - red_docs) * 2
actual_delta   = orig_nodes - red_nodes
logic_delta    = actual_delta - expected_delta

print(f'Docstring nodes removed : {orig_docs - red_docs}')
print(f'Expected AST delta      : {expected_delta}')
print(f'Actual AST delta        : {actual_delta}')
print(f'Logic delta (must be 0) : {logic_delta}')
print('Behavior equivalence:', 'PASS' if logic_delta == 0 else 'FAIL')
"
```

Expected:
```
Logic delta (must be 0) : 0
Behavior equivalence: PASS
```

---

## Step 4 — Export to QR

Once Steps 1–3 pass, run:

```powershell
python qr_export.py --file create_budget_full_script_reduced.py
```

Or use the safe launcher (default targets the unreduced file; pass `--file` explicitly for reduced):

```powershell
python qr_create_budget_full_script.py --file create_budget_full_script_reduced.py
```

Expected:
```
Chunks exported : 30/30
Chunk SHA256s   : OK (all 30 validated)
```

---

## Verification Summary

| Step | Command | Pass condition |
|---|---|---|
| Reduce | `py_reducer.py create_budget_full_script.py` | `_reduced.py` written, stats printed |
| Syntax | `py_compile create_budget_full_script_reduced.py` | No output |
| Behavior | Docstring-aware AST node-count check | `Logic delta (must be 0): 0` + `PASS` |
| QR export | `qr_export.py --file <reduced_file>` | 30/30 chunks, all SHA256 OK |

---

## Fail-fast rules

- Stop at any failing step. Do not advance to QR export with an unverified file.
- If `AST match: False`: the reducer changed program structure. Open `create_budget_full_script_reduced.py` and compare manually before retrying.
- If chunk count changes between runs: the source file changed. Re-run from Step 1.

### Step 3: Semantic Equivalence (AST-normalized)

Goal: gate QR export on a strong semantic check that is deterministic.

Method:
- Parse both the source and reduced files into AST
- Normalize AST by:
  - removing docstrings in both
  - comparing st.dump(..., include_attributes=False) to ignore line/offset noise

Pass condition:
- AST match = True

Important scope note:
- This gate asserts semantic equivalence excluding:
  - comments
  - docstrings
  - introspection output (__doc__, help() text)

