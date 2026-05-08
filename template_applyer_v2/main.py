"""
main.py — Single entry point for the OpenFOAM CHT Toolchain.

GUI mode  (default):
    python main.py

CLI modes (for scripting / CI pipelines):
    # Build a template from a tutorial case
    python main.py build-template \\
        --source $FOAM_TUTORIALS/heatTransfer/chtMultiRegionSimpleFoam/multiRegionHeater \\
        --output ~/templates/myTemplate \\
        --fluid  air  --solid  heatsink pcb soc

    # Deploy template + write Allrun/Allclean  (run AFTER splitMeshRegions)
    python main.py deploy \\
        --template ~/templates/myTemplate \\
        --case     ~/cases/myCHTCase \\
        --msh      case.msh \\
        --scale    0.001

    # Full pipeline in one shot (build-template + deploy, for CI)
    python main.py full \\
        --source   $FOAM_TUTORIALS/... \\
        --output   ~/templates/myTemplate \\
        --case     ~/cases/myCHTCase \\
        --msh      case.msh

Module map
----------
    main.py               ← you are here (CLI routing + GUI launch)
    gui.py                ← tabbed Tkinter UI (3 tabs, no business logic)
    template_builder.py   ← Tab 1: tutorial case → reusable template
    region_scanner.py     ← Tab 2: discover regions from splitMeshRegions output
    boundary_fixer.py     ← Tab 2: polyMesh/boundary patch → wall
    template_deployer.py  ← Tab 2: copy files + substitute placeholders + thermo
    allrun_writer.py      ← Tab 2: generate Allrun / Allclean scripts
    material_db.py        ← shared: thermophysical property lookup
"""

import sys
import argparse


# =============================================================================
# CLI HANDLERS
# =============================================================================

def _cmd_build_template(args) -> int:
    from template_builder import TemplateBuilder, detect_tutorial_regions

    log = print

    fluids = args.fluid or []
    solids = args.solid or []

    if not fluids or not solids:
        log("Auto-detecting regions in source case...")
        fluids, solids = detect_tutorial_regions(args.source, log)

    if not fluids and not solids:
        log("ERROR: No regions found. Use --fluid / --solid to specify them.")
        return 1

    builder = TemplateBuilder(args.source, args.output, log)
    ok = builder.build(fluids, solids)
    return 0 if ok else 1


def _cmd_deploy(args) -> int:
    from region_scanner    import RegionScanner
    from boundary_fixer    import BoundaryFixer
    from template_deployer import TemplateDeployer, GlobalDeployer
    from allrun_writer     import AllrunWriter

    log = print

    log(f"\n=== CHT Deployer (CLI) ===")
    log(f"Template : {args.template}")
    log(f"Case     : {args.case}")

    fluids, solids, material_map = RegionScanner().scan(args.case, log)

    if not fluids and not solids:
        log("ERROR: No regions found. Run splitMeshRegions -cellZones -overwrite first.")
        return 1

    log(f"\nFluids : {fluids}")
    log(f"Solids : {solids}")

    try:
        BoundaryFixer().fix_all(args.case, fluids + solids, log)

        deployer = TemplateDeployer()
        for r in fluids:
            deployer.deploy_region(args.template, args.case, r, "fluid",
                                   material_map.get(r), log)
        for r in solids:
            deployer.deploy_region(args.template, args.case, r, "solid",
                                   material_map.get(r), log)

        GlobalDeployer().deploy(args.template, args.case, fluids, solids, log)

        AllrunWriter().write(
            case_dir     = args.case,
            msh_file     = args.msh,
            template_dir = args.template,
            fluids       = fluids,
            solids       = solids,
            scale        = args.scale,
            parallel     = args.parallel,
            n_procs      = args.nprocs,
            log          = log,
        )

        log("\n✅  Deploy complete. Run ./Allrun to start the simulation.")
        return 0

    except Exception as exc:
        import traceback
        log(f"\n❌  FATAL: {exc}")
        log(traceback.format_exc())
        return 1


def _cmd_full(args) -> int:
    """Build template then deploy — convenience for CI."""
    rc = _cmd_build_template(args)
    if rc != 0:
        return rc
    args.template = args.output   # output of build = input of deploy
    return _cmd_deploy(args)


# =============================================================================
# GUI LAUNCHER
# =============================================================================

def _run_gui() -> None:
    import tkinter as tk
    from gui import CHTApp
    root = tk.Tk()
    CHTApp(root)
    root.mainloop()


# =============================================================================
# ARGUMENT PARSER
# =============================================================================

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="OpenFOAM CHT Toolchain — GUI or CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                                   # launch GUI (default)

  python main.py build-template \\
      --source $FOAM_TUTORIALS/heatTransfer/chtMultiRegionSimpleFoam/multiRegionHeater \\
      --output ~/templates/heater \\
      --fluid air --solid heatsink pcb soc

  python main.py deploy \\
      --template ~/templates/heater \\
      --case     ~/cases/myCase \\
      --msh      case.msh \\
      --scale    0.001

  python main.py full \\
      --source $FOAM_TUTORIALS/heatTransfer/chtMultiRegionSimpleFoam/multiRegionHeater \\
      --output ~/templates/heater \\
      --case   ~/cases/myCase \\
      --msh    case.msh
        """,
    )

    sub = parser.add_subparsers(dest="command")

    # ── build-template ────────────────────────────────────────────────────
    p_build = sub.add_parser("build-template",
        help="Convert a tutorial case into a reusable template folder")
    p_build.add_argument("--source", required=True, metavar="DIR",
        help="Source OpenFOAM tutorial case directory")
    p_build.add_argument("--output", required=True, metavar="DIR",
        help="Output template directory (will be created/overwritten)")
    p_build.add_argument("--fluid", nargs="+", metavar="REGION",
        help="Fluid region folder names (blank = auto-detect)")
    p_build.add_argument("--solid", nargs="+", metavar="REGION",
        help="Solid region folder names (blank = auto-detect)")

    # ── deploy ────────────────────────────────────────────────────────────
    p_deploy = sub.add_parser("deploy",
        help="Deploy template to a case after splitMeshRegions")
    p_deploy.add_argument("--template", required=True, metavar="DIR",
        help="Template folder (built by build-template)")
    p_deploy.add_argument("--case", required=True, metavar="DIR",
        help="OpenFOAM case folder (after splitMeshRegions)")
    p_deploy.add_argument("--msh", default="case.msh", metavar="FILE",
        help="Mesh filename relative to case root  (default: case.msh)")
    p_deploy.add_argument("--scale", type=float, default=0.001, metavar="F",
        help="transformPoints scale factor  (default: 0.001 = mm→m)")
    p_deploy.add_argument("--parallel", action="store_true",
        help="Write Allrun for MPI parallel run")
    p_deploy.add_argument("--nprocs", type=int, default=4, metavar="N",
        help="Number of MPI processes  (default: 4)")

    # ── full ──────────────────────────────────────────────────────────────
    p_full = sub.add_parser("full",
        help="build-template + deploy in one shot (CI convenience)")
    p_full.add_argument("--source",   required=True, metavar="DIR")
    p_full.add_argument("--output",   required=True, metavar="DIR",
        help="Template output dir (also used as deploy input)")
    p_full.add_argument("--case",     required=True, metavar="DIR")
    p_full.add_argument("--msh",      default="case.msh", metavar="FILE")
    p_full.add_argument("--scale",    type=float, default=0.001)
    p_full.add_argument("--fluid",    nargs="+", metavar="REGION")
    p_full.add_argument("--solid",    nargs="+", metavar="REGION")
    p_full.add_argument("--parallel", action="store_true")
    p_full.add_argument("--nprocs",   type=int, default=4)

    return parser


# =============================================================================
# ENTRY POINT
# =============================================================================

def main() -> None:
    parser = _build_parser()
    args   = parser.parse_args()

    if args.command is None:
        _run_gui()
        return

    dispatch = {
        "build-template": _cmd_build_template,
        "deploy":         _cmd_deploy,
        "full":           _cmd_full,
    }
    sys.exit(dispatch[args.command](args))


if __name__ == "__main__":
    main()
