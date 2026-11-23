"""Install the live V2 coach into an Ultimate Coach workbook (.xlsx -> .xlsm), from the same data the HTML embeds.

Why a macro engine: the V2 answer depends on availability, played players on both sides, the cap and skill already
used, put-up order and format, and is a look-ahead over the rest of the night. Precomputing every such state is not
feasible (roster subsets x caps x put-up turns), and worksheet formulas cannot express the recursive policy
reasonably, so the workbook carries the executed V2 policy as a VBA worksheet function (ui/excel_v2/UcV2Engine.bas)
that recalculates from the live cells. Only state-independent inputs are precomputed here, with the Python reference
code the HTML is tested against:

- V2 roster order and display names per team scope (analytics.uc_v2_inputs: memberOrder, wrDisplayName),
- the V2 win chance and matchup text of every pairing between teams of the same division and format
  (analytics.uc_v2_pair_model + analytics.uc_v2_explain), keyed by stable player IDs and skill levels.

Nothing in the existing workbook is removed or recalculated differently: a "V2 Coach" sheet, a V2 line on Command
Center and a hidden "V2 Data" sheet are added, and Excel itself saves the result, so formatting and features stay.
Trade-off (disclosed in the workbook): macros must be enabled, and Excel for the web / mobile cannot run the engine.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

from analytics.uc_v2_explain import pair_text
from analytics.uc_v2_inputs import V2Inputs
from analytics.uc_v2_pair_model import evidence_gaps, win_probability
from analytics.uc_v2_policy import POLICY_VERSION

BAS = Path(__file__).with_name("excel_v2") / "UcV2Engine.bas"
MODEL = Path(__file__).resolve().parents[1] / "analytics" / "uc_v2_model.json"
ARGS = ("wr_OurScope,wr_OppScope,wr_Category,wr_OurPids,wr_OurRemaining,wr_OurLineup,wr_OppPids,wr_OppUnplayed,wr_OppOut,"
        "wr_OppLabels,ll_Cap,'Command Center'!$C$6,'Five-Game Plan'!$B$5")
FORMATS = ("EIGHT", "NINE")


def sl_key(sl: Any) -> str:
    if sl is None:
        return ""
    return str(int(sl)) if float(sl).is_integer() else repr(float(sl))


def pair_key(fmt: str, m: dict[str, Any], t: dict[str, Any]) -> str:
    return f"{fmt}|{m['id']}|{sl_key(m['skill_level'])}|{t['id']}|{sl_key(t['skill_level'])}"


def v2_tables(compact: dict[str, Any]) -> tuple[list[tuple], list[tuple]]:
    """(roster rows, pair rows). Roster: scope, order, player id, display name, SL, SL key, format (browser order).
    Pairs: key, V2 win chance, matchup text, for every ordered pair of same-division, same-format team scopes."""
    inputs = V2Inputs(compact)
    roster_rows, by_group = [], {}
    for key in sorted(inputs.teams):
        team = inputs.teams[key]
        fmt = team["format"]
        members = inputs.roster(key)
        for k, m in enumerate(members, 1):
            roster_rows.append((key, k, str(m["id"]), inputs.display_name(m, members),
                                m["skill_level"], sl_key(m["skill_level"]), fmt))
        if fmt in FORMATS:
            by_group.setdefault((key.split("|")[1], fmt), []).append(key)
    pairs: dict[str, tuple] = {}
    for (_, fmt), scopes in sorted(by_group.items()):
        for a in scopes:
            for b in scopes:
                if a == b:
                    continue
                for m in inputs.roster(a):
                    for t in inputs.roster(b):
                        k = pair_key(fmt, m, t)
                        if k in pairs:
                            continue
                        kw = inputs.pair_inputs(m, t, fmt)
                        p = win_probability(fmt, m["skill_level"], t["skill_level"], **kw)
                        gaps = evidence_gaps(kw["direct"], kw["shared"], kw["form_p"], kw["form_o"],
                                             m["skill_level"], t["skill_level"])
                        pairs[k] = (k, p, pair_text(p, gaps))
    return roster_rows, sorted(pairs.values())


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def install(xlsx_in: str | Path, compact: dict[str, Any], xlsm_out: str | Path, *, meta: dict[str, str]) -> dict[str, Any]:
    """Open xlsx_in in Microsoft Excel, add the V2 coach, save as xlsm_out. Returns what was installed."""
    import pythoncom
    import win32com.client as win32

    pythoncom.CoInitialize()          # callers (e.g. the workbook validator) may have uninitialized COM on this thread

    xlsx_in, xlsm_out = Path(xlsx_in).resolve(), Path(xlsm_out).resolve()
    if xlsm_out.exists():
        raise FileExistsError(f"{xlsm_out} exists; never overwritten")
    roster, pairs = v2_tables(compact)
    stamp = hashlib.sha256(json.dumps([roster, pairs], sort_keys=True, default=str).encode()).hexdigest()
    info = dict(meta, policy=POLICY_VERSION, model_sha256=_sha(MODEL), engine_sha256=_sha(BAS),
                v2_inputs_sha256=stamp, roster_rows=str(len(roster)), pair_rows=str(len(pairs)))
    xl = win32.DispatchEx("Excel.Application")   # a fresh instance, never a running one
    xl.Visible = False
    xl.DisplayAlerts = False
    wb = None
    try:
        wb = xl.Workbooks.Open(str(xlsx_in), ReadOnly=True)
        last = wb.Worksheets(wb.Worksheets.Count)
        data = wb.Worksheets.Add(After=last)
        data.Name = "V2 Data"
        data.Range("A1").Value = "V2 engine inputs (generated; do not edit)"
        data.Range("A2").Value = "Stamp"
        data.Range("B2").Value = stamp
        data.Range("A3").Value = "Live trace"
        items = list(info.items())
        for n, (k, v) in enumerate(items, 4):
            data.Cells(n, 1).Value = k
            data.Cells(n, 2).NumberFormat = "@"
            data.Cells(n, 2).Value = str(v)
        top = 6 + len(items)
        data.Cells(top - 1, 1).Value = "Roster (scope, order, player id, display name, SL, SL key, format)"
        data.Cells(top - 1, 10).Value = "Pairs (key, V2 win chance, matchup text)"
        n_r, n_p = len(roster), len(pairs)
        for col in "ACDFG":
            data.Range(f"{col}{top}:{col}{top + n_r - 1}").NumberFormat = "@"
        data.Range(f"J{top}:J{top + n_p - 1}").NumberFormat = "@"
        data.Range(f"L{top}:L{top + n_p - 1}").NumberFormat = "@"
        data.Range(data.Cells(top, 1), data.Cells(top + n_r - 1, 7)).Value = [
            tuple("" if v is None else v for v in r) for r in roster]
        for start in range(0, n_p, 20000):
            chunk = pairs[start:start + 20000]
            data.Range(data.Cells(top + start, 10), data.Cells(top + start + len(chunk) - 1, 12)).Value = chunk
        wb.Names.Add(Name="v2_Stamp", RefersTo="='V2 Data'!$B$2")
        wb.Names.Add(Name="v2_Roster", RefersTo=f"='V2 Data'!$A${top}:$G${top + n_r - 1}")
        wb.Names.Add(Name="v2_Pairs", RefersTo=f"='V2 Data'!$J${top}:$L${top + n_p - 1}")
        # engine module (VBA import reads the Windows code page)
        with tempfile.TemporaryDirectory() as tmp:
            bas = Path(tmp) / "UcV2Engine.bas"
            bas.write_bytes(BAS.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\n", "\r\n").encode("cp1252"))
            wb.VBProject.VBComponents.Import(str(bas))
        data.Range("B3").Formula2 = f'=UC_V2("trace",{ARGS})'
        # V2 Coach sheet, right after START HERE
        coach = wb.Worksheets.Add(After=wb.Worksheets("START HERE"))
        coach.Name = "V2 Coach"
        coach.Range("A1").Value = "Ultimate Coach V2 — live answer"
        coach.Range("A1").Font.Bold = True
        coach.Range("A1").Font.Size = 18
        coach.Range("A2").Value = (
            "Recalculates from your marks: availability and played players on both sides (Lineup Lab), the opponent and teams (Match Day / "
            "War Room), the skill cap (Lineup Lab C7), who put up first (Five-Game Plan B5), their put-up (Command Center C6) "
            "and the format. Same V2 policy, model and data snapshot as the owner-review HTML. Win chances are estimates, "
            "not guarantees. Needs macros enabled in desktop Excel; Excel for the web and mobile cannot run it.")
        coach.Range("A3").Value = (f"Engine {POLICY_VERSION} · model {info['model_sha256'][:12]} · V2 inputs {stamp[:12]} · "
                                   f"data {meta.get('data_snapshot', '')}")
        coach.Range("A5").Formula2 = f'=UC_V2("table",{ARGS})'
        for col, width in zip("ABCDEF", (30, 26, 30, 14, 46, 90)):
            coach.Columns(col).ColumnWidth = width
        coach.Range("A2:A3").WrapText = False
        coach.Range("A5:F84").WrapText = True
        coach.Range("A5:F84").VerticalAlignment = -4160          # top
        coach.Range("A5:B5").Font.Bold = True
        coach.Range("A5:B5").Font.Size = 13
        # Command Center: the V2 answer to the live put-up, under "They put up:"
        cc = wb.Worksheets("Command Center")
        cc.Rows("7:8").Insert()
        cc.Range("B7").Value = "V2 answer (live):"
        cc.Range("B7").Font.Bold = True
        cc.Range("C7:K8").Merge()
        cc.Range("C7").Formula2 = f'=UC_V2("answer",{ARGS})'
        cc.Range("C7").WrapText = True
        cc.Range("C7").VerticalAlignment = -4160
        cc.Rows(7).RowHeight = 48
        cc.Rows(8).RowHeight = 48
        data.Visible = 0                                          # xlSheetHidden
        xl.CalculateFull()
        wb.SaveAs(str(xlsm_out), FileFormat=52)
        trace = data.Range("B3").Value
    finally:
        if wb is not None:
            wb.Close(SaveChanges=False)
        xl.Quit()
        pythoncom.CoUninitialize()
    return dict(info, out=str(xlsm_out), out_sha256=_sha(xlsm_out), trace=trace)
