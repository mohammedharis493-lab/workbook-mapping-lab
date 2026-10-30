"""Non-blocking, evidence-backed accounting classification advisories.

Advisories are NOT permission to change figures. They never alter approved
mapping rules, never block the import-copy workflow, and never replace
professional judgement. If evidence is missing the check is explicitly
unverified rather than silently assuming a correct classification.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path

from .simulator import WorkbookSnapshot


def value(raw: str) -> Decimal | None:
    try:
        result=Decimal(str(raw).replace(",","").strip())
        return result if result.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def money(amount: Decimal) -> str:
    return format(amount, "f")


def advisory(code: str, title: str, explanation: str, action: str,
             *, severity: str = "Review", evidence: list[dict] | None = None,
             difference: str = "", year: str = "Previous year") -> dict:
    if severity not in ("Review", "Info"):
        raise ValueError("Unsupported advisory severity")
    return {
        "code": code, "severity": severity, "period": year,
        "title": title, "explanation": explanation,
        "suggested_action": action, "difference": difference,
        "evidence": evidence or [],
        "acknowledged": False,
        "blocking": False,
    }


def check_creditor_ageing(prior_fs: str, prior_itr: str,
                          *, current_fs: str | None = None,
                          fs_sheet: str = "New Disclosure",
                          itr_sheet: str = "Creditors") -> list[dict]:
    """Compare PY 4-bucket FS ageing to corresponding PY ITR >1-year detail.

    This is a *classification* check: overall creditors can agree while the
    age split is wrong. Does not assume there is an importable <1-year child
    on the vendor form. The exact grouped heading is verified before relying
    on the historical amount.

    The default cell layout applies only when identified as the corresponding
    source schedules. Other entities can supply a different detection profile.
    """
    notes: list[dict] = []
    if not prior_fs or not prior_itr:
        return [advisory(
            "HISTORICAL_AGEING_NOT_CHECKED",
            "Previous-year classification not verified",
            "Both previous-year FS and completed previous-year return are required.",
            "Supply both exports to enable classification checks.",
            severity="Info",
        )]
    with WorkbookSnapshot(prior_fs) as fs, WorkbookSnapshot(prior_itr) as itr:
        if fs_sheet not in fs.sheets or itr_sheet not in itr.sheets:
            return [advisory(
                "HISTORICAL_AGEING_NOT_FOUND",
                "Previous-year creditor ageing cannot be checked",
                "The expected ageing and creditor-detail worksheets were not both found.",
                "Inspect the workbook layout and select an evidence profile before relying on previous-year mapping.",
                severity="Info",
            )]
        caption=fs.cell(fs_sheet,"A5")["value"].casefold()
        header=fs.cell(fs_sheet,"C4")["value"].casefold()
        older_heading=itr.cell(itr_sheet,"A4")["value"].casefold()
        if "msme" not in caption or "less than 1" not in header or "more than 1 year" not in older_heading:
            return [advisory(
                "HISTORICAL_AGEING_LAYOUT_UNRECOGNISED",
                "Previous-year ageing classification requires manual review",
                "The expected source labels or Winman over-one-year classification heading differ.",
                "Verify the actual source rows and select an applicable evidence profile; no amounts have been compared.",
                severity="Info",
            )]
        bucket_cells=("C5","D5","E5","F5")
        components=[value(fs.cell(fs_sheet,cell)["value"]) for cell in bucket_cells]
        fs_total=value(fs.cell(fs_sheet,"G5")["value"])
        reported_older=value(itr.cell(itr_sheet,"B5")["value"])
        prior_total=value(itr.cell(itr_sheet,"B6")["value"])
        if any(a is None for a in components) or fs_total is None or reported_older is None:
            return [advisory(
                "HISTORICAL_AGEING_INCOMPLETE",
                "Previous-year age comparison lacks numeric evidence",
                "A necessary amount in the ageing note or the return is blank or nonnumeric.",
                "Verify the affected cells in the original workbooks.",
                severity="Info",
            )]
        under_one,one_two,two_three,over_three=components
        over_one=one_two+two_three+over_three
        references=[
            {"source":"Previous-year FS ageing", "sheet":fs_sheet,
             "cell":"C5", "description":"Less than one year", "amount":money(under_one)},
            {"source":"Previous-year FS ageing","sheet":fs_sheet,
             "cell":"D5:F5", "description":"Sum of over-one-year ageing buckets",
             "amount":money(over_one)},
            {"source":"Previous-year FS ageing", "sheet":fs_sheet,
             "cell":"G5", "description":"Overall creditor balance", "amount":money(fs_total)},
            {"source":"Previous-year completed return", "sheet":itr_sheet,
             "cell":"B5", "description":"Reported under older-creditor heading",
             "amount":money(reported_older)},
        ]
        if sum(components,Decimal("0"))!=fs_total:
            notes.append(advisory(
                "FS_AGEING_NOTE_TOTAL_MISMATCH",
                "Previous-year FS ageing does not total",
                "The four ageing buckets differ from the FS note's total.",
                "Review the note and outstanding records. Do not assume either amount is correct.",
                evidence=references,
                difference=money(sum(components,Decimal("0"))-fs_total),
            ))
        if prior_total is not None and prior_total!=fs_total:
            notes.append(advisory(
                "PRIOR_CREDITOR_PARENT_TOTAL_DIFFERENCE",
                "Previous return creditor detail total differs from FS total",
                "The historical detail total and corresponding FS note total are unequal.",
                "Reconcile the underlying ledger and disclosure.",
                evidence=references + [{"source":"Previous-year completed return",
                                          "sheet":itr_sheet,"cell":"B6",
                                          "amount":money(prior_total),"description":"Reported detail total"}],
                difference=money(prior_total-fs_total),
            ))
        if reported_older != over_one:
            notes.append(advisory(
                "PRIOR_CREDITOR_AGE_CLASSIFICATION",
                "Previous-year trade creditors may have been aged incorrectly",
                ("The prior return reports "+money(reported_older)+
                 " under an over-one-year heading, but the PY FS ageing note "
                 "supports "+money(over_one)+" over one year and "+
                 money(under_one)+" under one year. The total may still agree."),
                "Review the previous-year classification and invoice ageing. Use the current-year reviewed age split rather than blindly repeating the earlier mapping.",
                evidence=references,
                difference=money(reported_older-over_one),
            ))
        # The old note's unit heading can be internally inconsistent with
        # figures reported as rupees. Warn, but do not silently rescale them.
        units=fs.cell(fs_sheet,"G2")["value"]
        if "'000" in units or "thousand" in units.casefold():
            notes.append(advisory(
                "HISTORICAL_NOTE_UNIT_HEADING",
                "Check the unit caption on the previous-year ageing note",
                "The header indicates thousands. Its underlying values should be verified against the BS/ledger before any unit scaling.",
                "Confirm the correct units; do not multiply the values automatically.",
                severity="Info",
                evidence=[{"source":"Previous-year FS ageing","sheet":fs_sheet,
                           "cell":"G2","description":"Ageing units heading","text":units}],
            ))
        if current_fs:
            with WorkbookSnapshot(current_fs) as cy:
                if fs_sheet in cy.sheets:
                    current=[value(cy.cell(fs_sheet,cell)["value"]) for cell in bucket_cells]
                    current_total=value(cy.cell(fs_sheet,"G5")["value"])
                    if all(a is not None for a in current) and current_total is not None:
                        actual=sum(current,Decimal("0"))
                        if actual!=current_total:
                            notes.append(advisory(
                                "CURRENT_FS_AGEING_TOTAL_MISMATCH",
                                "Current-year FS ageing buckets differ from note total",
                                "The current ageing breakdown does not match its stated total.",
                                "Reconcile the current ageing schedule and ledger before finalising the mapping.",
                                evidence=[{"source":"Current-year FS ageing","sheet":fs_sheet,
                                           "cell":"C5:G5","description":"Four ageing buckets and total"}],
                                difference=money(actual-current_total), year="Current year",
                            ))
                        # A roll-forward cannot be established without settled
                        # balances and invoice dates. Show as an advisory only.
                        expected=(under_one,one_two,two_three+over_three)
                        actual_aged=(current[1],current[2],current[3])
                        if actual_aged!=expected:
                            notes.append(advisory(
                                "AGEING_ROLLFORWARD_NEEDS_SUPPORT",
                                "Current-year creditor ageing needs roll-forward evidence",
                                "Older age buckets differ from the simple unpaid-balance roll of previous-year ageing.",
                                "Check settlements, credit notes and invoice dates before concluding that the ageing is wrong.",
                                evidence=[
                                    {"source":"Previous-year FS ageing","sheet":fs_sheet,
                                     "cell":"C5:F5","description":"Previous-year buckets"},
                                    {"source":"Current-year FS ageing","sheet":fs_sheet,
                                     "cell":"D5:F5","description":"Current-year older buckets"}],
                                year="Current year",
                            ))
    return notes


def check_advisories(prior_fs: str | None, prior_itr: str | None,
                     current_fs: str | None = None) -> list[dict]:
    """Return independent, non-blocking notes; no mapping state is mutated."""
    if not prior_fs or not prior_itr:
        return check_creditor_ageing(prior_fs or "",prior_itr or "")
    return check_creditor_ageing(prior_fs,prior_itr,current_fs=current_fs)
