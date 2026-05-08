"""
template_deployer.py — Copies OpenFOAM fluid/solid template files into a case.

Template substitution tokens
-----------------------------
  ".*_to_.*"           Coupled BC wildcard → "<region>_to_.*"
  LOCATION_PLACEHOLDER → folder/region  (e.g. "constant/air_normal")
  FLUID_PLACEHOLDER    → region name
  SOLID_PLACEHOLDER    → region name

thermophysicalProperties override
-----------------------------------
After copying, if a material match exists in material_db, the module
overwrites constant/<region>/thermophysicalProperties with the DB content.
This replaces the placeholder/generic template values with real properties.

Template folder structure expected:
    <template_dir>/
        fluid/
            0/          ← T, U, p, p_rgh, k, epsilon, nut, alphat
            constant/   ← thermophysicalProperties, turbulenceProperties, MRFProperties
            system/     ← fvSchemes, fvSolution, changeDictionaryDict, decomposeParDict
        solid/
            0/          ← T  (NOT p — solids have no pressure solve)
            constant/   ← thermophysicalProperties
            system/     ← fvSchemes, fvSolution, fvOptions, changeDictionaryDict
        global/
            constant/   ← g, regionProperties
            system/     ← controlDict, decomposeParDict, fvSchemes, fvSolution, ...
"""

import os


class TemplateDeployer:
    """
    Deploys one region (fluid or solid) from the template directory.
    """

    @staticmethod
    def _resolve_zero_folder(template_dir: str, region_type: str) -> str:
        """
        The template builder always writes to 0/ but an existing template
        may still have 0.orig/ if it was copied directly from a tutorial.
        Check which one exists and use it as the source.
        Always deploy INTO case 0/<region>/ regardless of source name.
        """
        zero     = os.path.join(template_dir, region_type, "0")
        zero_orig = os.path.join(template_dir, region_type, "0.orig")
        if os.path.exists(zero):
            return "0"
        if os.path.exists(zero_orig):
            return "0.orig"
        return "0"   # fallback — _deploy_folder will warn if missing

    def deploy_region(
        self,
        template_dir: str,
        case_dir: str,
        region_name: str,
        region_type: str,          # "fluid" | "solid"
        material: dict | None,
        log,
    ) -> None:
        log(f"\n  [{region_type:6s}] {region_name}")
        if material:
            log(f"    Material  : {material['description']}  (key='{material['matched_key']}')")
        else:
            log(f"    Material  : ⚠ no DB match — template file kept as-is")

        # Resolve whether template stores initial fields in 0/ or 0.orig/
        zero_src = self._resolve_zero_folder(template_dir, region_type)
        if zero_src == "0.orig":
            log(f"    Note      : template has 0.orig/ — deploying into case 0/{region_name}/")

        # src_folder → dest_folder mapping
        # Source name may vary (0 or 0.orig); destination is ALWAYS 0/
        folder_map = {zero_src: "0", "constant": "constant", "system": "system"}

        for src_folder, dest_folder in folder_map.items():
            self._deploy_folder(
                template_dir, case_dir,
                region_name, region_type,
                src_folder, dest_folder, log
            )

        # Auto-write thermophysicalProperties from DB after all template files are placed
        if material:
            self._write_thermo(case_dir, region_name, material, log)

    # ── Internal helpers ──────────────────────────────────────────────────

    def _deploy_folder(
        self,
        template_dir: str,
        case_dir: str,
        region_name: str,
        region_type: str,
        src_folder: str,       # folder name inside the template (may be "0.orig")
        dest_folder: str,      # folder name in the case     (always "0")
        log,
    ) -> None:
        src_dir  = os.path.join(template_dir, region_type, src_folder)
        dest_dir = os.path.join(case_dir, dest_folder, region_name)

        if not os.path.exists(src_dir):
            log(f"    [Warning] Template missing: {src_dir} — skipping")
            return

        os.makedirs(dest_dir, exist_ok=True)

        for file_name in os.listdir(src_dir):
            src_file  = os.path.join(src_dir, file_name)
            dest_file = os.path.join(dest_dir, file_name)
            if not os.path.isfile(src_file):
                continue

            content = self._read(src_file)
            content = self._substitute(content, region_name, dest_folder, log, file_name)
            self._write(dest_file, content)

    @staticmethod
    def _substitute(
        content: str,
        region_name: str,
        folder: str,
        log,
        file_name: str,
    ) -> str:
        # 1. Coupled BC wildcard
        if '".*_to_.*"' in content:
            replacement = f'"{region_name}_to_.*"'
            content = content.replace('".*_to_.*"', replacement)
            log(f"    [{file_name}] coupled BC → {replacement}")

        # 2. Location
        content = content.replace(
            "LOCATION_PLACEHOLDER", f"{folder}/{region_name}"
        )

        # 3. Region name (same token for both fluid and solid templates)
        content = content.replace("FLUID_PLACEHOLDER", region_name)
        content = content.replace("SOLID_PLACEHOLDER", region_name)

        return content

    @staticmethod
    def _write_thermo(
        case_dir: str,
        region_name: str,
        material: dict,
        log,
    ) -> None:
        thermo_path = os.path.join(
            case_dir, "constant", region_name, "thermophysicalProperties"
        )
        with open(thermo_path, "w", encoding="utf-8") as f:
            f.write(material["content"])
        log(f"    [thermophysicalProperties] written from material DB")

    @staticmethod
    def _read(path: str) -> str:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    @staticmethod
    def _write(path: str, content: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)


class GlobalDeployer:
    """
    Copies global template files (controlDict, regionProperties, g, etc.)
    and substitutes fluid/solid region name lists.
    """

    def deploy(
        self,
        template_dir: str,
        case_dir: str,
        fluids: list[str],
        solids: list[str],
        log,
    ) -> None:
        log("\n  Deploying global files...")

        for folder in ("constant", "system"):
            src_dir     = os.path.join(template_dir, "global", folder)
            dest_folder = os.path.join(case_dir, folder)

            if not os.path.exists(src_dir):
                log(f"  [Warning] Global template missing: {src_dir}")
                continue

            os.makedirs(dest_folder, exist_ok=True)

            for file_name in os.listdir(src_dir):
                src_file  = os.path.join(src_dir, file_name)
                dest_file = os.path.join(dest_folder, file_name)
                if not os.path.isfile(src_file):
                    continue

                with open(src_file, "r", encoding="utf-8") as f:
                    content = f.read()

                if file_name == "regionProperties":
                    content = content.replace("FLUID_PLACEHOLDER", " ".join(fluids))
                    content = content.replace("SOLID_PLACEHOLDER", " ".join(solids))

                content = content.replace("LOCATION_PLACEHOLDER", folder)

                with open(dest_file, "w", encoding="utf-8") as f:
                    f.write(content)

                log(f"    Written: {folder}/{file_name}")
