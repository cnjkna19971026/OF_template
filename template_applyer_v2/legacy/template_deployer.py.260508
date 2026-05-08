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

        for folder in ("0", "constant", "system"):
            self._deploy_folder(
                template_dir, case_dir,
                region_name, region_type, folder, log
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
        folder: str,
        log,
    ) -> None:
        src_dir  = os.path.join(template_dir, region_type, folder)
        dest_dir = os.path.join(case_dir, folder, region_name)

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
            content = self._substitute(content, region_name, folder, log, file_name)
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
