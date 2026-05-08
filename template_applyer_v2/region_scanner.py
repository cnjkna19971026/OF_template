"""
region_scanner.py — Discovers fluid/solid regions from splitMeshRegions output.

splitMeshRegions -cellZones -overwrite creates:
    constant/<regionName>/polyMesh/

This module scans that structure, classifies each region as fluid or solid,
and resolves its material from material_db.
"""

import os
from material_db import lookup_material, classify_region


class RegionScanner:
    """
    Reads constant/<region>/polyMesh directories and returns classified
    fluid/solid lists with matched materials.
    """

    def scan(self, case_dir: str, log) -> tuple[list, list, dict]:
        """
        Scan case_dir for splitMeshRegions output.

        Returns:
            fluids       — list of region folder names classified as fluid
            solids       — list of region folder names classified as solid
            material_map — dict: region_name → material dict | None
        """
        fluids: list[str] = []
        solids: list[str] = []
        material_map: dict = {}

        constant_path = os.path.join(case_dir, "constant")

        if not os.path.exists(constant_path):
            log("  ERROR: constant/ directory not found.")
            log(f"         Expected: {constant_path}")
            return [], [], {}

        candidates = self._find_region_dirs(constant_path)

        if not candidates:
            log("  ERROR: No polyMesh regions found.")
            log("         Run: splitMeshRegions -cellZones -overwrite")
            log("         Then re-scan.")
            return [], [], {}

        log(f"  Found {len(candidates)} region(s) in constant/")

        for name in sorted(candidates):
            mat = lookup_material(name)
            material_map[name] = mat
            rtype = classify_region(name, mat)

            if rtype == "fluid":
                fluids.append(name)
            else:
                solids.append(name)

            mat_label = f"→ {mat['matched_key']}" if mat else "→ ⚠ no match"
            log(f"    [{rtype:6s}] {name:30s} {mat_label}")

        # Warn about unmatched regions
        unknowns = [n for n, m in material_map.items() if m is None]
        if unknowns:
            log(f"\n  ⚠  No material DB match for: {unknowns}")
            log("     Template thermophysicalProperties will be used unchanged.")
            log("     To fix: add the keyword to MATERIAL_DB in material_db.py,")
            log("     or rename the region folder to include a known keyword.")

        return fluids, solids, material_map

    @staticmethod
    def _find_region_dirs(constant_path: str) -> list[str]:
        """Return folder names under constant/ that contain a polyMesh subdirectory."""
        result = []
        for item in os.listdir(constant_path):
            item_path = os.path.join(constant_path, item)
            poly_path = os.path.join(item_path, "polyMesh")
            if os.path.isdir(item_path) and os.path.exists(poly_path):
                result.append(item)
        return result
