from __future__ import annotations

import argparse
from .mapping import apply, discover, load_csv, save_csv


def main() -> None:
    p = argparse.ArgumentParser(description="Winman FS Mapper — review-only prototype")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("discover", help="Suggest PY FS → PY Winman mappings; never auto-approve")
    a.add_argument("--previous-fs", required=True)
    a.add_argument("--previous-winman", required=True)
    a.add_argument("--output", required=True)
    b = sub.add_parser("apply", help="Apply accountant-approved rules to CY FS")
    b.add_argument("--current-fs", required=True)
    b.add_argument("--approved-rules", required=True)
    b.add_argument("--target-fields", required=True)
    b.add_argument("--output", required=True)
    b.add_argument("--exceptions", required=True)
    args = p.parse_args()
    if args.cmd == "discover":
        src = load_csv(args.previous_fs, ("source_id", "section", "caption", "amount"))
        target = load_csv(args.previous_winman, ("field_id", "section", "caption", "amount"))
        rows = discover(src, target)
        save_csv(args.output,
                 ("source_id", "section", "source_caption", "suggested_field_id",
                  "candidate_count", "status", "approved"), rows)
        print(f"Wrote {len(rows)} mapping candidates; none approved automatically.")
    else:
        src = load_csv(args.current_fs, ("source_id", "section", "caption", "amount"))
        rules = load_csv(args.approved_rules, ("source_id", "field_id", "approved"))
        fields = load_csv(args.target_fields, ("field_id", "section", "caption"))
        rows, issues = apply(src, rules, fields)
        save_csv(args.output, ("field_id", "section", "caption", "amount"), rows)
        save_csv(args.exceptions, ("issue", "source_id", "field_id"), issues)
        print(f"Mapped {len(rows)} target fields; {len(issues)} exceptions. No Winman files changed.")


if __name__ == "__main__":
    main()
