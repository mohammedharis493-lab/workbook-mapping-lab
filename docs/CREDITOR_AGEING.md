# Creditor ageing roll-forward and two-band return mapping

## Source and period treatment

The source of truth is the current independently reviewed financial-statement
ageing note. Do not replace its age analysis with guessed opening balances, a
two-bucket recast, or an automatically created template.

A year-end outstanding invoice normally rolls as follows, provided it remains
unpaid and is still outstanding:

- Prior under 1 year -> current 1-2 years.
- Prior 1-2 years -> current 2-3 years.
- Prior 2-3 years -> current over 3 years.
- Prior over 3 years -> stays over 3 years.
- Current-year new unpaid invoices appear under 1 year.

Changes caused by settlement, adjustment, credit notes, or invoice-date
differences must be reconciled with supporting evidence, not balanced away.
The check_rollforward function reports unexpected differences.

## Two-band return classification

When the destination return asks for only two categories, compute these from
the current-year reviewed four-bucket schedule:

    under_one = CY_under_one
    over_one = CY_one_to_two + CY_two_to_three + CY_over_three
    total = under_one + over_one

Do NOT put only CY over-three-years into the over-one-year field. Do NOT put
the entire outstanding balance in the under-one-year field.

For a template with separate short-term and long-term trade-payable fields,
use the approved classification and the fields in the existing vendor-exported
template. The program must never recreate or overwrite the template.

## Example with invented test amounts

Previous-year four-bucket ageing: 15, 25, 35, 45.
Current-year four-bucket ageing: 52, 15, 25, 80.

Expected current over-three = prior 35 + prior 45 = 80.
Current over-one-year return amount = 15 + 25 + 80 = 120.
Current under-one-year return amount = 52.
Current total = 172.

These are synthetic example figures only.

## Verification and privacy

- Compare the four current-year buckets with their FS note control total.
- Check the control total against the Balance Sheet payable balance.
- Cross-check previous-year buckets to explain ageing roll.
- Review payment and credit-note evidence where balances differ.
- Enter only the two requested current-year bands into the vendor's exported template.
- Benchmark against an independently completed return, but do not treat
  historical classification as infallible.
- Keep all company-specific figures and workbooks private.
