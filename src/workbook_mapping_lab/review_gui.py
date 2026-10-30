"""Windows/local Tkinter review desk for structured financial workbooks.

Only local files are accessed. The GUI does not connect to accounting software,
send telemetry, upload source files or silently approve new classifications.
"""
from __future__ import annotations

import copy
import csv
import json
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .fs_extract import extract_profile, load_profile, scan_sheet
from .learning import propose_mappings
from .mapping import load_csv
from .pipeline import controlled_build
from .review import ReviewSession, require_private_directory
from .simulator import WorkbookSnapshot
from .template_contract import detail_coverage
from .advisories import check_advisories,advisory,evaluate_evidence_rules,load_evidence_rules
from .layout_resolver import resolve_layout, merge_approved_routes, write_private_layout


class ReviewDesk(tk.Tk):
    def __init__(self, session_file: str | None = None):
        super().__init__()
        self.title("Workbook Mapping Lab | Local review")
        self.geometry("1300x830")
        self.minsize(1050, 650)
        self.profile = None
        self.review = None
        self.latest_saved = None
        self.extraction_issues = []
        self.advisory_items = []
        self.advisory_decisions = {}
        self.variables = {
            key:tk.StringVar() for key in (
                "source","previous","profile","layout","prior_rules","previous_target",
                "folder","source_controls","output_controls","template","output","detail_routes","companion_details","advisory_rules"
            )
        }
        self.section=tk.StringVar(value="BS-A")
        self.destination=tk.StringVar()
        self.sign=tk.StringVar(value="keep")
        self.portion=tk.StringVar(value="1")
        self.status=tk.StringVar(value="Load an FS workbook, a reviewed extraction profile and a destination layout.")
        self._make_widgets()
        if session_file:
            data=json.loads(Path(session_file).read_text(encoding="utf-8-sig"))
            if not isinstance(data,dict) or data.get("version")!=1:
                raise ValueError("Unrecognised private session settings")
            for key,value in data.get("paths",{}).items():
                if key in self.variables and isinstance(value,str):
                    self.variables[key].set(value)
            self.status.set("Private session paths loaded; click Extract profile rows to begin.")

    def _path_row(self, parent, label, key, kind="file", row=0):
        ttk.Label(parent,text=label).grid(row=row,column=0,sticky="w",padx=5,pady=4)
        entry=ttk.Entry(parent,textvariable=self.variables[key],width=90)
        entry.grid(row=row,column=1,sticky="ew",padx=5)
        def browse():
            if kind=="dir":
                p=filedialog.askdirectory(title="Choose a private folder")
            elif kind=="save":
                p=filedialog.asksaveasfilename(
                    defaultextension=".xlsx",filetypes=[("Excel workbook","*.xlsx")])
            elif key in ("layout","prior_rules","source_controls","output_controls","detail_routes","companion_details","advisory_rules"):
                p=filedialog.askopenfilename(filetypes=[("CSV files","*.csv"),("All files","*.*")])
            elif key=="profile":
                p=filedialog.askopenfilename(filetypes=[("Profile JSON","*.json")])
            else:
                p=filedialog.askopenfilename(filetypes=[("Excel workbook","*.xlsx"),("All files","*.*")])
            if p:
                self.variables[key].set(p)
                if key in ("profile","source","layout","prior_rules"):
                    self.review=None
                    self.latest_saved=None
        ttk.Button(parent,text="Browse",command=browse,width=10).grid(row=row,column=2,padx=4)
        return entry

    def _make_widgets(self):
        padding={"padx":11,"pady":6}
        heading=ttk.Frame(self)
        heading.pack(fill="x",**padding)
        ttk.Label(heading,text="Workbook Mapping Lab",font=("Segoe UI",16,"bold")).pack(anchor="w")
        ttk.Label(heading,text="Private review • Historic classifications are reused only when the source is unchanged.").pack(anchor="w")
        notebook=ttk.Notebook(self)
        notebook.pack(fill="both",expand=True,padx=12,pady=4)
        setup=ttk.Frame(notebook)
        review=ttk.Frame(notebook)
        warnings_tab=ttk.Frame(notebook)
        build=ttk.Frame(notebook)
        notebook.add(setup,text=" 1  Sources ")
        notebook.add(review,text=" 2  Review mappings ")
        notebook.add(warnings_tab,text=" 3  Warnings (advisory) ")
        notebook.add(build,text=" 4  Build checked copy ")

        top=ttk.LabelFrame(setup,text="Local source files")
        top.pack(fill="x",**padding)
        top.columnconfigure(1,weight=1)
        for i,(label,key) in enumerate([
            ("Current-year FS (.xlsx)","source"),
            ("Previous-year FS (optional)","previous"),
            ("Reviewed extraction profile (.json)","profile"),
            ("Target-field layout (.csv)","layout"),
            ("Existing approved rules (optional, .csv)","prior_rules"),
            ("Approved detailed target routes (.csv)","detail_routes"),
            ("Previous-year populated destination (optional)","previous_target"),
            ("Additional advisory checks (optional, .json)","advisory_rules"),
            ("Private working folder","folder"),
        ]):
            self._path_row(top,label,key,"dir" if key=="folder" else "file",i)
        row=ttk.Frame(setup)
        row.pack(fill="x",**padding)
        ttk.Button(row,text="Extract profile rows",command=self.load_selected).pack(side="left",padx=5)
        ttk.Button(row,text="Find additional rows",command=self.open_scanner).pack(side="left",padx=5)
        ttk.Button(row,text="View extraction findings",command=self.show_findings).pack(side="left",padx=5)
        ttk.Button(row,text="Resolve detailed fields",command=self.resolve_detail_fields).pack(side="left",padx=5)
        ttk.Button(row,text="Save updated profile privately",command=self.save_profile).pack(side="left",padx=5)
        ttk.Label(setup,text=("Use the scan window to add new items. Never include totals and their "
                              "underlying detail in the same section.")).pack(anchor="w",padx=20)

        frame=ttk.Frame(review)
        frame.pack(fill="both",expand=True,padx=10,pady=8)
        cols=("status","section","caption","current","previous","risk","target","location")
        self.tree=ttk.Treeview(frame,columns=cols,show="headings",selectmode="browse")
        labels={"status":"Decision","section":"Section","caption":"FS item",
                "current":"Current","previous":"Prior","risk":"Exceptions",
                "target":"Target field","location":"Source cell"}
        widths={"status":105,"section":78,"caption":245,"current":118,
                "previous":118,"risk":230,"target":185,"location":165}
        for key in cols:
            self.tree.heading(key,text=labels[key])
            self.tree.column(key,width=widths[key],stretch=key in ("caption","risk","target"))
        self.tree.grid(row=0,column=0,sticky="nsew")
        bar=ttk.Scrollbar(frame,orient="vertical",command=self.tree.yview)
        bar.grid(row=0,column=1,sticky="ns")
        self.tree.configure(yscrollcommand=bar.set)
        frame.rowconfigure(0,weight=1)
        frame.columnconfigure(0,weight=1)
        self.tree.bind("<<TreeviewSelect>>",lambda e:self._selected_row())

        actions=ttk.LabelFrame(review,text="Review selected field")
        actions.pack(fill="x",padx=12,pady=5)
        ttk.Label(actions,text="Destination").grid(row=0,column=0,padx=6,pady=8)
        self.field_choice=ttk.Combobox(actions,textvariable=self.destination,width=42,state="readonly")
        self.field_choice.grid(row=0,column=1,sticky="ew",padx=4)
        ttk.Label(actions,text="Portion").grid(row=0,column=2,padx=4)
        ttk.Entry(actions,textvariable=self.portion,width=7).grid(row=0,column=3,padx=4)
        ttk.Label(actions,text="Sign").grid(row=0,column=4,padx=4)
        ttk.Combobox(actions,textvariable=self.sign,values=["keep","reverse"],width=10,state="readonly").grid(row=0,column=5,padx=4)
        ttk.Button(actions,text="Approve selected",command=self.approve_row).grid(row=0,column=6,padx=8)
        ttk.Button(actions,text="Revoke",command=self.revoke_row).grid(row=0,column=7,padx=6)
        actions.columnconfigure(1,weight=1)
        ttk.Button(review,text="Export private source + approved rules + exception report",
                   command=self.export_review).pack(anchor="e",padx=14,pady=8)

        warning_heading=ttk.Frame(warnings_tab)
        warning_heading.pack(fill="x",padx=12,pady=10)
        ttk.Label(warning_heading,text="Independent classification warnings",
                  font=("Segoe UI",13,"bold")).pack(anchor="w")
        ttk.Label(warning_heading,text="Warnings are optional advice: they never change figures or prevent a build. "
                  "Strict structural and reconciliation checks remain separate.").pack(anchor="w",pady=4)
        cols_warning=("severity","period","title","difference","decision")
        warning_frame=ttk.Frame(warnings_tab)
        warning_frame.pack(fill="both",expand=True,padx=12,pady=4)
        self.warning_table=ttk.Treeview(warning_frame,columns=cols_warning,
                                        show="headings",selectmode="browse",height=8)
        for key,width in (("severity",85),("period",110),("title",580),
                          ("difference",120),("decision",140)):
            self.warning_table.heading(key,text=key.title())
            self.warning_table.column(key,width=width,stretch=key=="title")
        self.warning_table.pack(fill="both",expand=True)
        self.warning_table.bind("<<TreeviewSelect>>",lambda e:self._warning_selected())
        ttk.Label(warnings_tab,text="Evidence and suggested next step").pack(anchor="w",padx=14,pady=4)
        self.warning_details=tk.Text(warnings_tab,height=9,wrap="word",
                                     font=("Segoe UI",10),state="disabled")
        self.warning_details.pack(fill="x",padx=12)
        notes_frame=ttk.Frame(warnings_tab)
        notes_frame.pack(fill="x",padx=12,pady=8)
        ttk.Label(notes_frame,text="Optional reviewer note").pack(side="left",padx=4)
        self.warning_note=tk.StringVar()
        ttk.Entry(notes_frame,textvariable=self.warning_note,width=95).pack(side="left",fill="x",expand=True,padx=4)
        actions_warning=ttk.Frame(warnings_tab)
        actions_warning.pack(fill="x",padx=12,pady=8)
        ttk.Button(actions_warning,text="Re-check evidence",command=self.refresh_warnings).pack(side="left",padx=4)
        ttk.Button(actions_warning,text="Mark reviewed (no changes)",command=self.acknowledge_warning).pack(side="left",padx=4)
        ttk.Button(actions_warning,text="Reopen warning",command=self.reopen_warning).pack(side="left",padx=4)
        ttk.Button(actions_warning,text="Export warnings privately",command=self.save_warnings).pack(side="right",padx=4)

        task=ttk.LabelFrame(build,text="Only after every extracted item is reviewed")
        task.pack(fill="x",padx=10,pady=12)
        task.columnconfigure(1,weight=1)
        for i,(label,key,kind) in enumerate([
            ("Original blank destination template","template","file"),
            ("Independent source section totals","source_controls","file"),
            ("Independent expected output totals","output_controls","file"),
            ("Approved parent-child detail amounts (optional)","companion_details","file"),
            ("New checked-copy output filename","output","save"),
        ]):
            self._path_row(task,label,key,kind,i)
        ttk.Button(task,text="Build and verify checked copy",command=self.build_copy).grid(
            row=5,column=1,sticky="e",padx=10,pady=15)
        ttk.Label(build,text="This does not submit to any external application. Use an unused output filename.").pack(
            anchor="w",padx=20)

        status_bar=ttk.Frame(self)
        status_bar.pack(fill="x",padx=16,pady=7)
        ttk.Separator(status_bar,orient="horizontal").pack(fill="x")
        ttk.Label(status_bar,textvariable=self.status).pack(anchor="w",pady=4)

    def _show_error(self, message):
        self.status.set("Action blocked: " + str(message)[:250])
        messagebox.showerror("Unable to continue",str(message),parent=self)

    def _file(self, key, required=True):
        val=self.variables[key].get().strip()
        if not val and required:
            raise ValueError(f"Select {key.replace('_',' ')}")
        return val

    def _warning_key(self, item):
        return "|".join((item.get("code",""),item.get("period",""),item.get("title","")))

    def refresh_warnings(self):
        """Independent evidence checks; never alter approved mappings."""
        previous=self._file("previous",False)
        prior_irs=self._file("previous_target",False)
        current=self._file("source",False)
        try:
            self.advisory_items=check_advisories(previous,prior_irs,current or None)
            if self._file("advisory_rules",False):
                rule_checks=load_evidence_rules(self._file("advisory_rules"))
                self.advisory_items.extend(evaluate_evidence_rules({
                    "previous_fs":previous,
                    "previous_return":prior_irs,
                    "current_fs":current,
                },rule_checks))
        except (ValueError,KeyError,OSError) as err:
            self.advisory_items=[advisory(
                "EVIDENCE_CHECK_INCOMPLETE",
                "Could not verify historical classification evidence",
                "One or more selected workbooks could not be interpreted: "+str(err),
                "Review the input workbook layouts. The mapping workflow is unaffected.",
                severity="Info",
            )]
        self._draw_warnings()
        flagged=sum(item["severity"]=="Review" for item in self.advisory_items)
        self.status.set(f"Advisory review: {flagged} issue(s) to consider; "
                        "none prevent preparation or change figures.")
        return self.advisory_items

    def _draw_warnings(self):
        self.warning_table.delete(*self.warning_table.get_children())
        for n,item in enumerate(self.advisory_items):
            decision=self.advisory_decisions.get(self._warning_key(item),{})
            status="Reviewed" if decision.get("acknowledged") else "Not reviewed"
            self.warning_table.insert("",tk.END,iid=str(n),values=(
                item["severity"],item["period"],item["title"],
                item.get("difference") or "—",status))
        self.warning_note.set("")
        self.warning_details.config(state="normal")
        self.warning_details.delete("1.0","end")
        self.warning_details.insert("end",
                                    "Select a warning to see the source references, explanation and suggested review.")
        self.warning_details.config(state="disabled")

    def _warning_selected(self):
        selected=self.warning_table.selection()
        if not selected:
            return
        item=self.advisory_items[int(selected[0])]
        state=self.advisory_decisions.get(self._warning_key(item),{})
        self.warning_note.set(state.get("note",""))
        lines=[
            item["title"],
            "",
            item["explanation"],
            "",
            "Suggested check: "+item["suggested_action"],
            "",
            "Source evidence:",
        ]
        for proof in item.get("evidence",[]):
            location=proof.get("sheet","")+"!"+proof.get("cell","")
            lines.append("  "+proof.get("source","")+" | "+location+" | "+
                         proof.get("description","")+": "+
                         proof.get("amount",proof.get("text","")))
        lines.extend(["","This is a non-blocking advisory. Only explicit mapping approvals can change the output."])
        self.warning_details.config(state="normal")
        self.warning_details.delete("1.0","end")
        self.warning_details.insert("end","\n".join(lines))
        self.warning_details.config(state="disabled")

    def acknowledge_warning(self):
        selection=self.warning_table.selection()
        if not selection:
            self.status.set("Select a warning before marking it reviewed.")
            return
        item=self.advisory_items[int(selection[0])]
        self.advisory_decisions[self._warning_key(item)]={
            "acknowledged":True, "note":self.warning_note.get().strip()[:600],
        }
        self._draw_warnings()
        self.warning_table.selection_set(selection[0])
        self._warning_selected()
        self.status.set("Warning marked reviewed; financial data and mapping remain unchanged.")

    def reopen_warning(self):
        selection=self.warning_table.selection()
        if not selection:
            return
        item=self.advisory_items[int(selection[0])]
        previous=self.advisory_decisions.get(self._warning_key(item),{})
        self.advisory_decisions[self._warning_key(item)]={
            "acknowledged":False, "note":previous.get("note",""),
        }
        self._draw_warnings()
        self.warning_table.selection_set(selection[0])
        self._warning_selected()
        self.status.set("Warning reopened; this does not restrict workbook generation.")

    def save_warnings(self):
        try:
            from datetime import datetime
            folder=require_private_directory(self._file("folder"))
            dest=folder/("advisory_warnings_PRIVATE_"+
                         datetime.now().strftime("%Y%m%d_%H%M%S_%f")+".json")
            records=[]
            for w in self.advisory_items:
                entry=dict(w)
                decision=self.advisory_decisions.get(self._warning_key(w),{})
                entry["acknowledged"]=bool(decision.get("acknowledged"))
                entry["reviewer_note"]=decision.get("note","")
                records.append(entry)
            dest.write_text(json.dumps({
                "purpose":"Optional accounting warnings; no mappings changed",
                "not_a_release_gate":True,
                "warnings":records,
            },indent=2),encoding="utf-8")
            self.status.set("Private warnings report saved; no financial data modified.")
        except Exception as err:
            self._show_error(err)

    def load_selected(self):
        try:
            source=self._file("source")
            profile=load_profile(self._file("profile"))
            fields=load_csv(self._file("layout"),
                            ("field_id","section","sheet","cell","anchor_cell","anchor_text"))
            prior=[]
            if self._file("prior_rules",False):
                prior=load_csv(self._file("prior_rules"),
                               ("source_id","field_id","approved"))
            rows,issues=extract_profile(source,profile,
                previous_workbook_path=self._file("previous",False) or None)
            if self._file("previous_target",False) and self._file("template",False):
                contract=detail_coverage(self._file("previous_target"),self._file("template"))
                for sheet in contract["missing_active_detail_sheets"]:
                    issues.append({"issue":"VENDOR_TEMPLATE_DETAIL_MISSING",
                                   "source_id":"",
                                   "detail":sheet["sheet"]+" — export the active detail schedule from the application"})
            self.profile=profile
            proposals=[]
            if self._file("previous_target",False):
                proposals,reference_issues=propose_mappings(
                    rows,self._file("previous_target"),fields)
                if reference_issues:
                    self.status.set(f"Prior destination lookup: {len(reference_issues)} fields unresolved; review manually.")
            self.extraction_issues=issues
            self.review=ReviewSession(rows,issues,fields,prior,suggestions=proposals)
            self.latest_saved=None
            self._draw_rows()
            self.refresh_warnings()
            suggestion_count=sum(1 for x in self.review.entries.values() if x["review_status"]=="SUGGESTED")
            self.status.set(f"{len(rows)} details; {suggestion_count} suggested mappings; "
                            f"{len(self.review.unresolved())} need decisions; {len(issues)} findings.")
        except Exception as err:
            self._show_error(err)

    def resolve_detail_fields(self):
        """Refresh field positions only from the original exported workbook."""
        try:
            template=self._file("template")
            private=require_private_directory(self._file("folder"))
            if self._file("previous_target",False):
                contract=detail_coverage(self._file("previous_target"),template)
                if contract["status"]!="READY_FOR_REVIEW":
                    missing=", ".join(x["sheet"] for x in contract["missing_active_detail_sheets"])
                    raise ValueError("The current vendor export is missing active detailed schedules: "+missing)
            routes=load_csv(self._file("detail_routes"),("field_id","section","sheet","caption"))
            original=load_csv(self._file("layout"),
                ("field_id","section","sheet","cell","anchor_cell","anchor_text"))
            result=resolve_layout(template,routes)
            if result["status"]!="READY":
                missing="; ".join(x["field_id"]+": "+x["code"] for x in result["exceptions"])
                raise ValueError("Cannot safely resolve vendor detail cells: "+missing)
            merged=merge_approved_routes(original,result)
            from datetime import datetime
            path=private/("resolved_target_layout_"+datetime.now().strftime("%Y%m%d_%H%M%S_%f")+".csv")
            write_private_layout(merged,str(path))
            self.variables["layout"].set(str(path))
            self.review=None
            self.latest_saved=None
            self.status.set(f"Resolved {len(result['layout'])} exact detailed destinations. Review all mappings again before building.")
            messagebox.showinfo("Vendor template resolved",
                "All requested detailed destinations were found in the original export. "+
                "A private reviewed layout was created. No vendor file was modified.",parent=self)
        except Exception as err:
            self._show_error(err)

    def show_findings(self):
        dlg=tk.Toplevel(self)
        dlg.title("Source extraction findings")
        dlg.geometry("900x500")
        ttk.Label(dlg,text="Review new or changed source lines before building.",
                  font=("Segoe UI",11,"bold")).pack(anchor="w",padx=12,pady=10)
        cols=("issue","source_id","detail")
        tree=ttk.Treeview(dlg,columns=cols,show="headings")
        for key,width in (("issue",260),("source_id",220),("detail",390)):
            tree.heading(key,text=key.replace("_"," ").title())
            tree.column(key,width=width,stretch=key=="detail")
        tree.pack(fill="both",expand=True,padx=12,pady=7)
        for i,issue in enumerate(self.extraction_issues):
            tree.insert("",tk.END,iid=str(i),values=(
                issue.get("issue",""),issue.get("source_id",""),
                issue.get("detail","")))
        ttk.Label(dlg,text="New numeric rows are blocking exceptions until reviewed.").pack(
            anchor="w",padx=13,pady=10)


    def _draw_rows(self):
        self.tree.delete(*self.tree.get_children())
        if not self.review:
            return
        for sid,row in self.review.entries.items():
            self.tree.insert("",tk.END,iid=sid,values=(
                row.get("review_status"),row["section"],
                row["caption"][:130],row["amount"],row.get("previous_amount",""),
                ("; ".join(filter(None,[row.get("risk"),row.get("notice")])) or "—"),
                row.get("target_hint") or "—",
                f'{row.get("sheet","")}!{row.get("cell","")}',
            ))

    def _selected_row(self):
        if not self.review:
            return
        selected=self.tree.selection()
        if not selected:
            return
        sid=selected[0]
        row=self.review.entries.get(sid)
        if not row:
            return
        choices=[fid for fid,item in self.review.layout.items()
                 if item["section"]==row["section"]]
        self.field_choice["values"]=choices
        hint=row.get("target_hint","")
        self.destination.set(hint if hint in choices else (choices[0] if len(choices)==1 else ""))
        self.sign.set("keep")
        self.portion.set("1")

    def approve_row(self):
        try:
            if not self.review or not self.tree.selection():
                raise ValueError("Select an extracted row first")
            sid=self.tree.selection()[0]
            entry=self.review.entries[sid]
            accept=not entry.get("risk")
            if not accept:
                accept=messagebox.askyesno("Confirm source exception",
                    "Source requires review:\n"+entry["risk"]+
                    "\n\nHave you checked the underlying workbook and approved this treatment?",
                    parent=self)
            if not accept:
                return
            self.review.approve(sid,self.destination.get().strip(),
                portion=self.portion.get().strip(),sign=self.sign.get(),
                acknowledge_risks=accept)
            self.latest_saved=None
            self._draw_rows()
            self.status.set(f"Approved {sid}. Remaining items: {len(self.review.unresolved())}.")
        except Exception as err:
            self._show_error(err)

    def revoke_row(self):
        if self.review and self.tree.selection():
            self.review.revoke(self.tree.selection()[0])
            self.latest_saved=None
            self._draw_rows()
            self.status.set("Mapping revoked. No new file has been built.")

    def save_profile(self):
        try:
            if self.profile is None:
                raise ValueError("Load a profile and extract first")
            dest=require_private_directory(self._file("folder"))
            f=dest/"reviewed_extraction_profile.json"
            if f.exists():
                raise FileExistsError("Profile already exists; choose a new private folder")
            f.write_text(json.dumps(self.profile,indent=2),encoding="utf-8")
            self.variables["profile"].set(str(f))
            self.status.set("Saved profile privately. Click Extract profile rows to review the added items.")
        except Exception as err:
            self._show_error(err)

    def open_scanner(self):
        try:
            source=self._file("source")
            profile=load_profile(self._file("profile"))
            with WorkbookSnapshot(source) as w:
                sheet_names=list(w.sheets)
            if not sheet_names:
                raise ValueError("No readable worksheets")
        except Exception as err:
            self._show_error(err)
            return
        dlg=tk.Toplevel(self)
        dlg.title("Find new source rows (manual selection)")
        dlg.geometry("1040x660")
        sheet=tk.StringVar(value=profile["ranges"][0]["sheet"])
        section=tk.StringVar(value="PL-E")
        start=tk.StringVar(value="1")
        end=tk.StringVar(value="350")
        controls=ttk.Frame(dlg)
        controls.pack(fill="x",padx=10,pady=8)
        for label,var,options in [
            ("Worksheet",sheet,sheet_names),
            ("Section",section,["BS-A","BS-L","BS-MEMO","PL-I","PL-E"])]:
            ttk.Label(controls,text=label).pack(side="left",padx=3)
            ttk.Combobox(controls,textvariable=var,values=options,width=27 if label=="Worksheet" else 11).pack(side="left",padx=5)
        for label,var in (("From",start),("To",end)):
            ttk.Label(controls,text=label).pack(side="left")
            ttk.Entry(controls,textvariable=var,width=6).pack(side="left",padx=4)
        cols=("row","label","value","previous","risk")
        grid=ttk.Treeview(dlg,columns=cols,show="headings",selectmode="extended")
        for col,width in zip(cols,(65,430,140,140,210)):
            grid.heading(col,text=col.title())
            grid.column(col,width=width,stretch=col in ("label","risk"))
        grid.pack(fill="both",expand=True,padx=12,pady=6)
        candidates={}
        def scan():
            try:
                with WorkbookSnapshot(source) as wb:
                    raw=scan_sheet(wb,sheet.get(),
                        start_row=int(start.get()),end_row=int(end.get()))
                grid.delete(*grid.get_children())
                candidates.clear()
                for entry in raw:
                    rid=entry["row"]
                    candidates[rid]=entry
                    grid.insert("",tk.END,iid=rid,
                                values=(rid,entry["caption"][:130],
                                    entry["current_amount"],entry["previous_amount"],entry["risk"]))
            except Exception as exc:
                messagebox.showerror("Cannot scan",str(exc),parent=dlg)
        def include():
            selected=grid.selection()
            if not selected:
                return
            if not messagebox.askyesno("Confirm detail-only selection",
                f"Add {len(selected)} rows as candidate details in section {section.get()}?\n"
                "Do not select statement totals or repeated note figures.",parent=dlg):
                return
            target=None
            for block in profile["ranges"]:
                if block["sheet"]==sheet.get() and block["section"]==section.get():
                    target=block
                    break
            if target is None:
                base=profile["ranges"][0]
                target={"sheet":sheet.get(),"section":section.get(),
                        "caption_column":base["caption_column"],
                        "current_column":base["current_column"],
                        "previous_column":base.get("previous_column",""),
                        "unit":base.get("unit","rupees"),"selected_rows":[]}
                profile["ranges"].append(target)
            rows=set(target["selected_rows"])
            rows.update(int(x) for x in selected)
            target["selected_rows"]=sorted(rows)
            self.profile=profile
            # Reading a modified profile requires a private save before release.
            self.review=None
            self.latest_saved=None
            self.status.set(f"Added {len(selected)} candidates. Save updated profile privately, then load and review it.")
            dlg.destroy()
        buttons=ttk.Frame(dlg)
        buttons.pack(pady=8)
        ttk.Button(buttons,text="Scan",command=scan).pack(side="left",padx=6)
        ttk.Button(buttons,text="Add selected to profile",command=include).pack(side="left",padx=6)
        scan()

    def export_review(self):
        try:
            if not self.review:
                raise ValueError("Read profile rows first")
            from datetime import datetime
            base_prefix="local_review_"+datetime.now().strftime("%Y%m%d_%H%M%S")
            self.latest_saved=self.review.save_review(self._file("folder"),
                prefix=base_prefix)
            if self.latest_saved["status"]!="PASS":
                self.status.set("Review exported privately, but BUILD BLOCKED: outstanding exceptions.")
                messagebox.showwarning("Outstanding decisions",
                    f"{len(self.review.unresolved())} rows remain unresolved. "
                    "See the private exception report.",parent=self)
            else:
                self.status.set("Private review exported. All selected rows have approved field mappings.")
        except Exception as err:
            self._show_error(err)

    def build_copy(self):
        try:
            if not self.review or self.review.unresolved():
                raise ValueError("Resolve all selected-source mapping decisions first")
            if not self.latest_saved or self.latest_saved["status"]!="PASS":
                raise ValueError("Export a PASS private review before building")
            if not messagebox.askyesno("Build workbook copy",
                  "Generate a new test-only XLSX using the reviewed rules and independent totals?\n"
                  "The original template will remain unchanged.",parent=self):
                return
            result=controlled_build(
                source=self.latest_saved["sources"],rules=self.latest_saved["rules"],
                layout=self._file("layout"),template=self._file("template"),
                source_controls=self._file("source_controls"),
                output_controls=self._file("output_controls"),
                output=self._file("output"),
                previous_export=self._file("previous_target",False) or None,
                companion_details=self._file("companion_details",False) or None,
                exception_report=str(require_private_directory(self._file("folder"))/
                                     "build_result_private.json"),
                rounding="whole_rupees")
            if result["status"]=="PASS":
                self.status.set("Checked workbook copy created and independently verified. External import not tested.")
                messagebox.showinfo("Checked copy created",
                    "Offline checks passed. The target application's actual import still needs verification.",
                    parent=self)
            else:
                self.status.set("BUILD BLOCKED by reconciliation or mapping exceptions.")
                messagebox.showwarning("Build blocked",
                    "Review build_result_private.json in the private folder.",parent=self)
        except Exception as err:
            self._show_error(err)


def main():
    import argparse
    parser=argparse.ArgumentParser(description="Local-only financial workbook review")
    parser.add_argument("--session",help="Private local paths/settings JSON")
    options=parser.parse_args()
    try:
        ReviewDesk(session_file=options.session).mainloop()
    except tk.TclError as e:
        raise RuntimeError("A graphical Windows desktop session is required") from e


if __name__=="__main__":
    main()
