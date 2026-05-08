"""
gui.py — Unified OpenFOAM CHT Toolchain GUI

Single tabbed window covering the complete workflow in order:

  Tab 1 — Build Template
           Point at a tutorial case → auto-scaffold fluid/solid/global template.

  Tab 2 — Deploy & Run
           Point at template + case → scan regions → fix boundaries →
           deploy material properties → write Allrun/Allclean → launch.

  Tab 3 — Pipeline Status
           Live stdout/stderr from Allrun sub-process with per-step progress.

No business logic lives here. All computation is in:
    template_builder.py   material_db.py    region_scanner.py
    boundary_fixer.py     template_deployer.py   allrun_writer.py
"""

import os
import re
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from template_builder  import TemplateBuilder, detect_tutorial_regions
from region_scanner    import RegionScanner
from boundary_fixer    import BoundaryFixer
from template_deployer import TemplateDeployer, GlobalDeployer
from allrun_writer     import AllrunWriter


# ── Shared style constants ────────────────────────────────────────────────────
FONT_MONO  = ("Courier", 10)
FONT_BOLD  = ("TkDefaultFont", 10, "bold")
BG_LOG     = "#111111"
FG_LOG     = "#00e676"
BTN_GO     = dict(bg="#1b5e20", fg="white", font=FONT_BOLD)
BTN_BUILD  = dict(bg="#1a237e", fg="white", font=FONT_BOLD)
BTN_WARN   = dict(bg="#b71c1c", fg="white", font=FONT_BOLD)
PAD        = dict(padx=10, pady=4)


def _browse_dir(var: tk.StringVar, title: str) -> None:
    d = filedialog.askdirectory(title=title)
    if d:
        var.set(d)


def _browse_file(var: tk.StringVar, title: str, ftypes: list) -> None:
    f = filedialog.askopenfilename(title=title, filetypes=ftypes)
    if f:
        var.set(f)


# =============================================================================
# TAB 1 — Template Builder
# =============================================================================

class BuilderTab(tk.Frame):
    """
    Converts an existing OpenFOAM tutorial case into a reusable template.
    Wraps TemplateBuilder + detect_tutorial_regions.
    """

    def __init__(self, parent: ttk.Notebook, shared_template_var: tk.StringVar):
        super().__init__(parent)
        self._shared_template = shared_template_var   # syncs to Deploy tab
        self._source_var = tk.StringVar()
        self._output_var = tk.StringVar()
        self._fluid_var  = tk.StringVar()
        self._solid_var  = tk.StringVar()
        self._build_ui()

    def _build_ui(self) -> None:
        # ── Paths ─────────────────────────────────────────────────────────
        pf = tk.LabelFrame(self, text="Paths", **PAD)
        pf.pack(fill="x", **PAD)

        path_rows = [
            ("Tutorial case dir:",    self._source_var, "Select source tutorial case"),
            ("Output template dir:",  self._output_var, "Select output template folder"),
        ]
        for i, (label, var, title) in enumerate(path_rows):
            tk.Label(pf, text=label, width=20, anchor="w").grid(row=i, column=0, pady=3)
            tk.Entry(pf, textvariable=var, width=52).grid(row=i, column=1, pady=3, padx=4)
            tk.Button(pf, text="Browse…",
                      command=lambda v=var, t=title: _browse_dir(v, t)).grid(row=i, column=2)

        # ── Region override ────────────────────────────────────────────────
        rf = tk.LabelFrame(self, text="Region names  (blank = auto-detect from tutorial)", **PAD)
        rf.pack(fill="x", **PAD)

        tk.Label(rf, text="Fluid regions (space-separated):", anchor="w").pack(fill="x")
        tk.Entry(rf, textvariable=self._fluid_var, width=70).pack(fill="x", pady=2)
        tk.Label(rf, text="Solid regions (space-separated):", anchor="w").pack(fill="x", pady=(6,0))
        tk.Entry(rf, textvariable=self._solid_var, width=70).pack(fill="x", pady=2)

        # ── Buttons ────────────────────────────────────────────────────────
        bf = tk.Frame(self, **PAD)
        bf.pack(fill="x", **PAD)
        tk.Button(bf, text="Auto-detect regions", width=20,
                  command=self._detect).pack(side="left", padx=(0, 8))
        tk.Button(bf, text="Build Template", width=18,
                  **BTN_BUILD, command=self._build).pack(side="left")

        # ── Log ───────────────────────────────────────────────────────────
        lf = tk.LabelFrame(self, text="Log", **PAD)
        lf.pack(fill="both", expand=True, **PAD)
        self._log_widget = scrolledtext.ScrolledText(
            lf, state="disabled", bg=BG_LOG, fg=FG_LOG, font=FONT_MONO)
        self._log_widget.pack(fill="both", expand=True)

    def log(self, msg: str) -> None:
        self._log_widget.config(state="normal")
        self._log_widget.insert(tk.END, msg + "\n")
        self._log_widget.see(tk.END)
        self._log_widget.config(state="disabled")
        self.update_idletasks()

    def _detect(self) -> None:
        source = self._source_var.get().strip()
        if not source:
            messagebox.showerror("Error", "Select a tutorial case directory first.")
            return
        self.log("\nAuto-detecting regions...")
        fluids, solids = detect_tutorial_regions(source, self.log)
        self._fluid_var.set(" ".join(fluids))
        self._solid_var.set(" ".join(solids))

    def _build(self) -> None:
        source = self._source_var.get().strip()
        output = self._output_var.get().strip()
        if not source or not output:
            messagebox.showerror("Error", "Select both source and output directories.")
            return

        fluids = self._fluid_var.get().split()
        solids = self._solid_var.get().split()

        if not fluids or not solids:
            self.log("\nNo regions specified — running auto-detect...")
            fluids, solids = detect_tutorial_regions(source, self.log)
            self._fluid_var.set(" ".join(fluids))
            self._solid_var.set(" ".join(solids))

        if not fluids and not solids:
            messagebox.showerror("Error",
                "No regions found. Specify them manually or choose a different tutorial case.")
            return

        builder = TemplateBuilder(source, output, self.log)
        ok = builder.build(fluids, solids)

        if ok:
            # Push output path to Deploy tab automatically
            self._shared_template.set(output)
            messagebox.showinfo("Done",
                f"Template built at:\n{output}\n\nTemplate folder pre-filled in Deploy tab.")


# =============================================================================
# TAB 2 — Deploy & Configure
# =============================================================================

class DeployTab(tk.Frame):
    """
    Applies template to a case and writes Allrun/Allclean.
    Wraps RegionScanner, BoundaryFixer, TemplateDeployer, GlobalDeployer,
    AllrunWriter.
    """

    def __init__(self, parent: ttk.Notebook, shared_template_var: tk.StringVar):
        super().__init__(parent)
        self._template_var = shared_template_var
        self._case_var     = tk.StringVar()
        self._msh_var      = tk.StringVar(value="case.msh")
        self._scale_var    = tk.StringVar(value="0.001")
        self._parallel_var = tk.BooleanVar(value=False)
        self._nprocs_var   = tk.StringVar(value="4")

        # State set by scan, consumed by deploy
        self._fluids:       list[str] = []
        self._solids:       list[str] = []
        self._material_map: dict      = {}

        self._scanner  = RegionScanner()
        self._fixer    = BoundaryFixer()
        self._deployer = TemplateDeployer()
        self._global   = GlobalDeployer()
        self._writer   = AllrunWriter()

        self._build_ui()

    def _build_ui(self) -> None:
        # ── Paths ─────────────────────────────────────────────────────────
        pf = tk.LabelFrame(self, text="Paths", **PAD)
        pf.pack(fill="x", **PAD)

        path_rows = [
            ("Template folder:", self._template_var, "Select template folder"),
            ("Case folder:",     self._case_var,     "Select OpenFOAM case folder"),
        ]
        for i, (label, var, title) in enumerate(path_rows):
            tk.Label(pf, text=label, width=16, anchor="w").grid(row=i, column=0, pady=3)
            tk.Entry(pf, textvariable=var, width=54).grid(row=i, column=1, pady=3, padx=4)
            tk.Button(pf, text="Browse…",
                      command=lambda v=var, t=title: _browse_dir(v, t)).grid(row=i, column=2)

        # ── Allrun options ─────────────────────────────────────────────────
        of = tk.LabelFrame(self, text="Allrun options", **PAD)
        of.pack(fill="x", **PAD)

        tk.Label(of, text=".msh filename (relative to case):", anchor="w").grid(
            row=0, column=0, sticky="w", pady=2)
        tk.Entry(of, textvariable=self._msh_var, width=30).grid(row=0, column=1, sticky="w", padx=6)

        tk.Label(of, text="transformPoints scale:", anchor="w").grid(
            row=1, column=0, sticky="w", pady=2)
        tk.Entry(of, textvariable=self._scale_var, width=10).grid(row=1, column=1, sticky="w", padx=6)
        tk.Label(of, text="(0.001 = mm→m, 1.0 = already in metres)", fg="gray").grid(
            row=1, column=2, sticky="w")

        tk.Checkbutton(of, text="Parallel run", variable=self._parallel_var,
                       command=self._toggle_parallel).grid(row=2, column=0, sticky="w", pady=2)
        self._nprocs_label = tk.Label(of, text="MPI processes:", anchor="w")
        self._nprocs_label.grid(row=2, column=1, sticky="w", padx=6)
        self._nprocs_entry = tk.Entry(of, textvariable=self._nprocs_var, width=5)
        self._nprocs_entry.grid(row=2, column=2, sticky="w")
        self._toggle_parallel()   # set initial enable/disable state

        # ── Action buttons ─────────────────────────────────────────────────
        bf = tk.Frame(self, **PAD)
        bf.pack(fill="x", **PAD)

        tk.Button(bf, text="①  Scan Regions",
                  width=18, command=self._scan).pack(side="left", padx=(0, 8))
        tk.Button(bf, text="②  Deploy + Write Allrun",
                  width=26, **BTN_GO, command=self._deploy).pack(side="left")

        # ── Region table ───────────────────────────────────────────────────
        tf = tk.LabelFrame(self, text="Detected regions & materials", **PAD)
        tf.pack(fill="x", **PAD)

        cols = ("Region", "Type", "Material", "κ W/m·K", "ρ kg/m³", "Cp J/kg·K")
        widths = {"Region": 170, "Type": 52, "Material": 140,
                  "κ W/m·K": 72, "ρ kg/m³": 72, "Cp J/kg·K": 72}
        self._tree = ttk.Treeview(tf, columns=cols, show="headings", height=6)
        for col in cols:
            self._tree.heading(col, text=col)
            self._tree.column(col, width=widths.get(col, 80), anchor="w")
        self._tree.pack(fill="x")
        self._tree.tag_configure("fluid",   foreground="#0d47a1")
        self._tree.tag_configure("solid",   foreground="#4e342e")
        self._tree.tag_configure("unknown", foreground="#b71c1c")

        # ── Log ───────────────────────────────────────────────────────────
        lf = tk.LabelFrame(self, text="Log", **PAD)
        lf.pack(fill="both", expand=True, **PAD)
        self._log_widget = scrolledtext.ScrolledText(
            lf, state="disabled", height=6, bg=BG_LOG, fg=FG_LOG, font=FONT_MONO)
        self._log_widget.pack(fill="both", expand=True)

    def _toggle_parallel(self) -> None:
        state = "normal" if self._parallel_var.get() else "disabled"
        self._nprocs_entry.config(state=state)
        self._nprocs_label.config(state=state)

    def log(self, msg: str) -> None:
        self._log_widget.config(state="normal")
        self._log_widget.insert(tk.END, msg + "\n")
        self._log_widget.see(tk.END)
        self._log_widget.config(state="disabled")
        self.update_idletasks()

    def _scan(self) -> None:
        case_dir = self._case_var.get().strip()
        if not case_dir:
            messagebox.showerror("Error", "Select a case folder first.")
            return
        self.log(f"\n=== Scanning: {case_dir} ===")
        self._fluids, self._solids, self._material_map = \
            self._scanner.scan(case_dir, self.log)
        self._refresh_table()
        self.log(f"  Fluids : {self._fluids}")
        self.log(f"  Solids : {self._solids}")
        if not self._fluids and not self._solids:
            messagebox.showwarning("No regions",
                "No regions found.\n"
                "Run gmshToFoam → transformPoints → splitMeshRegions first.")

    def _refresh_table(self) -> None:
        for row in self._tree.get_children():
            self._tree.delete(row)
        for region in self._fluids + self._solids:
            rtype = "fluid" if region in self._fluids else "solid"
            mat   = self._material_map.get(region)
            if mat:
                tag  = rtype
                name = mat["matched_key"]
                kv   = str(mat.get("kappa")) if mat.get("kappa") else "varies"
                rv   = str(mat.get("rho"))   if mat.get("rho")   else "varies"
                cv   = str(mat.get("cp"))    if mat.get("cp")    else "varies"
            else:
                tag  = "unknown"
                name = "⚠ unknown"
                kv = rv = cv = "—"
            self._tree.insert("", "end",
                              values=(region, rtype, name, kv, rv, cv),
                              tags=(tag,))

    def _deploy(self) -> None:
        template_dir = self._template_var.get().strip()
        case_dir     = self._case_var.get().strip()

        if not template_dir or not case_dir:
            messagebox.showerror("Error", "Select both template and case folders.")
            return
        if not self._fluids and not self._solids:
            messagebox.showerror("Error", "Scan regions first.")
            return

        try:
            scale   = float(self._scale_var.get())
            n_procs = int(self._nprocs_var.get())
        except ValueError:
            messagebox.showerror("Error", "Scale and nprocs must be numbers.")
            return

        if not messagebox.askyesno("Confirm",
                f"Overwrite files in:\n{case_dir}\n\nProceed?"):
            return

        self.log("\n=== Deploying ===")
        try:
            self._fixer.fix_all(case_dir, self._fluids + self._solids, self.log)

            for r in self._fluids:
                self._deployer.deploy_region(
                    template_dir, case_dir, r, "fluid",
                    self._material_map.get(r), self.log)
            for r in self._solids:
                self._deployer.deploy_region(
                    template_dir, case_dir, r, "solid",
                    self._material_map.get(r), self.log)

            self._global.deploy(template_dir, case_dir,
                                self._fluids, self._solids, self.log)

            self._writer.write(
                case_dir     = case_dir,
                msh_file     = self._msh_var.get().strip(),
                template_dir = template_dir,
                fluids       = self._fluids,
                solids       = self._solids,
                scale        = scale,
                parallel     = self._parallel_var.get(),
                n_procs      = n_procs,
                log          = self.log,
            )

            self.log("\n✅  Deploy complete.")
            self.log("    Switch to the 'Pipeline' tab and click Run to launch Allrun.")

            messagebox.showinfo("Done",
                "Deploy complete.\n"
                "Switch to the Pipeline tab to run the simulation.")

        except Exception as exc:
            import traceback
            self.log(f"\n❌  FATAL: {exc}")
            self.log(traceback.format_exc())

    @property
    def case_dir(self) -> str:
        return self._case_var.get().strip()


# =============================================================================
# TAB 3 — Pipeline Runner
# =============================================================================

class PipelineTab(tk.Frame):
    """
    Launches Allrun as a subprocess and streams its output live.
    Shows per-step progress based on OpenFOAM's runApplication log lines.
    """

    # OpenFOAM runApplication writes "Running <command>" to stdout
    STEPS = [
        ("gmshToFoam",             "Convert .msh → OpenFOAM"),
        ("transformPoints",        "Scale units"),
        ("checkMesh",              "Check mesh quality"),
        ("splitMeshRegions",       "Split mesh regions"),
        ("apply_template",         "Deploy templates & materials"),
        ("changeDictionary",       "Apply boundary conditions"),
        ("chtMultiRegionSimpleFoam","Run CHT solver"),
    ]

    def __init__(self, parent: ttk.Notebook, deploy_tab: DeployTab):
        super().__init__(parent)
        self._deploy_tab = deploy_tab
        self._process: subprocess.Popen | None = None
        self._step_labels: list[tk.Label] = []
        self._build_ui()

    def _build_ui(self) -> None:
        # ── Step tracker ──────────────────────────────────────────────────
        sf = tk.LabelFrame(self, text="Pipeline steps", **PAD)
        sf.pack(fill="x", **PAD)

        for i, (_, label) in enumerate(self.STEPS):
            row = tk.Frame(sf)
            row.pack(fill="x", pady=1)
            indicator = tk.Label(row, text="○", width=2, font=("Courier", 12))
            indicator.pack(side="left")
            tk.Label(row, text=label, anchor="w").pack(side="left")
            self._step_labels.append(indicator)

        # ── Controls ──────────────────────────────────────────────────────
        cf = tk.Frame(self, **PAD)
        cf.pack(fill="x", **PAD)

        self._run_btn = tk.Button(cf, text="▶  Run Allrun",
                                  width=16, **BTN_GO, command=self._run)
        self._run_btn.pack(side="left", padx=(0, 8))

        self._stop_btn = tk.Button(cf, text="■  Stop",
                                   width=10, **BTN_WARN,
                                   state="disabled", command=self._stop)
        self._stop_btn.pack(side="left")

        self._status_var = tk.StringVar(value="Ready")
        tk.Label(cf, textvariable=self._status_var, anchor="w").pack(
            side="left", padx=12)

        # ── Live log ───────────────────────────────────────────────────────
        lf = tk.LabelFrame(self, text="Allrun output", **PAD)
        lf.pack(fill="both", expand=True, **PAD)
        self._log_widget = scrolledtext.ScrolledText(
            lf, state="disabled", bg=BG_LOG, fg=FG_LOG, font=FONT_MONO)
        self._log_widget.pack(fill="both", expand=True)

    def _set_step(self, idx: int, done: bool) -> None:
        """Update step indicator: ● = done, ◐ = running, ○ = pending."""
        for i, lbl in enumerate(self._step_labels):
            if i < idx:
                lbl.config(text="●", fg="#00c853")
            elif i == idx:
                lbl.config(text="◐", fg="#ffd600")
            else:
                lbl.config(text="○", fg="gray")

    def _detect_step(self, line: str) -> int | None:
        """Return step index if this log line announces a new step."""
        line_lower = line.lower()
        for i, (cmd, _) in enumerate(self.STEPS):
            if cmd.lower() in line_lower and "running" in line_lower:
                return i
        return None

    def _append_log(self, text: str) -> None:
        self._log_widget.config(state="normal")
        self._log_widget.insert(tk.END, text)
        self._log_widget.see(tk.END)
        self._log_widget.config(state="disabled")

    def _run(self) -> None:
        case_dir = self._deploy_tab.case_dir
        if not case_dir:
            messagebox.showerror("Error", "Set the case folder in the Deploy tab first.")
            return

        allrun = os.path.join(case_dir, "Allrun")
        if not os.path.exists(allrun):
            messagebox.showerror("Error",
                f"Allrun not found in:\n{case_dir}\n\nRun 'Deploy + Write Allrun' first.")
            return

        # Reset step indicators
        for lbl in self._step_labels:
            lbl.config(text="○", fg="gray")

        self._run_btn.config(state="disabled")
        self._stop_btn.config(state="normal")
        self._status_var.set("Running…")

        self._process = subprocess.Popen(
            ["/bin/sh", allrun],
            cwd=case_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        threading.Thread(target=self._stream, daemon=True).start()

    def _stream(self) -> None:
        """Read subprocess stdout line-by-line and update UI via after()."""
        current_step = 0
        for line in self._process.stdout:
            step = self._detect_step(line)
            if step is not None:
                current_step = step
                self.after(0, self._set_step, current_step, False)
            self.after(0, self._append_log, line)

        rc = self._process.wait()
        self.after(0, self._on_finished, rc, current_step)

    def _on_finished(self, rc: int, last_step: int) -> None:
        if rc == 0:
            for lbl in self._step_labels:
                lbl.config(text="●", fg="#00c853")
            self._status_var.set("✅  Simulation complete")
            messagebox.showinfo("Done", "Allrun finished successfully.\nPost-process with paraFoam.")
        else:
            self._set_step(last_step, False)
            self._status_var.set(f"❌  Failed (exit code {rc})")
            messagebox.showerror("Failed",
                f"Allrun exited with code {rc}.\nCheck the log for the error.")

        self._run_btn.config(state="normal")
        self._stop_btn.config(state="disabled")
        self._process = None

    def _stop(self) -> None:
        if self._process:
            self._process.terminate()
            self._status_var.set("Stopped by user")
            self._stop_btn.config(state="disabled")
            self._run_btn.config(state="normal")


# =============================================================================
# ROOT APPLICATION
# =============================================================================

class CHTApp:
    """
    Tabbed root application.  Shared state:
      - template_var  flows from BuilderTab output to DeployTab input
      - deploy_tab    reference passed to PipelineTab for case_dir
    """

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("OpenFOAM CHT Toolchain")
        self.root.geometry("820x680")
        self.root.resizable(True, True)

        shared_template = tk.StringVar()

        nb = ttk.Notebook(root)
        nb.pack(fill="both", expand=True)

        tab1 = BuilderTab(nb, shared_template)
        nb.add(tab1, text="  ① Build Template  ")

        tab2 = DeployTab(nb, shared_template)
        nb.add(tab2, text="  ② Deploy & Configure  ")

        tab3 = PipelineTab(nb, tab2)
        nb.add(tab3, text="  ③ Run Pipeline  ")


# =============================================================================
# ENTRY POINT (when run directly for testing)
# =============================================================================

if __name__ == "__main__":
    root = tk.Tk()
    CHTApp(root)
    root.mainloop()
