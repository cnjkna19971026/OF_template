"""
template_builder.py — Scaffolds a fluid/solid/global template folder from an
existing OpenFOAM tutorial case.

Problem it solves
-----------------
Every new CHT simulation currently requires manually:
  1. Finding a tutorial case (e.g. $FOAM_TUTORIALS/heatTransfer/chtMultiRegionSimpleFoam/...)
  2. Copying it
  3. Manually splitting files into fluid/, solid/, global/ folders
  4. Manually inserting FLUID_PLACEHOLDER / SOLID_PLACEHOLDER / ".*_to_.*" tokens

This tool automates all four steps.

How it works
------------
Given a source tutorial case that already has region sub-folders under
0/, constant/, system/ (i.e. after splitMeshRegions was run on the tutorial),
the builder:

  1. Scans 0.orig/, constant/, system/ for region subdirectories
  2. Classifies each subdirectory as fluid, solid, or global
  3. Copies files into the output template structure, injecting placeholders
  4. Writes a README explaining how to customise the template

Output template structure
-------------------------
<output>/
  fluid/
    0/        ← T, U, p, p_rgh, k, epsilon, nut, alphat  (with FLUID_PLACEHOLDER)
    constant/ ← thermophysicalProperties, turbulenceProperties, MRFProperties
    system/   ← fvSchemes, fvSolution, changeDictionaryDict, decomposeParDict
  solid/
    0/        ← T  (with SOLID_PLACEHOLDER)
    constant/ ← thermophysicalProperties
    system/   ← fvSchemes, fvSolution, fvOptions, changeDictionaryDict
  global/
    constant/ ← g, regionProperties
    system/   ← controlDict, decomposeParDict, fvSchemes, fvSolution, ...

Usage
-----
  python template_builder.py                        # GUI mode
  python template_builder.py --cli \\
      --source /path/to/tutorial \\
      --output /path/to/new/template \\
      --fluid  air                   \\
      --solid  heatsink pcb soc      \\
      --global-files g regionProperties controlDict decomposeParDict
"""

import os
import re
import shutil
import argparse

from material_db import FLUID_KEYWORDS, SOLID_KEYWORDS


# Files that belong in global/system regardless of region
GLOBAL_SYSTEM_FILES = {
    "controlDict", "decomposeParDict", "fvSchemes", "fvSolution",
    "meshQualityDict", "blockMeshDict", "snappyHexMeshDict",
    "createBafflesDict", "surfaceFeatureExtractDict",
}

GLOBAL_CONSTANT_FILES = {
    "g", "regionProperties", "transportProperties",
}

# Field files that are fluid-only (no pressure solve in solids)
FLUID_ONLY_FIELDS = {"U", "p_rgh", "k", "epsilon", "omega", "nut", "alphat"}

# Placeholder tokens inserted into template files
TOKEN_FLUID    = "FLUID_PLACEHOLDER"
TOKEN_SOLID    = "SOLID_PLACEHOLDER"
TOKEN_LOCATION = "LOCATION_PLACEHOLDER"
TOKEN_COUPLED  = '".*_to_.*"'


# =============================================================================
# CORE BUILDER
# =============================================================================

class TemplateBuilder:
    """
    Converts an existing OpenFOAM CHT tutorial case into a reusable template.
    """

    def __init__(self, source_dir: str, output_dir: str, log):
        self.source  = source_dir
        self.output  = output_dir
        self.log     = log

    def build(
        self,
        fluid_regions: list[str],
        solid_regions: list[str],
    ) -> bool:
        """
        Main entry point.  fluid_regions / solid_regions are the known
        region folder names found in the source tutorial case.

        Returns True on success.
        """
        self.log(f"\n=== Building template ===")
        self.log(f"  Source : {self.source}")
        self.log(f"  Output : {self.output}")
        self.log(f"  Fluids : {fluid_regions}")
        self.log(f"  Solids : {solid_regions}")

        if os.path.exists(self.output):
            shutil.rmtree(self.output)
        os.makedirs(self.output)

        try:
            # One representative region drives the template for each type
            if fluid_regions:
                self._build_region_template("fluid", fluid_regions[0])
            if solid_regions:
                self._build_region_template("solid", solid_regions[0])
            self._build_global_template(fluid_regions + solid_regions)
            self._write_readme(fluid_regions, solid_regions)
            self.log("\n✅  Template built successfully.")
            return True
        except Exception as exc:
            import traceback
            self.log(f"\n❌  Build failed: {exc}")
            self.log(traceback.format_exc())
            return False

    # ── Region template (fluid or solid) ──────────────────────────────────

    def _build_region_template(self, rtype: str, source_region: str) -> None:
        self.log(f"\n  [{rtype}] using source region '{source_region}'")

        for folder in ("0.orig", "constant", "system"):
            src_dir  = os.path.join(self.source, folder, source_region)
            dest_dir = os.path.join(self.output, rtype, folder)

            if not os.path.exists(src_dir):
                # Try top-level folder (some tutorials don't use sub-regions)
                src_dir = os.path.join(self.source, folder)

            if not os.path.exists(src_dir):
                self.log(f"    [Warning] Source not found: {src_dir}")
                continue

            os.makedirs(dest_dir, exist_ok=True)

            for fname in os.listdir(src_dir):
                fpath = os.path.join(src_dir, fname)
                if not os.path.isfile(fpath):
                    continue

                # Skip fluid-only fields when building solid template
                if rtype == "solid" and folder == "0" and fname in FLUID_ONLY_FIELDS:
                    self.log(f"    [skip] {folder}/{fname} (fluid-only field)")
                    continue

                content = self._read(fpath)
                content = self._inject_placeholders(content, source_region, rtype, folder)
                dest_file = os.path.join(dest_dir, fname)
                self._write(dest_file, content)
                self.log(f"    {folder}/{fname}")

    # ── Global template ────────────────────────────────────────────────────

    def _build_global_template(self, all_regions: list[str]) -> None:
        self.log("\n  [global]")

        for folder, target_files in (
            ("constant", GLOBAL_CONSTANT_FILES),
            ("system",   GLOBAL_SYSTEM_FILES),
        ):
            src_dir  = os.path.join(self.source, folder)
            dest_dir = os.path.join(self.output, "global", folder)

            if not os.path.exists(src_dir):
                continue

            os.makedirs(dest_dir, exist_ok=True)

            for fname in os.listdir(src_dir):
                fpath = os.path.join(src_dir, fname)
                if not os.path.isfile(fpath):
                    continue
                if fname not in target_files:
                    continue

                content = self._read(fpath)

                # regionProperties: replace actual region lists with placeholders
                if fname == "regionProperties":
                    content = self._replace_region_list(content, all_regions, "fluid")
                    content = self._replace_region_list(content, all_regions, "solid")

                content = content.replace("LOCATION_PLACEHOLDER", folder)
                dest_file = os.path.join(dest_dir, fname)
                self._write(dest_file, content)
                self.log(f"    {folder}/{fname}")

    # ── Placeholder injection ──────────────────────────────────────────────

    def _inject_placeholders(
        self,
        content: str,
        region_name: str,
        rtype: str,
        folder: str,
    ) -> str:
        token = TOKEN_FLUID if rtype == "fluid" else TOKEN_SOLID

        # 1. Replace region name with generic placeholder
        #    Use word boundary so "air_normal" doesn't clobber "airT"
        content = re.sub(
            rf'\b{re.escape(region_name)}\b',
            token,
            content,
        )

        # 2. Replace coupled interface patch names with wildcard
        #    e.g. "air_to_heatsink" → ".*_to_.*"
        content = re.sub(
            r'"[^"]+_to_[^"]+"',
            TOKEN_COUPLED,
            content,
        )

        # 3. Location field in FoamFile header
        content = re.sub(
            r'(location\s+"?)([^";]+)("?;)',
            lambda m: f'{m.group(1)}{TOKEN_LOCATION}{m.group(3)}',
            content,
        )

        return content

    @staticmethod
    def _replace_region_list(
        content: str, all_regions: list[str], rtype: str
    ) -> str:
        """
        In regionProperties, replace actual region name lists with placeholders.
        e.g.  fluid  ( air );   →   fluid  ( FLUID_PLACEHOLDER );
        """
        token = TOKEN_FLUID if rtype == "fluid" else TOKEN_SOLID
        # Match:  fluid  (  air_normal  );
        pattern = rf'({rtype}\s*\(\s*)([^)]+)(\s*\);)'
        return re.sub(pattern, rf'\g<1>{token}\g<3>', content)

    # ── File I/O ──────────────────────────────────────────────────────────

    @staticmethod
    def _read(path: str) -> str:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except UnicodeDecodeError:
            # Binary file (unlikely in OF cases but safe)
            return ""

    @staticmethod
    def _write(path: str, content: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    # ── README ────────────────────────────────────────────────────────────

    def _write_readme(
        self, fluid_regions: list[str], solid_regions: list[str]
    ) -> None:
        readme = f"""\
# CHT Template — generated by template_builder.py
# Source: {self.source}

## Placeholder tokens
  FLUID_PLACEHOLDER     — replaced with the actual fluid region name at deploy time
  SOLID_PLACEHOLDER     — replaced with the actual solid region name at deploy time
  LOCATION_PLACEHOLDER  — replaced with folder/region  (e.g. constant/air_normal)
  ".*_to_.*"            — replaced with "<region>_to_.*"  for coupled BC wildcard

## Original source regions
  Fluid : {fluid_regions}
  Solid : {solid_regions}

## Usage
  1. Edit material properties in fluid/constant/thermophysicalProperties
     and solid/constant/thermophysicalProperties if needed.
     (apply_template.py will override these automatically from material_db.py
      if your region folder names match a known material keyword.)

  2. Run apply_template.py and point it at:
       Template folder : this directory
       Case folder     : your gmshToFoam case after splitMeshRegions

## Directory structure
  fluid/   0/  constant/  system/
  solid/   0/  constant/  system/
  global/  constant/  system/
"""
        self._write(os.path.join(self.output, "README.md"), readme)
        self.log("    README.md")


# =============================================================================
# REGION DETECTOR  (scans tutorial case to find region sub-folders)
# =============================================================================

def detect_tutorial_regions(source_dir: str, log) -> tuple[list[str], list[str]]:
    """
    Auto-detect fluid and solid region folders in a tutorial case.
    Looks for sub-directories under 0/ or constant/ that look like regions
    (contain field files or a polyMesh).
    """
    fluids, solids = [], []

    for folder in ("0.orig", "constant" ,"system"):
        folder_path = os.path.join(source_dir, folder)
        if not os.path.exists(folder_path):
            continue

        for item in os.listdir(folder_path):
            item_path = os.path.join(folder_path, item)
            if not os.path.isdir(item_path):
                continue
            # Skip non-region folders
            if item in ("polyMesh", "triSurface", "extendedFeatureEdgeMesh"):
                continue

            name_lower = item.lower()
            tokens = re.split(r"[_\-]", name_lower)

            if any(t in FLUID_KEYWORDS for t in tokens) or \
               any(kw in name_lower for kw in FLUID_KEYWORDS):
                if item not in fluids:
                    fluids.append(item)
                    log(f"  [fluid] {item}")
            else:
                if item not in solids:
                    solids.append(item)
                    log(f"  [solid] {item}")
        break   # Only need to scan one folder

    return fluids, solids


# =============================================================================
# CLI
# =============================================================================

def _run_cli(args) -> int:
    def log(msg): print(msg)

    log(f"\n=== Template Builder (CLI) ===")
    log(f"Source: {args.source}")

    if args.fluid or args.solid:
        fluids = args.fluid or []
        solids = args.solid or []
    else:
        log("\nAuto-detecting regions...")
        fluids, solids = detect_tutorial_regions(args.source, log)

    if not fluids and not solids:
        log("ERROR: No regions detected. Use --fluid / --solid to specify them.")
        return 1

    builder = TemplateBuilder(args.source, args.output, log)
    ok = builder.build(fluids, solids)
    return 0 if ok else 1


# =============================================================================
# GUI
# =============================================================================

def _run_gui() -> None:
    import tkinter as tk
    from tkinter import filedialog, messagebox, scrolledtext

    root = tk.Tk()
    root.title("CHT Template Builder")
    root.geometry("700x520")
    root.resizable(True, True)

    source_var = tk.StringVar()
    output_var = tk.StringVar()
    fluid_var  = tk.StringVar()
    solid_var  = tk.StringVar()

    # ── Path selectors ────────────────────────────────────────────────────
    top = tk.Frame(root, padx=12, pady=10)
    top.pack(fill="x")

    def browse(var, title):
        d = filedialog.askdirectory(title=title)
        if d:
            var.set(d)

    rows = [
        ("Tutorial case dir:", source_var, "Select source tutorial case"),
        ("Output template dir:", output_var, "Select output folder for template"),
    ]
    for i, (label, var, title) in enumerate(rows):
        tk.Label(top, text=label, width=18, anchor="w").grid(row=i, column=0, pady=4)
        tk.Entry(top, textvariable=var, width=50).grid(row=i, column=1, pady=4, padx=4)
        tk.Button(top, text="Browse…",
                  command=lambda v=var, t=title: browse(v, t)).grid(row=i, column=2, pady=4)

    # ── Region override fields ────────────────────────────────────────────
    mid = tk.Frame(root, padx=12, pady=4)
    mid.pack(fill="x")

    tk.Label(mid, text="Fluid regions (space-separated, blank = auto-detect):",
             anchor="w").pack(fill="x")
    tk.Entry(mid, textvariable=fluid_var, width=70).pack(fill="x", pady=2)
    tk.Label(mid, text="Solid regions (space-separated, blank = auto-detect):",
             anchor="w").pack(fill="x", pady=(6, 0))
    tk.Entry(mid, textvariable=solid_var, width=70).pack(fill="x", pady=2)

    # ── Log ───────────────────────────────────────────────────────────────
    log_frame = tk.LabelFrame(root, text="Log", padx=8, pady=4)
    log_frame.pack(fill="both", expand=True, padx=12, pady=8)
    log_widget = scrolledtext.ScrolledText(
        log_frame, height=10, state="disabled",
        bg="#111", fg="#00e676", font=("Courier", 10)
    )
    log_widget.pack(fill="both", expand=True)

    def log(msg):
        log_widget.config(state="normal")
        log_widget.insert(tk.END, msg + "\n")
        log_widget.see(tk.END)
        log_widget.config(state="disabled")
        root.update_idletasks()

    # ── Action ───────────────────────────────────────────────────────────
    def run():
        source = source_var.get().strip()
        output = output_var.get().strip()
        if not source or not output:
            messagebox.showerror("Error", "Select both source and output folders.")
            return

        fluids = fluid_var.get().split() or None
        solids = solid_var.get().split() or None

        if not fluids or not solids:
            log("\nAuto-detecting regions in source case...")
            af, as_ = detect_tutorial_regions(source, log)
            fluids = fluids or af
            solids = solids or as_

        builder = TemplateBuilder(source, output, log)
        builder.build(fluids or [], solids or [])

    btn_frame = tk.Frame(root, padx=12, pady=4)
    btn_frame.pack(fill="x")
    tk.Button(
        btn_frame, text="Build Template",
        bg="#1a237e", fg="white", font=("", 10, "bold"),
        width=22, command=run
    ).pack(side="left")

    root.mainloop()


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CHT Template Builder")
    parser.add_argument("--cli",    action="store_true")
    parser.add_argument("--source", metavar="DIR")
    parser.add_argument("--output", metavar="DIR")
    parser.add_argument("--fluid",  nargs="+", metavar="REGION")
    parser.add_argument("--solid",  nargs="+", metavar="REGION")
    args = parser.parse_args()

    if args.cli:
        if not args.source or not args.output:
            parser.error("--cli requires --source and --output")
        import sys
        sys.exit(_run_cli(args))
    else:
        _run_gui()
