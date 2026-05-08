"""
material_db.py — Thermophysical material database for chtMultiRegionSimpleFoam.

How to add a new material
--------------------------
Add one entry to MATERIAL_DB following the existing pattern:

    "keyword": {
        "type":        "fluid" | "solid",
        "description": "Human-readable label shown in the GUI table",
        "kappa":       float,   # W/(m·K) — for display only (real value in content)
        "rho":         float,   # kg/m³
        "cp":          float,   # J/(kg·K)
        "content":     str,     # complete thermophysicalProperties file content
    }

The keyword is matched against region folder name tokens split on [_-].
Example: folder "air_normal"  → tokens ["air", "normal"] → matches "air".
         folder "SOC"         → tokens ["soc"]           → matches "soc".
         folder "bottomcase"  → no token match           → checked as substring → matches "case".

lookup_material() returns the matching dict (with "matched_key" added) or None.
"""

import re

# =============================================================================
# DATABASE
# =============================================================================

MATERIAL_DB: dict[str, dict] = {

    # ── Fluids ──────────────────────────────────────────────────────────────

    "air": {
        "type": "fluid",
        "description": "Air ~300 K, ideal gas (Sutherland + JANAF)",
        "kappa": None, "rho": None, "cp": None,   # varies with T
        "content": """\
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "constant";
    object      thermophysicalProperties;
}
thermoType
{
    type            heRhoThermo;
    mixture         pureMixture;
    transport       sutherland;
    thermo          janaf;
    energy          sensibleEnthalpy;
    equationOfState perfectGas;
    specie          specie;
}
mixture
{
    specie          { molWeight 28.9; }
    thermodynamics
    {
        Tlow        200;
        Thigh       5000;
        Tcommon     1000;
        highCpCoeffs ( 3.57304 -4.35e-04 2.16e-06 -1.15e-09 2.24e-13 -1047.9 3.124 );
        lowCpCoeffs  ( 3.09591  1.22e-03  4.44e-07 -1.88e-10  5.96e-14  -983.2 5.087 );
    }
    transport       { As 1.458e-06; Ts 110.4; }
}
""",
    },

    "water": {
        "type": "fluid",
        "description": "Liquid water ~300 K (Boussinesq)",
        "kappa": 0.598, "rho": 998.2, "cp": 4182,
        "content": """\
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "constant";
    object      thermophysicalProperties;
}
thermoType
{
    type            heRhoThermo;
    mixture         pureMixture;
    transport       const;
    thermo          hConst;
    energy          sensibleEnthalpy;
    equationOfState Boussinesq;
    specie          specie;
}
mixture
{
    specie          { molWeight 18.015; }
    equationOfState { rho0 998.2; T0 300; beta 2.57e-4; }
    thermodynamics  { Cp 4182; Hf 0; }
    transport       { mu 1.002e-3; Pr 6.99; }
}
""",
    },

    "coolant": {
        "type": "fluid",
        "description": "Generic coolant (water-like)",
        "kappa": 0.598, "rho": 998.2, "cp": 4182,
        "content": """\
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "constant";
    object      thermophysicalProperties;
}
thermoType
{
    type            heRhoThermo;
    mixture         pureMixture;
    transport       const;
    thermo          hConst;
    energy          sensibleEnthalpy;
    equationOfState Boussinesq;
    specie          specie;
}
mixture
{
    specie          { molWeight 18.015; }
    equationOfState { rho0 998.2; T0 300; beta 2.57e-4; }
    thermodynamics  { Cp 4182; Hf 0; }
    transport       { mu 1.002e-3; Pr 6.99; }
}
""",
    },

    # ── Metals ──────────────────────────────────────────────────────────────

    "aluminum": {
        "type": "solid",
        "description": "Aluminium alloy 6061",
        "kappa": 160.0, "rho": 2700.0, "cp": 896.0,
        "content": """\
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "constant";
    object      thermophysicalProperties;
}
thermoType
{
    type            heSolidThermo;
    mixture         pureMixture;
    transport       constIso;
    thermo          hConst;
    equationOfState rhoConst;
    specie          specie;
    energy          sensibleEnthalpy;
}
mixture
{
    specie          { molWeight 26.98; }
    transport       { kappa 160; }
    thermodynamics  { Cp 896; Hf 0; }
    equationOfState { rho 2700; }
}
""",
    },

    "aluminium": {          # British spelling — identical properties
        "type": "solid",
        "description": "Aluminium alloy 6061 (British spelling)",
        "kappa": 160.0, "rho": 2700.0, "cp": 896.0,
        "content": """\
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "constant";
    object      thermophysicalProperties;
}
thermoType
{
    type            heSolidThermo;
    mixture         pureMixture;
    transport       constIso;
    thermo          hConst;
    equationOfState rhoConst;
    specie          specie;
    energy          sensibleEnthalpy;
}
mixture
{
    specie          { molWeight 26.98; }
    transport       { kappa 160; }
    thermodynamics  { Cp 896; Hf 0; }
    equationOfState { rho 2700; }
}
""",
    },

    "copper": {
        "type": "solid",
        "description": "Pure copper (C11000)",
        "kappa": 385.0, "rho": 8960.0, "cp": 385.0,
        "content": """\
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "constant";
    object      thermophysicalProperties;
}
thermoType
{
    type            heSolidThermo;
    mixture         pureMixture;
    transport       constIso;
    thermo          hConst;
    equationOfState rhoConst;
    specie          specie;
    energy          sensibleEnthalpy;
}
mixture
{
    specie          { molWeight 63.55; }
    transport       { kappa 385; }
    thermodynamics  { Cp 385; Hf 0; }
    equationOfState { rho 8960; }
}
""",
    },

    "steel": {
        "type": "solid",
        "description": "Stainless steel 316L",
        "kappa": 16.3, "rho": 8000.0, "cp": 500.0,
        "content": """\
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "constant";
    object      thermophysicalProperties;
}
thermoType
{
    type            heSolidThermo;
    mixture         pureMixture;
    transport       constIso;
    thermo          hConst;
    equationOfState rhoConst;
    specie          specie;
    energy          sensibleEnthalpy;
}
mixture
{
    specie          { molWeight 55.85; }
    transport       { kappa 16.3; }
    thermodynamics  { Cp 500; Hf 0; }
    equationOfState { rho 8000; }
}
""",
    },

    # ── Electronics ─────────────────────────────────────────────────────────

    "pcb": {
        "type": "solid",
        "description": "FR4 PCB (low κ in-plane)",
        "kappa": 0.3, "rho": 1850.0, "cp": 1200.0,
        "content": """\
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "constant";
    object      thermophysicalProperties;
}
thermoType
{
    type            heSolidThermo;
    mixture         pureMixture;
    transport       constIso;
    thermo          hConst;
    equationOfState rhoConst;
    specie          specie;
    energy          sensibleEnthalpy;
}
mixture
{
    specie          { molWeight 100; }
    transport       { kappa 0.3; }
    thermodynamics  { Cp 1200; Hf 0; }
    equationOfState { rho 1850; }
}
""",
    },

    "board": {
        "type": "solid",
        "description": "FR4 PCB board (alias of pcb)",
        "kappa": 0.3, "rho": 1850.0, "cp": 1200.0,
        "content": """\
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "constant";
    object      thermophysicalProperties;
}
thermoType
{
    type            heSolidThermo;
    mixture         pureMixture;
    transport       constIso;
    thermo          hConst;
    equationOfState rhoConst;
    specie          specie;
    energy          sensibleEnthalpy;
}
mixture
{
    specie          { molWeight 100; }
    transport       { kappa 0.3; }
    thermodynamics  { Cp 1200; Hf 0; }
    equationOfState { rho 1850; }
}
""",
    },

    "soc": {
        "type": "solid",
        "description": "Silicon SoC die",
        "kappa": 130.0, "rho": 2329.0, "cp": 700.0,
        "content": """\
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "constant";
    object      thermophysicalProperties;
}
thermoType
{
    type            heSolidThermo;
    mixture         pureMixture;
    transport       constIso;
    thermo          hConst;
    equationOfState rhoConst;
    specie          specie;
    energy          sensibleEnthalpy;
}
mixture
{
    specie          { molWeight 28.09; }
    transport       { kappa 130; }
    thermodynamics  { Cp 700; Hf 0; }
    equationOfState { rho 2329; }
}
""",
    },

    "chip": {
        "type": "solid",
        "description": "Silicon chip die (alias of soc)",
        "kappa": 130.0, "rho": 2329.0, "cp": 700.0,
        "content": """\
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "constant";
    object      thermophysicalProperties;
}
thermoType
{
    type            heSolidThermo;
    mixture         pureMixture;
    transport       constIso;
    thermo          hConst;
    equationOfState rhoConst;
    specie          specie;
    energy          sensibleEnthalpy;
}
mixture
{
    specie          { molWeight 28.09; }
    transport       { kappa 130; }
    thermodynamics  { Cp 700; Hf 0; }
    equationOfState { rho 2329; }
}
""",
    },

    "thermalpad": {
        "type": "solid",
        "description": "TIM pad — silicone-based ~5 W/m·K",
        "kappa": 5.0, "rho": 2500.0, "cp": 1000.0,
        "content": """\
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "constant";
    object      thermophysicalProperties;
}
thermoType
{
    type            heSolidThermo;
    mixture         pureMixture;
    transport       constIso;
    thermo          hConst;
    equationOfState rhoConst;
    specie          specie;
    energy          sensibleEnthalpy;
}
mixture
{
    specie          { molWeight 100; }
    transport       { kappa 5.0; }
    thermodynamics  { Cp 1000; Hf 0; }
    equationOfState { rho 2500; }
}
""",
    },

    "heatsink": {
        "type": "solid",
        "description": "Aluminium heatsink body",
        "kappa": 160.0, "rho": 2700.0, "cp": 896.0,
        "content": """\
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "constant";
    object      thermophysicalProperties;
}
thermoType
{
    type            heSolidThermo;
    mixture         pureMixture;
    transport       constIso;
    thermo          hConst;
    equationOfState rhoConst;
    specie          specie;
    energy          sensibleEnthalpy;
}
mixture
{
    specie          { molWeight 26.98; }
    transport       { kappa 160; }
    thermodynamics  { Cp 896; Hf 0; }
    equationOfState { rho 2700; }
}
""",
    },

    # ── Plastics / Structural ────────────────────────────────────────────────

    "case": {
        "type": "solid",
        "description": "ABS plastic enclosure/case",
        "kappa": 0.17, "rho": 1050.0, "cp": 1400.0,
        "content": """\
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "constant";
    object      thermophysicalProperties;
}
thermoType
{
    type            heSolidThermo;
    mixture         pureMixture;
    transport       constIso;
    thermo          hConst;
    equationOfState rhoConst;
    specie          specie;
    energy          sensibleEnthalpy;
}
mixture
{
    specie          { molWeight 100; }
    transport       { kappa 0.17; }
    thermodynamics  { Cp 1400; Hf 0; }
    equationOfState { rho 1050; }
}
""",
    },

    "plastic": {
        "type": "solid",
        "description": "Generic ABS plastic",
        "kappa": 0.17, "rho": 1050.0, "cp": 1400.0,
        "content": """\
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "constant";
    object      thermophysicalProperties;
}
thermoType
{
    type            heSolidThermo;
    mixture         pureMixture;
    transport       constIso;
    thermo          hConst;
    equationOfState rhoConst;
    specie          specie;
    energy          sensibleEnthalpy;
}
mixture
{
    specie          { molWeight 100; }
    transport       { kappa 0.17; }
    thermodynamics  { Cp 1400; Hf 0; }
    equationOfState { rho 1050; }
}
""",
    },
}

# Keywords used as fallback fluid/solid classification when no DB entry matches
FLUID_KEYWORDS = frozenset([
    "air", "water", "fluid", "gas", "liquid", "coolant", "oil",
    "channel", "plenum", "inlet", "outlet",
])
SOLID_KEYWORDS = frozenset([
    "steel", "copper", "aluminum", "aluminium", "board", "soc", "thermalpad",
    "case", "solid", "heatsink", "fin", "pcb", "chip",
    "iron", "glass", "plastic", "pad", "spreader", "housing",
])


# =============================================================================
# LOOKUP
# =============================================================================

def lookup_material(region_name: str) -> dict | None:
    """
    Match a region folder name against MATERIAL_DB.

    Strategy (first match wins):
      1. Full lowercase name  → "air_normal"  exact match unlikely but fast
      2. Token split on _/-   → "air_normal"  → ["air","normal"] → "air" ✓
      3. Substring scan       → "bottomcase"  → contains "case" ✓

    Returns the matching dict with "matched_key" injected, or None.
    """
    name_lower = region_name.lower()

    # 1. Exact match
    if name_lower in MATERIAL_DB:
        return {**MATERIAL_DB[name_lower], "matched_key": name_lower}

    # 2. Token match (underscore / hyphen split)
    tokens = re.split(r"[_\-\s]+", name_lower)
    for token in tokens:
        if token in MATERIAL_DB:
            return {**MATERIAL_DB[token], "matched_key": token}

    # 3. Substring match (e.g. "bottomcase" contains "case")
    for key in MATERIAL_DB:
        if key in name_lower:
            return {**MATERIAL_DB[key], "matched_key": key}

    return None


def classify_region(region_name: str, material: dict | None) -> str:
    """
    Return 'fluid' or 'solid' for a region.
    Uses the material DB type if matched, otherwise falls back to keyword scan.
    Defaults to 'solid' if nothing matches (safe CHT default).
    """
    if material:
        return material["type"]

    name_lower = region_name.lower()
    tokens = re.split(r"[_\-\s]+", name_lower)

    if any(t in FLUID_KEYWORDS for t in tokens) or any(kw in name_lower for kw in FLUID_KEYWORDS):
        return "fluid"
    if any(t in SOLID_KEYWORDS for t in tokens) or any(kw in name_lower for kw in SOLID_KEYWORDS):
        return "solid"

    return "solid"   # safe default — all physical bodies conduct heat
