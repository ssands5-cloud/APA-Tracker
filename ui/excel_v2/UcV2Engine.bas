Attribute VB_Name = "UcV2Engine"
' Ultimate Coach V2 live engine for the workbook: the executed V2 captain-control policy (analytics/uc_v2_policy.py,
' browser v2Policy / v2Classify / v2OptionsText) recomputed from the workbook's live marks on every recalculation.
' Inputs: the V2 roster order, display names and per-pairing V2 win chances written by ui/excel_v2_coach.py from the
' same compact payload the HTML embeds (sheet "V2 Data"), plus the live War Room / Lineup Lab / Command Center cells.
' No model, coefficient, threshold or wording is decided here: every rule mirrors the Python reference, which is
' tested against the HTML. A missing input fails closed with a message; there is no M3 fallback.
Option Explicit

Private Const EPS As Double = 0.000000000001
Private Const PRACTICAL_TIE As Double = 0.01
Private Const PLAN_TIE As Double = 0.02
Private Const STRATEGIC_GAIN As Double = 0.1
Private Const INF As Double = 1E+308
Private Const MAX_PLAYERS As Long = 16

Private BITV(0 To 30) As Long
Private nO As Long, nT As Long
Private oId() As String, oNm() As String, oKn() As Boolean, oSl() As Double
Private tId() As String, tNm() As String, tKn() As Boolean, tSl() As Double
Private PP() As Double, PT() As String
Private gGames As Long, gCapOn As Boolean, gCap As Double, gUsed As Double
Private gOppCapOn As Boolean, gOppUsed As Double
Private fullO As Long, fullT As Long
Private stD As Object, rsD As Object, lgD As Object, tlD As Object
Private sW() As Double, sA() As Double, sHasLead() As Boolean, sLeadI() As Long, sLeadR() As Long, sWorst() As Long, sN As Long
Private rW() As Double, rA() As Double, rPick() As Long, rRole() As String, rN As Long

' ---- loaded V2 data (from the "V2 Data" sheet) ----
Private gStamp As String
Private rosterIdx As Object          ' scope -> "first,count" into the roster arrays
Private rsPid() As String, rsName() As String, rsKn() As Boolean, rsSl() As Double, rsKey() As String, rsFmt() As String
Private pairIdx As Object            ' key -> row
Private prP() As Double, prT() As String

' ---- result cache (one computation per distinct input state) ----
Private gSig As String
Private gTrace As String, gAnswer As String, gTable As Variant

' ============================== public worksheet functions ==============================

' view: "answer" (one line for Command Center), "table" (the V2 Coach sheet, spills), "trace" (machine-readable, tests)
Public Function UC_V2(view As String, ourScope As Variant, oppScope As Variant, fmt As Variant, ourPids As Variant, _
                     ourRemaining As Variant, ourLineup As Variant, oppPids As Variant, oppUnplayed As Variant, _
                     oppLabels As Variant, cap As Variant, putUp As Variant, firstPutUp As Variant) As Variant
    On Error GoTo Failed
    Dim a() As Variant, sig As String
    a = Array(V1(ourScope), V1(oppScope), V1(fmt), Flat(ourPids), Flat(ourRemaining), Flat(ourLineup), Flat(oppPids), _
              Flat(oppUnplayed), Flat(oppLabels), V1(cap), V1(putUp), V1(firstPutUp))
    LoadData
    sig = gStamp & Chr(1) & Join(a, Chr(1))
    If sig <> gSig Then
        Compute a(0), a(1), a(2), ourPids, ourRemaining, ourLineup, oppPids, oppUnplayed, oppLabels, a(9), a(10), a(11)
        gSig = sig
    End If
    Select Case LCase(view)
        Case "answer": UC_V2 = gAnswer
        Case "trace": UC_V2 = gTrace
        Case Else: UC_V2 = gTable
    End Select
    Exit Function
Failed:
    gSig = ""
    UC_V2 = "V2 engine error: " & Err.Description & " — no recommendation shown (no fallback)."
End Function

' ============================== data loading ==============================

Private Sub LoadData()
    Dim stamp As String, v As Variant, i As Long, n As Long, s As String, cur As String, first As Long
    stamp = CStr(ThisWorkbook.Names("v2_Stamp").RefersToRange.Value)
    If stamp = gStamp And Not rosterIdx Is Nothing Then Exit Sub
    v = ThisWorkbook.Names("v2_Roster").RefersToRange.Value
    n = UBound(v, 1)
    ReDim rsPid(1 To n): ReDim rsName(1 To n): ReDim rsKn(1 To n): ReDim rsSl(1 To n): ReDim rsKey(1 To n): ReDim rsFmt(1 To n)
    Set rosterIdx = CreateObject("Scripting.Dictionary")
    cur = "": first = 0
    For i = 1 To n
        s = CStr(v(i, 1))
        rsPid(i) = CStr(v(i, 3)): rsName(i) = CStr(v(i, 4)): rsKey(i) = CStr(v(i, 6)): rsFmt(i) = CStr(v(i, 7))
        If IsNumeric(v(i, 5)) And Not IsEmpty(v(i, 5)) And CStr(v(i, 5)) <> "" Then
            rsSl(i) = CDbl(v(i, 5)): rsKn(i) = rsSl(i) > 0
        Else
            rsSl(i) = 0: rsKn(i) = False
        End If
        If s <> cur Then
            If cur <> "" Then rosterIdx(cur) = first & "," & (i - first)
            cur = s: first = i
        End If
    Next i
    If cur <> "" Then rosterIdx(cur) = first & "," & (n + 1 - first)
    v = ThisWorkbook.Names("v2_Pairs").RefersToRange.Value
    n = UBound(v, 1)
    ReDim prP(1 To n): ReDim prT(1 To n)
    Set pairIdx = CreateObject("Scripting.Dictionary")
    For i = 1 To n
        pairIdx(CStr(v(i, 1))) = i
        prP(i) = CDbl(v(i, 2)): prT(i) = CStr(v(i, 3))
    Next i
    gStamp = stamp
    gSig = ""
End Sub

' ============================== state from the workbook ==============================

Private Sub Compute(ourScope As Variant, oppScope As Variant, fmt As Variant, ourPids As Variant, ourRemaining As Variant, _
                    ourLineup As Variant, oppPids As Variant, oppUnplayed As Variant, oppLabels As Variant, _
                    cap As Variant, putUp As Variant, firstPutUp As Variant)
    Dim k As Long
    For k = 0 To 30: BITV(k) = 2 ^ k: Next k
    gTrace = "": gAnswer = "": gTable = Empty
    Dim status As String
    status = Prepare(CStr(ourScope), CStr(oppScope), CStr(fmt), ourPids, ourRemaining, ourLineup, oppPids, oppUnplayed, cap)
    Dim tossKnown As Boolean, tossUs As Boolean, nextUs As Boolean, playedN As Long
    tossKnown = (CStr(firstPutUp) = "We put up first" Or CStr(firstPutUp) = "They put up first")
    tossUs = (CStr(firstPutUp) = "We put up first")
    playedN = 5 - gGames
    nextUs = ((playedN Mod 2) = 0) = tossUs
    If status <> "" Then
        gAnswer = status
        gTrace = "{""status"":" & JStr(status) & "}"
        gTable = Table(status, False, False, False, "")
        Exit Sub
    End If
    BuildOutputs CStr(putUp), oppPids, oppLabels, tossKnown, nextUs
End Sub

Private Function Prepare(ourScope As String, oppScope As String, fmt As String, ourPids As Variant, ourRemaining As Variant, _
                         ourLineup As Variant, oppPids As Variant, oppUnplayed As Variant, cap As Variant) As String
    nO = 0: nT = 0: gGames = 0
    If ourScope = "" Or oppScope = "" Then Prepare = "Choose your team and the opponent (Match Day or War Room) to see the V2 answer.": Exit Function
    If fmt <> "EIGHT" And fmt <> "NINE" Then Prepare = "V2 has no pairing model for this format (8-Ball and 9-Ball only). No recommendation shown.": Exit Function
    If Not rosterIdx.Exists(ourScope) Then Prepare = "V2 data has no roster for your team in this snapshot. No recommendation shown.": Exit Function
    If Not rosterIdx.Exists(oppScope) Then Prepare = "V2 data has no roster for this opponent in this snapshot. No recommendation shown.": Exit Function
    Dim pidsO As Variant, remO As Variant, lineO As Variant, pidsT As Variant, unpT As Variant
    pidsO = Grid(ourPids): remO = Grid(ourRemaining): lineO = Grid(ourLineup): pidsT = Grid(oppPids): unpT = Grid(oppUnplayed)
    Dim remD As Object, played As Object, unp As Object, r As Long, p As String
    Set remD = CreateObject("Scripting.Dictionary"): Set played = CreateObject("Scripting.Dictionary")
    Set unp = CreateObject("Scripting.Dictionary")
    For r = 1 To UBound(pidsO, 1)
        p = CStr(pidsO(r, 1))
        If p <> "" Then remD(p) = IsTrue(remO(r, 1)): played(p) = (CStr(lineO(r, 1)) = "Played")
    Next r
    For r = 1 To UBound(pidsT, 1)
        p = CStr(pidsT(r, 1))
        If p <> "" Then unp(p) = IsTrue(unpT(r, 1))
    Next r
    Dim f0 As Long, c0 As Long, f1 As Long, c1 As Long, i As Long
    Span ourScope, f0, c0
    Span oppScope, f1, c1
    If c0 <> remD.Count Or c1 <> unp.Count Then Prepare = "V2 roster differs from the workbook roster for this pairing. No recommendation shown.": Exit Function
    For i = f0 To f0 + c0 - 1
        If Not remD.Exists(rsPid(i)) Or rsFmt(i) <> fmt Then Prepare = "V2 roster differs from the workbook roster for this pairing. No recommendation shown.": Exit Function
    Next i
    For i = f1 To f1 + c1 - 1
        If Not unp.Exists(rsPid(i)) Or rsFmt(i) <> fmt Then Prepare = "V2 roster differs from the workbook roster for this pairing. No recommendation shown.": Exit Function
    Next i
    ' ours = remaining roster members in V2 roster order; played count and played skill as the page (mnInputs)
    Dim oRow() As Long, tRow() As Long, playedN As Long, playedSl As Double, oppUsed As Double
    ReDim oRow(0 To MAX_PLAYERS): ReDim tRow(0 To MAX_PLAYERS)
    For i = f0 To f0 + c0 - 1
        If played(rsPid(i)) Then
            playedN = playedN + 1
            If rsKn(i) Then playedSl = playedSl + rsSl(i)
        End If
        If remD(rsPid(i)) Then
            If nO >= MAX_PLAYERS Then Prepare = "More than 16 remaining players: beyond the V2 engine's limit.": Exit Function
            oRow(nO) = i: nO = nO + 1
        End If
    Next i
    For i = f1 To f1 + c1 - 1
        If unp(rsPid(i)) Then
            If nT >= MAX_PLAYERS Then Prepare = "More than 16 opponent players: beyond the V2 engine's limit.": Exit Function
            tRow(nT) = i: nT = nT + 1
        ElseIf rsKn(i) Then
            oppUsed = oppUsed + Fix(rsSl(i))
        End If
    Next i
    ReDim oId(0 To MAX_PLAYERS): ReDim oNm(0 To MAX_PLAYERS): ReDim oKn(0 To MAX_PLAYERS): ReDim oSl(0 To MAX_PLAYERS)
    ReDim tId(0 To MAX_PLAYERS): ReDim tNm(0 To MAX_PLAYERS): ReDim tKn(0 To MAX_PLAYERS): ReDim tSl(0 To MAX_PLAYERS)
    ReDim PP(0 To MAX_PLAYERS, 0 To MAX_PLAYERS): ReDim PT(0 To MAX_PLAYERS, 0 To MAX_PLAYERS)
    Dim j As Long, key As String
    For i = 0 To nO - 1
        oId(i) = rsPid(oRow(i)): oNm(i) = rsName(oRow(i)): oKn(i) = rsKn(oRow(i)): oSl(i) = rsSl(oRow(i))
    Next i
    For j = 0 To nT - 1
        tId(j) = rsPid(tRow(j)): tNm(j) = rsName(tRow(j)): tKn(j) = rsKn(tRow(j)): tSl(j) = rsSl(tRow(j))
    Next j
    For i = 0 To nO - 1
        For j = 0 To nT - 1
            key = fmt & "|" & oId(i) & "|" & rsKey(oRow(i)) & "|" & tId(j) & "|" & rsKey(tRow(j))
            If Not pairIdx.Exists(key) Then
                Prepare = "No V2 win chance for " & oNm(i) & " vs " & tNm(j) & " in this snapshot (teams outside one division are not precomputed). No recommendation shown."
                Exit Function
            End If
            PP(i, j) = prP(pairIdx(key)): PT(i, j) = prT(pairIdx(key))
        Next j
    Next i
    gGames = 5 - playedN
    gUsed = playedSl: gOppUsed = oppUsed
    gCapOn = False: gCap = 0
    If Not IsEmpty(cap) Then
        If IsNumeric(cap) And CStr(cap) <> "" Then
            If Int(CDbl(cap)) > 0 Then gCapOn = True: gCap = Int(CDbl(cap))
        End If
    End If
    ResetNight
    gOppCapOn = gCapOn
    If gCapOn And gGames <> 0 Then
        Dim ta() As Long, nt0 As Long
        LegalTheirs fullO, fullT, ta, nt0
        If nt0 = 0 Then gOppCapOn = False: ResetNight
    End If
    Prepare = ""
End Function

Private Sub ResetNight()
    fullO = BITV(nO) - 1: fullT = BITV(nT) - 1
    Set stD = CreateObject("Scripting.Dictionary"): Set rsD = CreateObject("Scripting.Dictionary")
    Set lgD = CreateObject("Scripting.Dictionary"): Set tlD = CreateObject("Scripting.Dictionary")
    sN = 0: rN = 0
    ReDim sW(0 To 255): ReDim sA(0 To 255): ReDim sHasLead(0 To 255): ReDim sLeadI(0 To 255): ReDim sLeadR(0 To 255): ReDim sWorst(0 To 255)
    ReDim rW(0 To 255): ReDim rA(0 To 255): ReDim rPick(0 To 255): ReDim rRole(0 To 255)
End Sub

' ============================== _Night legality (analytics/match_night_engine.py) ==============================

Private Function Pop(ByVal m As Long) As Long
    Dim c As Long
    Do While m <> 0
        c = c + (m And 1)
        m = (m And &H7FFFFFFE) \ 2
    Loop
    Pop = c
End Function

Private Function GamesRem(om As Long) As Long
    GamesRem = gGames - (Pop(fullO) - Pop(om))
End Function

Private Sub SortAsc(a() As Double, n As Long)
    Dim i As Long, j As Long, x As Double
    For i = 1 To n - 1
        x = a(i): j = i - 1
        Do While j >= 0
            If a(j) <= x Then Exit Do
            a(j + 1) = a(j): j = j - 1
        Loop
        a(j + 1) = x
    Next i
End Sub

Private Function Legal(om As Long, i As Long, gAfter As Long) As Boolean
    If Not gCapOn Then Legal = True: Exit Function
    Dim key As String
    key = om & ":" & i
    If lgD.Exists(key) Then Legal = lgD(key): Exit Function
    Dim rest() As Double, nr As Long, unk As Long, k As Long, spent As Double, own As Double, need As Long, total As Double
    ReDim rest(0 To nO)
    For k = 0 To nO - 1
        If (om And BITV(k)) <> 0 Then
            If k <> i Then
                If oKn(k) Then
                    rest(nr) = Fix(oSl(k)): nr = nr + 1
                Else
                    unk = unk + 1
                End If
            End If
        ElseIf oKn(k) Then
            spent = spent + Fix(oSl(k))
        End If
    Next k
    SortAsc rest, nr
    need = gAfter - unk
    If need < 0 Then need = 0
    If need > nr Then need = nr
    If oKn(i) Then own = Fix(oSl(i))
    total = gUsed + spent + own
    For k = 0 To need - 1: total = total + rest(k): Next k
    Legal = (total <= gCap)
    lgD(key) = Legal
End Function

Private Function TheirLegal(om As Long, tm As Long, j As Long) As Boolean
    If Not gOppCapOn Then TheirLegal = True: Exit Function
    Dim gAfter As Long, key As String
    gAfter = GamesRem(om) - 1
    key = tm & ":" & j & ":" & gAfter
    If tlD.Exists(key) Then TheirLegal = tlD(key): Exit Function
    Dim rest() As Double, nr As Long, unk As Long, k As Long, spent As Double, own As Double, need As Long, total As Double
    ReDim rest(0 To nT)
    For k = 0 To nT - 1
        If (tm And BITV(k)) <> 0 Then
            If k <> j Then
                If tKn(k) Then
                    rest(nr) = Fix(tSl(k)): nr = nr + 1
                Else
                    unk = unk + 1
                End If
            End If
        ElseIf tKn(k) Then
            spent = spent + Fix(tSl(k))
        End If
    Next k
    SortAsc rest, nr
    need = gAfter - unk
    If need < 0 Then need = 0
    If need > nr Then need = nr
    If tKn(j) Then own = Fix(tSl(j))
    total = gOppUsed + spent + own
    For k = 0 To need - 1: total = total + rest(k): Next k
    TheirLegal = (total <= gCap)
    tlD(key) = TheirLegal
End Function

Private Sub LegalOurs(om As Long, arr() As Long, cnt As Long)
    Dim g As Long, i As Long
    ReDim arr(0 To MAX_PLAYERS): cnt = 0
    g = GamesRem(om)
    If g <= 0 Then Exit Sub
    For i = 0 To nO - 1
        If (om And BITV(i)) <> 0 Then
            If Legal(om, i, g - 1) Then arr(cnt) = i: cnt = cnt + 1
        End If
    Next i
End Sub

Private Sub LegalTheirs(om As Long, tm As Long, arr() As Long, cnt As Long)
    Dim j As Long
    ReDim arr(0 To MAX_PLAYERS): cnt = 0
    If GamesRem(om) <= 0 Then Exit Sub
    For j = 0 To nT - 1
        If (tm And BITV(j)) <> 0 Then
            If TheirLegal(om, tm, j) Then arr(cnt) = j: cnt = cnt + 1
        End If
    Next j
End Sub

' ============================== V2 policy (analytics/uc_v2_policy.py) ==============================

Private Function BestIdx(v() As Double, n As Long) As Long
    Dim b As Long, x As Long
    For x = 1 To n - 1
        If v(x) > v(b) + EPS Then b = x
    Next x
    BestIdx = b
End Function

Private Sub Classify(n As Long, rp() As Double, rtw() As Double, rta() As Double, nowX As Long, stratX As Long, avgX As Long, _
                     pickX As Long, strategic As Boolean, gW As Double, gA As Double, roles() As String, tied() As Boolean, eq() As Boolean)
    Dim x As Long, p As Double, role As String
    nowX = BestIdx(rp, n): stratX = BestIdx(rtw, n): avgX = BestIdx(rta, n)
    gW = rtw(stratX) - rtw(nowX): gA = rta(stratX) - rta(nowX)
    strategic = (stratX <> nowX) And gW >= STRATEGIC_GAIN And gA >= STRATEGIC_GAIN
    If strategic Then pickX = stratX Else pickX = nowX
    ReDim roles(0 To n - 1): ReDim tied(0 To n - 1): ReDim eq(0 To n - 1)
    For x = 0 To n - 1
        tied(x) = (x <> nowX) And (rp(nowX) - rp(x) < PRACTICAL_TIE)
        eq(x) = (x <> pickX) And (Abs(rtw(x) - rtw(pickX)) < PLAN_TIE) And (Abs(rta(x) - rta(pickX)) < PLAN_TIE)
        p = rp(x)
        If x = pickX Then
            If strategic Then
                If p < 0.4 Then role = "Strategic choice (deliberate concession)" Else role = "Strategic choice"
            ElseIf p >= 0.47 Then
                role = "Recommended competitive matchup"
            ElseIf p >= 0.4 Then
                role = "Recommended (underdog)"
            Else
                role = "Best available (every option is a long shot)"
            End If
        ElseIf x = nowX Then
            role = "Strongest matchup now"
        ElseIf x = stratX Then
            role = "Strategic alternative"
        ElseIf x = avgX Then
            role = "Best if they choose evenly"
        ElseIf tied(x) Then
            role = "Practically tied with the strongest"
        ElseIf eq(x) Then
            role = "Practically equal plan"
        Else
            role = ""
        End If
        roles(x) = role
    Next x
End Sub

Private Sub GrowS()
    If sN > UBound(sW) Then
        Dim m As Long: m = 2 * (UBound(sW) + 1) - 1
        ReDim Preserve sW(0 To m): ReDim Preserve sA(0 To m): ReDim Preserve sHasLead(0 To m)
        ReDim Preserve sLeadI(0 To m): ReDim Preserve sLeadR(0 To m): ReDim Preserve sWorst(0 To m)
    End If
End Sub

Private Sub GrowR()
    If rN > UBound(rW) Then
        Dim m As Long: m = 2 * (UBound(rW) + 1) - 1
        ReDim Preserve rW(0 To m): ReDim Preserve rA(0 To m): ReDim Preserve rPick(0 To m): ReDim Preserve rRole(0 To m)
    End If
End Sub

' Lead rows of a state (we put up): worst-case and even-choice totals and their most damaging reply, per legal player.
Private Sub LeadRows(om As Long, tm As Long, oa() As Long, cntO As Long, rwv() As Double, rav() As Double, rrv() As Long)
    Dim ta() As Long, cntT As Long, x As Long, y As Long, i As Long, j As Long, c As Long, p As Double, wv As Double, av As Double, rep As Long
    LegalOurs om, oa, cntO
    LegalTheirs om, tm, ta, cntT
    If cntO = 0 Or cntT = 0 Then cntO = 0: Exit Sub
    ReDim rwv(0 To cntO - 1): ReDim rav(0 To cntO - 1): ReDim rrv(0 To cntO - 1)
    For x = 0 To cntO - 1
        i = oa(x): wv = INF: av = 0: rep = -1
        For y = 0 To cntT - 1
            j = ta(y)
            c = St(om And Not BITV(i), tm And Not BITV(j), False)
            p = PP(i, j)
            If p + sW(c) < wv Then wv = p + sW(c): rep = j
            av = av + (p + sA(c)) / cntT
        Next y
        rwv(x) = wv: rav(x) = av: rrv(x) = rep
    Next x
End Sub

Private Function LeadBest(cntO As Long, rwv() As Double, rav() As Double) As Long
    Dim top As Double, x As Long, b As Long
    top = -INF
    For x = 0 To cntO - 1
        If rwv(x) > top Then top = rwv(x)
    Next x
    b = -1
    For x = 0 To cntO - 1
        If rwv(x) >= top - PLAN_TIE Then
            If b = -1 Then
                b = x
            ElseIf rav(x) > rav(b) + EPS Then
                b = x
            End If
        End If
    Next x
    LeadBest = b
End Function

Private Function St(om As Long, tm As Long, lead As Boolean) As Long
    Dim key As String
    key = om & ":" & tm & ":" & IIf(lead, "1", "0")
    If stD.Exists(key) Then St = stD(key): Exit Function
    Dim w As Double, a As Double, hasLead As Boolean, li As Long, lr As Long, wj As Long
    li = -1: lr = -1: wj = -1
    If lead Then
        Dim oa() As Long, cntO As Long, rwv() As Double, rav() As Double, rrv() As Long, b As Long
        LeadRows om, tm, oa, cntO, rwv, rav, rrv
        If cntO = 0 Then
            w = 0: a = 0
        Else
            b = LeadBest(cntO, rwv, rav)
            w = rwv(b): a = rav(b): hasLead = True: li = oa(b): lr = rrv(b)
        End If
    Else
        Dim ob() As Long, nob As Long, ta() As Long, cntT As Long, y As Long, j As Long, r As Long
        LegalOurs om, ob, nob
        LegalTheirs om, tm, ta, cntT
        If nob = 0 Or cntT = 0 Then
            w = 0: a = 0
        Else
            w = INF: a = 0
            For y = 0 To cntT - 1
                j = ta(y)
                r = Resp(om, tm, j)
                If rW(r) < w Then w = rW(r): wj = j
                a = a + rA(r) / cntT
            Next y
        End If
    End If
    GrowS
    sW(sN) = w: sA(sN) = a: sHasLead(sN) = hasLead: sLeadI(sN) = li: sLeadR(sN) = lr: sWorst(sN) = wj
    stD(key) = sN
    St = sN
    sN = sN + 1
End Function

' Response rows to their player j (we answer): p now, rest of night under both opponent models.
Private Sub RespRows(om As Long, tm As Long, j As Long, oa() As Long, cntO As Long, rp() As Double, rtw() As Double, rta() As Double)
    Dim x As Long, i As Long, c As Long
    LegalOurs om, oa, cntO
    If cntO = 0 Then Exit Sub
    ReDim rp(0 To cntO - 1): ReDim rtw(0 To cntO - 1): ReDim rta(0 To cntO - 1)
    For x = 0 To cntO - 1
        i = oa(x)
        c = St(om And Not BITV(i), tm And Not BITV(j), True)
        rp(x) = PP(i, j): rtw(x) = PP(i, j) + sW(c): rta(x) = PP(i, j) + sA(c)
    Next x
End Sub

Private Function Resp(om As Long, tm As Long, j As Long) As Long
    Dim key As String
    key = om & ":" & tm & ":" & j
    If rsD.Exists(key) Then Resp = rsD(key): Exit Function
    Dim oa() As Long, cntO As Long, rp() As Double, rtw() As Double, rta() As Double
    RespRows om, tm, j, oa, cntO, rp, rtw, rta
    If cntO = 0 Then Err.Raise vbObjectError + 1, , "No legal response"
    Dim nowX As Long, stratX As Long, avgX As Long, pickX As Long, strategic As Boolean, gW As Double, gA As Double
    Dim roles() As String, tied() As Boolean, eq() As Boolean
    Classify cntO, rp, rtw, rta, nowX, stratX, avgX, pickX, strategic, gW, gA, roles, tied, eq
    GrowR
    rW(rN) = rtw(pickX): rA(rN) = rta(pickX): rPick(rN) = oa(pickX): rRole(rN) = roles(pickX)
    rsD(key) = rN
    Resp = rN
    rN = rN + 1
End Function

' The night as the policy plays it, their captain making the most damaging choice each time.
Private Sub PlayLine(ByVal om As Long, ByVal tm As Long, ByVal lead As Boolean, ld() As Boolean, li() As Long, lj() As Long, n As Long)
    Dim oa() As Long, cntO As Long, ta() As Long, cntT As Long, s As Long, i As Long, j As Long
    ReDim ld(0 To 5): ReDim li(0 To 5): ReDim lj(0 To 5): n = 0
    Do
        LegalOurs om, oa, cntO
        LegalTheirs om, tm, ta, cntT
        If cntO = 0 Or cntT = 0 Then Exit Do
        s = St(om, tm, lead)
        If lead Then
            i = sLeadI(s): j = sLeadR(s)
        Else
            j = sWorst(s): i = rPick(Resp(om, tm, j))
        End If
        If n > UBound(ld) Then ReDim Preserve ld(0 To 2 * n): ReDim Preserve li(0 To 2 * n): ReDim Preserve lj(0 To 2 * n)
        ld(n) = lead: li(n) = i: lj(n) = j: n = n + 1
        om = om And Not BITV(i): tm = tm And Not BITV(j): lead = Not lead
    Loop
End Sub

' ============================== wording (analytics/uc_v2_explain.py) ==============================

Private Function JsRound(x As Double) As Double
    JsRound = Int(x + 0.5)
End Function

Private Function JsFixed(x As Double, d As Long) As String
    Dim n As Double, s As String
    n = Int(Abs(x) * 10 ^ d + 0.5)
    s = Format(n, "0")
    Do While Len(s) <= d: s = "0" & s: Loop
    If d > 0 Then s = Left(s, Len(s) - d) & "." & Right(s, d)
    If x < 0 Then s = "-" & s
    JsFixed = s
End Function

Private Function Pct(p As Double) As String
    Pct = Format(JsRound(100 * p), "0") & "%"
End Function

Private Function Wins(x As Double) As String
    Wins = IIf(x >= 0, "+", "") & JsFixed(x, 3)
End Function

Private Function OptionsText(j As Long, oa() As Long, cntO As Long, rp() As Double, tied() As Boolean, eq() As Boolean, _
                             nowX As Long, stratX As Long, pickX As Long, gW As Double, gA As Double) As String
    Dim x As Long, tiedS As String, eqS As String, tie As String, later As String
    For x = 0 To cntO - 1
        If tied(x) Then tiedS = tiedS & IIf(tiedS = "", "", ", ") & oNm(oa(x))
        If eq(x) Then eqS = eqS & IIf(eqS = "", "", ", ") & oNm(oa(x))
    Next x
    If tiedS <> "" Then tie = " Practically tied now with " & tiedS & " (within 1 point)."
    If eqS <> "" Then tie = tie & " Practically equal plan with " & eqS & " instead (within 0.02 expected wins either way); your read decides."
    Dim ld() As Boolean, li() As Long, lj() As Long, n As Long, g As Long
    PlayLine fullO And Not BITV(oa(stratX)), fullT And Not BITV(j), True, ld, li, lj, n
    For g = 0 To IIf(n < 2, n, 2) - 1
        later = later & IIf(g = 0, "", ", ") & oNm(li(g)) & " vs " & tNm(lj(g))
    Next g
    Dim nm As String, ns As String
    nm = oNm(oa(nowX)): ns = oNm(oa(stratX))
    If pickX = nowX And stratX = nowX Then
        OptionsText = "Strongest matchup available (" & Pct(rp(nowX)) & ") and also the best plan for the rest of the night." & tie
    ElseIf pickX = nowX Then
        OptionsText = "Strongest matchup available (" & Pct(rp(nowX)) & ")." & tie & " Strategic alternative: " & ns & " (" & Pct(rp(stratX)) & ") keeps " & nm _
            & " for later (" & later & "): " & Wins(gW) & " expected wins only if they always make their most damaging choice, " & Wins(gA) _
            & " if they choose evenly. Not enough to give up the stronger matchup (needs 0.10 under both)."
    Else
        OptionsText = "Strategic choice: " & ns & " (" & Pct(rp(stratX)) & ") instead of the strongest matchup " & nm & " (" & Pct(rp(nowX)) & "). It keeps " & nm _
            & " for later (" & later & "): " & Wins(gW) & " expected wins if they make their most damaging choices, " & Wins(gA) & " if they choose evenly." & tie _
            & " The captain may prefer the stronger matchup now."
    End If
End Function

' ============================== outputs ==============================

Private Sub BuildOutputs(putUp As String, oppPids As Variant, oppLabels As Variant, tossKnown As Boolean, nextUs As Boolean)
    Dim L As Long, T As Long, js As String, tb As String, x As Long
    L = St(fullO, fullT, True): T = St(fullO, fullT, False)
    Dim capIncomplete As Boolean, oppCapIncomplete As Boolean
    For x = 0 To nO - 1
        If gCapOn And Not oKn(x) Then capIncomplete = True
    Next x
    For x = 0 To nT - 1
        If gOppCapOn And Not tKn(x) Then oppCapIncomplete = True
    Next x
    js = "{""status"":""ok"",""games"":" & gGames & ",""cap"":" & IIf(gCapOn, CStr(gCap), "null") & ",""used"":" & JNum(gUsed) _
        & ",""oppUsed"":" & JNum(gOppUsed) & ",""relaxed"":" & JBool(gCapOn And Not gOppCapOn) & ",""capIncomplete"":" & JBool(capIncomplete) _
        & ",""oppCapIncomplete"":" & JBool(oppCapIncomplete) & ",""tossKnown"":" & JBool(tossKnown) & ",""nextUs"":" & JBool(nextUs)
    js = js & ",""ours"":[": For x = 0 To nO - 1: js = js & IIf(x = 0, "", ",") & JStr(oId(x)): Next x
    js = js & "],""theirs"":[": For x = 0 To nT - 1: js = js & IIf(x = 0, "", ",") & JStr(tId(x)): Next x
    js = js & "]"
    ' ---- lead ----
    Dim leadText As String, leadName As String, whyLead As String, eqNames As String, eqIds As String
    If sHasLead(L) Then
        Dim oa() As Long, cntO As Long, rwv() As Double, rav() As Double, rrv() As Long, b As Long
        LeadRows fullO, fullT, oa, cntO, rwv, rav, rrv
        b = LeadBest(cntO, rwv, rav)
        For x = 0 To cntO - 1
            If x <> b And Abs(rwv(x) - rwv(b)) < PLAN_TIE And Abs(rav(x) - rav(b)) < PLAN_TIE Then
                eqNames = eqNames & IIf(eqNames = "", "", ", ") & oNm(oa(x)): eqIds = eqIds & IIf(eqIds = "", "", ",") & JStr(oId(oa(x)))
            End If
        Next x
        leadName = oNm(sLeadI(L))
        whyLead = "Lead " & leadName & ": their most damaging reply is " & tNm(sLeadR(L)) & " (" & Pct(PP(sLeadI(L), sLeadR(L))) _
            & " for us); night " & JsFixed(sW(L), 2) & " expected wins if they always make the most damaging choice, " & JsFixed(sA(L), 2) & " if they choose evenly"
        js = js & ",""lead"":{""our"":" & JStr(oId(sLeadI(L))) & ",""reply"":" & JStr(tId(sLeadR(L))) & ",""w"":" & JNum(sW(L)) & ",""a"":" & JNum(sA(L)) _
            & ",""p"":" & JNum(PP(sLeadI(L), sLeadR(L))) & ",""equal"":[" & eqIds & "],""why"":" & JStr(PT(sLeadI(L), sLeadR(L))) & ",""whyLead"":" & JStr(whyLead) & "}"
        leadText = "Lead " & leadName & " — " & PT(sLeadI(L), sLeadR(L)) & ". " & whyLead & "." & IIf(eqNames = "", "", " Equally good leads: " & eqNames & ".")
    Else
        js = js & ",""lead"":null"
    End If
    ' ---- answers to each put-up ----
    Dim ta() As Long, cntT As Long, y As Long, j As Long
    Dim respOur() As String, respRole() As String, respP() As Double, respWhy() As String, respCost() As String, respJ() As Long
    js = js & ",""responses"":["
    If sHasLead(L) Then LegalTheirs fullO, fullT, ta, cntT Else cntT = 0
    If cntT > 0 Then
        ReDim respOur(0 To cntT - 1): ReDim respRole(0 To cntT - 1): ReDim respP(0 To cntT - 1): ReDim respWhy(0 To cntT - 1)
        ReDim respCost(0 To cntT - 1): ReDim respJ(0 To cntT - 1)
    End If
    For y = 0 To cntT - 1
        j = ta(y)
        Dim ob() As Long, nob As Long, rp() As Double, rtw() As Double, rta() As Double
        Dim nowX As Long, stratX As Long, avgX As Long, pickX As Long, strategic As Boolean, gW As Double, gA As Double
        Dim roles() As String, tied() As Boolean, eq() As Boolean, rows As String
        RespRows fullO, fullT, j, ob, nob, rp, rtw, rta
        Classify nob, rp, rtw, rta, nowX, stratX, avgX, pickX, strategic, gW, gA, roles, tied, eq
        respJ(y) = j: respOur(y) = oNm(ob(pickX)): respRole(y) = roles(pickX): respP(y) = rp(pickX): respWhy(y) = PT(ob(pickX), j)
        respCost(y) = OptionsText(j, ob, nob, rp, tied, eq, nowX, stratX, pickX, gW, gA)
        rows = ""
        For x = 0 To nob - 1
            rows = rows & IIf(x = 0, "", ",") & "{""our"":" & JStr(oId(ob(x))) & ",""role"":" & JStr(roles(x)) & ",""p"":" & JNum(rp(x)) _
                & ",""tw"":" & JNum(rtw(x)) & ",""ta"":" & JNum(rta(x)) & "}"
        Next x
        js = js & IIf(y = 0, "", ",") & "{""their"":" & JStr(tId(j)) & ",""pick"":" & JStr(oId(ob(pickX))) & ",""now"":" & JStr(oId(ob(nowX))) _
            & ",""strat"":" & JStr(oId(ob(stratX))) & ",""avg"":" & JStr(oId(ob(avgX))) & ",""strategic"":" & JBool(strategic) _
            & ",""gW"":" & JNum(gW) & ",""gA"":" & JNum(gA) & ",""role"":" & JStr(roles(pickX)) & ",""p"":" & JNum(rp(pickX)) _
            & ",""why"":" & JStr(respWhy(y)) & ",""cost"":" & JStr(respCost(y)) & ",""rows"":[" & rows & "]}"
    Next y
    js = js & "]"
    ' ---- the two plans, totals and planned long shots ----
    Dim ldU() As Boolean, liU() As Long, ljU() As Long, nU As Long, ldT() As Boolean, liT() As Long, ljT() As Long, nTh As Long
    PlayLine fullO, fullT, True, ldU, liU, ljU, nU
    PlayLine fullO, fullT, False, ldT, liT, ljT, nTh
    js = js & ",""planUs"":" & PlanJson(ldU, liU, ljU, nU) & ",""planThem"":" & PlanJson(ldT, liT, ljT, nTh)
    js = js & ",""totals"":{""us"":{""w"":" & JNum(sW(L)) & ",""a"":" & JNum(sA(L)) & "},""them"":{""w"":" & JNum(sW(T)) & ",""a"":" & JNum(sA(T)) & "}}"
    Dim sac As String, sacN As Long, om As Long, tm As Long, g As Long, why As String, sacText As String
    om = fullO: tm = fullT
    For g = 0 To nTh - 1
        If PP(liT(g), ljT(g)) < 0.4 And sacN < 2 Then
            If Not ldT(g) Then why = rRole(Resp(om, tm, ljT(g))) Else why = "planned long shot"
            why = why & " — " & PT(liT(g), ljT(g))
            sac = sac & IIf(sacN = 0, "", ",") & "{""our"":" & JStr(oId(liT(g))) & ",""their"":" & JStr(tId(ljT(g))) & ",""why"":" & JStr(why) & "}"
            sacText = sacText & IIf(sacN = 0, "", " · ") & oNm(liT(g)) & " vs " & tNm(ljT(g)) & ": " & why
            sacN = sacN + 1
        End If
        om = om And Not BITV(liT(g)): tm = tm And Not BITV(ljT(g))
    Next g
    js = js & ",""sacrifices"":[" & sac & "]"
    ' ---- the answer for the live put-up ----
    Dim ans As String, sel As Long, pid As String
    sel = -1
    If gGames <= 0 Then
        ans = "No games left to plan tonight."
    ElseIf Not sHasLead(L) Then
        ans = "No legal send fits the entered skill cap — check the cap and remaining skill levels."
    ElseIf Not tossKnown Then
        ans = "Choose who puts up first on Five-Game Plan (cell B5) to see whose turn it is."
    ElseIf nextUs Then
        ans = "Our put-up (game " & (6 - gGames) & "): " & leadText
    ElseIf putUp = "" Then
        ans = "Their put-up (game " & (6 - gGames) & "): choose the player they put up in Command Center C6."
    Else
        pid = LabelToPid(putUp, oppPids, oppLabels)
        For y = 0 To cntT - 1
            If tId(respJ(y)) = pid Then sel = y
        Next y
        If sel = -1 Then
            ans = putUp & " has already played, is not on their roster, or cannot be put up under the cap. Check Lineup Lab."
        Else
            ans = "They put up " & tNm(respJ(sel)) & " (game " & (6 - gGames) & "): send " & respOur(sel) & " — " & respRole(sel) & " · " & respWhy(sel) & ". " & respCost(sel)
        End If
    End If
    If capIncomplete Then ans = ans & " Cap check incomplete: a remaining player has no captured skill level."
    If gCapOn And Not gOppCapOn Then ans = ans & " Their known skill levels already exceed the cap, so their put-ups are not limited by it."
    If sel = -1 Then js = js & ",""selected"":null" Else js = js & ",""selected"":" & JStr(tId(respJ(sel)))
    js = js & ",""answer"":" & JStr(ans) & "}"
    gTrace = js
    gAnswer = ans
    ' ---- the V2 Coach table ----
    Dim out() As Variant, r As Long
    ReDim out(1 To 80, 1 To 6)
    For r = 1 To 80: For x = 1 To 6: out(r, x) = "": Next x: Next r
    r = 1
    out(r, 1) = "V2 ANSWER NOW": out(r, 2) = ans: r = r + 2
    out(r, 1) = "Night state": out(r, 2) = gGames & " game(s) left · cap " & IIf(gCapOn, CStr(gCap), "off") & " · our skill already used " & gUsed _
        & " · their skill already used " & gOppUsed & IIf(tossKnown, " · next put-up: " & IIf(nextUs, "us", "them"), " · first put-up not chosen"): r = r + 2
    out(r, 1) = "IF THEY PUT UP": out(r, 2) = "Our answer": out(r, 3) = "Role": out(r, 4) = "V2 win chance": out(r, 5) = "Matchup": out(r, 6) = "Strategy and alternatives": r = r + 1
    For y = 0 To cntT - 1
        If r > 60 Then Exit For
        out(r, 1) = tNm(respJ(y)): out(r, 2) = respOur(y): out(r, 3) = respRole(y): out(r, 4) = Pct(respP(y)): out(r, 5) = respWhy(y): out(r, 6) = respCost(y)
        r = r + 1
    Next y
    r = r + 1
    out(r, 1) = "IF WE PUT UP": out(r, 2) = IIf(sHasLead(L), leadName, "No legal lead"): out(r, 6) = IIf(sHasLead(L), whyLead & "." & IIf(eqNames = "", "", " Equally good: " & eqNames & "."), "")
    If sHasLead(L) Then out(r, 4) = Pct(PP(sLeadI(L), sLeadR(L))): out(r, 5) = PT(sLeadI(L), sLeadR(L))
    r = r + 2
    r = PlanRows(out, r, "PLAN IF WE PUT UP FIRST", ldU, liU, ljU, nU, sW(L), sA(L))
    r = PlanRows(out, r, "PLAN IF THEY PUT UP FIRST", ldT, liT, ljT, nTh, sW(T), sA(T))
    If sacText <> "" Then out(r, 1) = "PLANNED LONG SHOTS": out(r, 6) = sacText: r = r + 2
    If capIncomplete Then out(r, 1) = "WARNING": out(r, 6) = "Cap check incomplete: a remaining player has no captured skill level; their own cost cannot be verified.": r = r + 1
    If gCapOn And Not gOppCapOn Then out(r, 1) = "NOTE": out(r, 6) = "Their known skill levels already exceed the cap, so their put-ups are not limited by it.": r = r + 1
    gTable = out
End Sub

Private Function PlanRows(out() As Variant, ByVal r As Long, title As String, ld() As Boolean, li() As Long, lj() As Long, n As Long, w As Double, a As Double) As Long
    Dim g As Long
    out(r, 1) = title: out(r, 2) = "Our player": out(r, 3) = "Their player": out(r, 4) = "V2 win chance": out(r, 5) = "Matchup"
    out(r, 6) = "Expected wins: " & JsFixed(w, 2) & " if they always make the most damaging choice, " & JsFixed(a, 2) & " if they choose evenly"
    r = r + 1
    For g = 0 To n - 1
        out(r, 1) = "Game " & (6 - gGames + g) & " · " & IIf(ld(g), "we put up", "they put up")
        out(r, 2) = oNm(li(g)): out(r, 3) = tNm(lj(g)): out(r, 4) = Pct(PP(li(g), lj(g))): out(r, 5) = PT(li(g), lj(g))
        r = r + 1
    Next g
    PlanRows = r + 1
End Function

Private Function PlanJson(ld() As Boolean, li() As Long, lj() As Long, n As Long) As String
    Dim g As Long, s As String
    For g = 0 To n - 1
        s = s & IIf(g = 0, "", ",") & "{""leader"":" & JStr(IIf(ld(g), "us", "them")) & ",""our"":" & JStr(oId(li(g))) & ",""their"":" & JStr(tId(lj(g))) _
            & ",""p"":" & JNum(PP(li(g), lj(g))) & "}"
    Next g
    PlanJson = "[" & s & "]"
End Function

Private Function Table(msg As String, a As Boolean, b As Boolean, c As Boolean, d As String) As Variant
    Dim out() As Variant, r As Long, x As Long
    ReDim out(1 To 80, 1 To 6)
    For r = 1 To 80: For x = 1 To 6: out(r, x) = "": Next x: Next r
    out(1, 1) = "V2 ANSWER NOW": out(1, 2) = msg
    Table = out
End Function

' ============================== helpers ==============================

Private Function LabelToPid(label As String, oppPids As Variant, oppLabels As Variant) As String
    Dim p As Variant, l As Variant, r As Long
    p = Grid(oppPids): l = Grid(oppLabels)
    For r = 1 To UBound(l, 1)
        If CStr(l(r, 1)) = label Then LabelToPid = CStr(p(r, 1)): Exit Function
    Next r
    LabelToPid = ""
End Function

Private Sub Span(scope As String, first As Long, cnt As Long)
    Dim s() As String
    s = Split(rosterIdx(scope), ",")
    first = CLng(s(0)): cnt = CLng(s(1))
End Sub

Private Function Grid(v As Variant) As Variant
    Dim g As Variant
    If TypeName(v) = "Range" Then g = v.Value Else g = v
    If Not IsArray(g) Then
        Dim one(1 To 1, 1 To 1) As Variant
        one(1, 1) = g: Grid = one
    Else
        Grid = g
    End If
End Function

Private Function V1(v As Variant) As String
    Dim g As Variant
    If TypeName(v) = "Range" Then g = v.Cells(1, 1).Value Else g = v
    If IsError(g) Then V1 = "" Else V1 = CStr(g)
End Function

Private Function Flat(v As Variant) As String
    Dim g As Variant, r As Long, s As String
    g = Grid(v)
    For r = 1 To UBound(g, 1)
        If IsError(g(r, 1)) Then s = s & "#" & Chr(2) Else s = s & CStr(g(r, 1)) & Chr(2)
    Next r
    Flat = s
End Function

Private Function JStr(s As String) As String
    Dim i As Long, ch As String, o As String, c As Long
    For i = 1 To Len(s)
        ch = Mid$(s, i, 1): c = AscW(ch)
        If ch = """" Then
            o = o & "\"""
        ElseIf ch = "\" Then
            o = o & "\\"
        ElseIf c >= 0 And c < 32 Then
            o = o & "\u" & Right$("000" & Hex$(c), 4)
        Else
            o = o & ch
        End If
    Next i
    JStr = """" & o & """"
End Function

Private Function JNum(x As Double) As String
    Dim s As String
    s = Trim$(Str$(x))
    If Left$(s, 1) = "." Then s = "0" & s
    If Left$(s, 2) = "-." Then s = "-0" & Mid$(s, 2)
    JNum = s
End Function

Private Function IsTrue(v As Variant) As Boolean
    If VarType(v) = vbBoolean Then IsTrue = v
End Function

Private Function JBool(b As Boolean) As String
    JBool = IIf(b, "true", "false")
End Function
