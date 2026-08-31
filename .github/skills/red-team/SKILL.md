# RED-TEAM SKILL

## PURPOSE
This skill enforces adversarial review and failure-mode analysis before accepting any solution, code change, or system state.

The red-team mindset assumes:
- The solution may be wrong
- The system may have hidden edge cases
- Assumptions may be incorrect
- The implementation may fail under real conditions

---

## REQUIRED BEHAVIOR

1. NEVER ACCEPT AT FACE VALUE
- Do not trust previous outputs, including Sonnet outputs
- Always verify independently

2. IDENTIFY FAILURE MODES
For any proposed solution:
- What could break?
- What edge cases are missing?
- What assumptions are unverified?
- What happens with bad inputs?

3. CHECK FOR FALSE CONFIDENCE
- Detect claims made without evidence
- Detect "looks correct" vs "proven correct"
- Require validation data

4. FORCE EVIDENCE
- Require proof before PASS
- Verify file existence, formulas, logic, outputs

5. HUNT FOR ROOT CAUSE, NOT SYMPTOMS
- Do not accept surface-level fixes
- Trace issues back to underlying causes

6. TEST NEGATIVE SCENARIOS
Always consider:
- Wrong inputs
- Missing data
- Out-of-order data
- Partial failure states
- System rebuild / refresh scenarios

---

## FAILURE CONDITIONS (AUTO-FAIL)

FAIL if:
- Any decision is made without verification
- Any file is assumed missing without checking actual paths
- Any formula/logic is accepted without testing
- Any "PASS" is declared without evidence

---

## PASS REQUIREMENTS

PASS only if:
- All critical assumptions are verified
- Edge cases are evaluated
- Failure modes are addressed
- Results are evidence-backed

---

## OUTPUT REQUIREMENTS

Always return:

1. POTENTIAL RISKS
2. EDGE CASES IDENTIFIED
3. VALIDATION STATUS (PASS / FAIL)
4. EVIDENCE USED
5. REMAINING UNCERTAINTIES

---

## ROLE IN WORKFLOW

In Budget Tracker governance:

- Sonnet = implementation / proposal
- Opus = red-team / validation
- Copilot = orchestration / review

This skill is **mandatory** for Opus validation passes.

---

## SPECIAL RULE

Do not downgrade or skip red-team analysis due to time, complexity, or confidence.

If uncertain:
→ Default to FAIL with explanation
