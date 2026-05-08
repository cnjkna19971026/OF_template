"""
main.py — Entry point for the OpenFOAM CHT Template Deployer.

GUI mode (default):
    python main.py

CLI mode (for scripting / CI):
    python main.py --cli --template /path/to/template --case /path/to/case

The CLI mode runs the full pipeline (scan → fix → deploy) non-interactively
and exits with code 0 on success or 1 on failure.
"""

import sys
import argparse

from region_scanner import RegionScanner
from boundary_fixer import BoundaryFixer
from template_deployer import TemplateDeployer, GlobalDeployer


def _run_cli(template_dir: str, case_dir: str) -> int:
    """
    Headless pipeline for scripting.
    Returns 0 on success, 1 on failure.
    """
    def log(msg: str) -> None:
        print(msg)

    scanner  = RegionScanner()
    fixer    = BoundaryFixer()
    deployer = TemplateDeployer()
    globdep  = GlobalDeployer()

    log(f"\n=== CHT Deployer (CLI) ===")
    log(f"Template : {template_dir}")
    log(f"Case     : {case_dir}\n")

    fluids, solids, material_map = scanner.scan(case_dir, log)

    if not fluids and not solids:
        log("ERROR: No regions found. Aborting.")
        return 1

    log(f"\nFluids : {fluids}")
    log(f"Solids : {solids}\n")

    try:
        fixer.fix_all(case_dir, fluids + solids, log)

        for region in fluids:
            deployer.deploy_region(
                template_dir, case_dir, region, "fluid",
                material_map.get(region), log
            )
        for region in solids:
            deployer.deploy_region(
                template_dir, case_dir, region, "solid",
                material_map.get(region), log
            )

        globdep.deploy(template_dir, case_dir, fluids, solids, log)

        log("\n✅  Done. Case is ready for chtMultiRegionSimpleFoam.")
        return 0

    except Exception as exc:
        import traceback
        log(f"\n❌  FATAL: {exc}")
        log(traceback.format_exc())
        return 1


def _run_gui() -> None:
    import tkinter as tk
    from gui import DeployerApp

    root = tk.Tk()
    DeployerApp(root)
    root.mainloop()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="OpenFOAM CHT Template Deployer"
    )
    parser.add_argument(
        "--cli", action="store_true",
        help="Run without GUI (requires --template and --case)"
    )
    parser.add_argument("--template", metavar="DIR", help="Template folder path")
    parser.add_argument("--case",     metavar="DIR", help="OpenFOAM case folder path")
    args = parser.parse_args()

    if args.cli:
        if not args.template or not args.case:
            parser.error("--cli requires both --template and --case")
        sys.exit(_run_cli(args.template, args.case))
    else:
        _run_gui()


if __name__ == "__main__":
    main()
