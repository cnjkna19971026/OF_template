"""
gui.py — Tkinter GUI for the OpenFOAM CHT Template Deployer.

This module contains ONLY presentation code.
All business logic lives in the four core modules:
    material_db.py       — material database & lookup
    region_scanner.py    — discover regions from constant/
    boundary_fixer.py    — polyMesh/boundary patch → wall conversion
    template_deployer.py — file copy + substitution + thermo override

GUI flow:
    1. User picks template folder and case folder.
    2. Click "Scan Regions" → RegionScanner runs, table populates.
    3. User reviews the region/material table.
    4. Click "Deploy" → BoundaryFixer + TemplateDeployer + GlobalDeployer run.
"""

import re
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from region_scanner import RegionScanner
from boundary_fixer import BoundaryFixer
from template_deployer import TemplateDeployer, GlobalDeployer


class DeployerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("OpenFOAM CHT Template Deployer")
        self.root.geometry("740x600")
        self.root.resizable(True, True)

        # Path variables
        self.template_dir_var = tk.StringVar()
        self.case_dir_var     = tk.StringVar()

        # Service objects (no state, safe to instantiate once)
        self._scanner  = RegionScanner()
        self._fixer    = BoundaryFixer()
        self._deployer = TemplateDeployer()
        self._global   = GlobalDeployer()

        # Scan results (populated by _scan, consumed by _deploy)
        self._fluids:       list[str] = []
        self._solids:       list[str] = []
        self._material_map: dict      = {}

        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self._build_path_frame()
        self._build_button_bar()
        self._build_region_table()
        self._build_log_panel()

    def _build_path_frame(self) -> None:
        frame = tk.Frame(self.root, padx=12, pady=10)
        frame.pack(fill="x")

        rows = [
            ("Template folder:", self.template_dir_var, self._browse_template),
            ("Case folder:",     self.case_dir_var,     self._browse_case),
        ]
        for i, (label, var, cmd) in enumerate(rows):
            tk.Label(frame, text=label, width=16, anchor="w").grid(
                row=i, column=0, pady=4)
            tk.Entry(frame, textvariable=var, width=56).grid(
                row=i, column=1, pady=4, padx=4)
            tk.Button(frame, text="Browse…", command=cmd).grid(
                row=i, column=2, pady=4)

    def _build_button_bar(self) -> None:
        frame = tk.Frame(self.root, padx=12, pady=2)
        frame.pack(fill="x")

        tk.Button(
            frame, text="①  Scan Regions",
            width=18, command=self._scan
        ).pack(side="left", padx=(0, 8))

        tk.Button(
            frame, text="②  Deploy Templates & Fix Boundaries",
            bg="#1b5e20", fg="white", font=("", 10, "bold"),
            width=36, command=self._deploy
        ).pack(side="left")

    def _build_region_table(self) -> None:
        frame = tk.LabelFrame(
            self.root, text="Detected regions & materials",
            padx=8, pady=6
        )
        frame.pack(fill="x", padx=12, pady=(10, 0))

        cols = ("Region", "Type", "Matched material",
                "κ W/m·K", "ρ kg/m³", "Cp J/kg·K")
        col_widths = {
            "Region": 170, "Type": 52, "Matched material": 140,
            "κ W/m·K": 72, "ρ kg/m³": 72, "Cp J/kg·K": 72,
        }

        self._tree = ttk.Treeview(frame, columns=cols, show="headings", height=7)
        for col in cols:
            self._tree.heading(col, text=col)
            self._tree.column(col, width=col_widths.get(col, 90), anchor="w")
        self._tree.pack(fill="x")

        self._tree.tag_configure("fluid", foreground="#0d47a1")
        self._tree.tag_configure("solid", foreground="#4e342e")
        self._tree.tag_configure("unknown", foreground="#b71c1c")

    def _build_log_panel(self) -> None:
        frame = tk.LabelFrame(self.root, text="Log", padx=8, pady=4)
        frame.pack(fill="both", expand=True, padx=12, pady=8)

        self._log = scrolledtext.ScrolledText(
            frame, height=9, state="disabled",
            bg="#111", fg="#00e676", font=("Courier", 10),
            insertbackground="#00e676",
        )
        self._log.pack(fill="both", expand=True)

    # ── Logging ───────────────────────────────────────────────────────────

    def log(self, msg: str) -> None:
        self._log.config(state="normal")
        self._log.insert(tk.END, msg + "\n")
        self._log.see(tk.END)
        self._log.config(state="disabled")
        self.root.update_idletasks()

    # ── Browse callbacks ──────────────────────────────────────────────────

    def _browse_template(self) -> None:
        d = filedialog.askdirectory(title="Select template folder")
        if d:
            self.template_dir_var.set(d)

    def _browse_case(self) -> None:
        d = filedialog.askdirectory(title="Select OpenFOAM case folder")
        if d:
            self.case_dir_var.set(d)

    # ── Scan ──────────────────────────────────────────────────────────────

    def _scan(self) -> None:
        case_dir = self.case_dir_var.get().strip()
        if not case_dir:
            messagebox.showerror("Error", "Select a case folder first.")
            return

        self.log(f"\n=== Scanning: {case_dir} ===")

        self._fluids, self._solids, self._material_map = \
            self._scanner.scan(case_dir, self.log)

        self._refresh_table()

        self.log(f"\n  Fluids : {self._fluids}")
        self.log(f"  Solids : {self._solids}")

        if not self._fluids and not self._solids:
            messagebox.showwarning(
                "No regions found",
                "Run 'splitMeshRegions -cellZones -overwrite' first,\n"
                "then re-scan."
            )

    def _refresh_table(self) -> None:
        for row in self._tree.get_children():
            self._tree.delete(row)

        for region in self._fluids + self._solids:
            rtype = "fluid" if region in self._fluids else "solid"
            mat   = self._material_map.get(region)

            if mat:
                mat_name = mat["matched_key"]
                kappa    = self._fmt(mat.get("kappa"))
                rho      = self._fmt(mat.get("rho"))
                cp       = self._fmt(mat.get("cp"))
                tag      = rtype
            else:
                mat_name = "⚠ unknown"
                kappa = rho = cp = "—"
                tag = "unknown"

            self._tree.insert(
                "", "end",
                values=(region, rtype, mat_name, kappa, rho, cp),
                tags=(tag,),
            )

    @staticmethod
    def _fmt(value) -> str:
        if value is None:
            return "varies"
        return str(value)

    # ── Deploy ────────────────────────────────────────────────────────────

    def _deploy(self) -> None:
        template_dir = self.template_dir_var.get().strip()
        case_dir     = self.case_dir_var.get().strip()

        if not template_dir or not case_dir:
            messagebox.showerror("Error", "Select both template and case folders.")
            return

        if not self._fluids and not self._solids:
            messagebox.showerror(
                "Error",
                "No regions scanned yet.\nClick '① Scan Regions' first."
            )
            return

        if not messagebox.askyesno(
            "Confirm deploy",
            f"Files in the following case will be overwritten:\n\n{case_dir}\n\nProceed?"
        ):
            return

        self.log("\n=== Deploying templates ===")
        try:
            # 1. Fix boundary types
            self._fixer.fix_all(
                case_dir, self._fluids + self._solids, self.log
            )

            # 2. Deploy per-region physics
            for region in self._fluids:
                self._deployer.deploy_region(
                    template_dir, case_dir, region, "fluid",
                    self._material_map.get(region), self.log
                )
            for region in self._solids:
                self._deployer.deploy_region(
                    template_dir, case_dir, region, "solid",
                    self._material_map.get(region), self.log
                )

            # 3. Deploy global files
            self._global.deploy(
                template_dir, case_dir,
                self._fluids, self._solids, self.log
            )

            self.log("\n✅  Done. Case is ready for chtMultiRegionSimpleFoam.")

        except Exception as exc:
            import traceback
            self.log(f"\n❌  FATAL: {exc}")
            self.log(traceback.format_exc())
