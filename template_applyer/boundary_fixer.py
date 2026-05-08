"""
boundary_fixer.py — Rewrites polyMesh/boundary patch types for chtMultiRegionSimpleFoam.

Problem
-------
gmshToFoam assigns every boundary face the generic type 'patch'.
chtMultiRegionSimpleFoam requires:
  - Physical walls             → type wall
  - Coupled fluid-solid faces  → type mappedWall  (handled by changeDictionary)
  - Inlets / outlets           → type patch  (kept as-is)

This module handles the patch → wall conversion for all non-inlet/outlet,
non-coupled boundaries across all regions.

Parser design
-------------
Uses a forward-scan with a running patch-name tracker rather than backward
lookahead. This works correctly on both multi-line and compact boundary formats:

  Multi-line (gmshToFoam default):        Compact (some older versions):
      myPatch                                 myPatch { type patch; ... }
      {
          type patch;
      }

The tracker updates current_patch whenever it sees a bare identifier line
(no braces, no semicolons, not a comment, not starting with a digit).
"""

import os


# Patch name tokens that must NOT be converted to wall
_KEEP_AS_PATCH = ("inlet", "outlet", "_to_")


class BoundaryFixer:
    """
    Iterates over all regions and rewrites their polyMesh/boundary files.
    """

    def fix_all(self, case_dir: str, regions: list[str], log) -> None:
        log("\n  Fixing boundary types (patch → wall)...")
        changed_count = 0
        for region in regions:
            n = self._fix_region(case_dir, region, log)
            changed_count += n
        log(f"  Boundary fix complete — {changed_count} patch(es) converted.")

    def _fix_region(self, case_dir: str, region: str, log) -> int:
        """Returns number of patches converted in this region."""
        b_file = os.path.join(
            case_dir, "constant", region, "polyMesh", "boundary"
        )
        if not os.path.exists(b_file):
            log(f"    [Warning] No boundary file for '{region}' — skipping.")
            return 0

        with open(b_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

        new_lines, n_changed = self._process_lines(lines, region, log)

        if n_changed:
            with open(b_file, "w", encoding="utf-8") as f:
                f.writelines(new_lines)

        return n_changed

    @staticmethod
    def _process_lines(lines: list[str], region: str, log) -> tuple[list[str], int]:
        """
        Parse lines and convert eligible 'type patch;' entries to 'type wall;'.
        Returns (modified_lines, number_of_changes).
        """
        current_patch = ""
        n_changed = 0
        result = []

        for line in lines:
            stripped = line.strip()

            # Track patch name: bare word line with no braces or semicolons
            if (stripped
                    and not stripped.startswith("//")
                    and "{" not in stripped
                    and "}" not in stripped
                    and ";" not in stripped
                    and not stripped[0].isdigit()):
                current_patch = stripped

            # Convert patch → wall where appropriate
            if "type" in line and "patch;" in line:
                name_lower = current_patch.lower()
                if not any(kw in name_lower for kw in _KEEP_AS_PATCH):
                    line = line.replace("patch;", "wall;")
                    n_changed += 1
                    log(f"    [{region}] '{current_patch}' patch → wall")

            result.append(line)

        return result, n_changed
