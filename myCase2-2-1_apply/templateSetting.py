import os
import shutil

# =============================================================================
# 1. DEFINE YOUR REGIONS HERE
# =============================================================================
# Define exactly as they appear in your constant/ directory
FLUID_REGIONS = ["air"]
SOLID_REGIONS =["soc", "thermal_pad", "board", "case", "top_case"]

# =============================================================================
# 2. RAW OPENFOAM TEMPLATE CONTENT
# =============================================================================
# We use REPLACE_REGION placeholder to dynamically update headers during copy

def get_header(cls, obj):
    return """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  v2212                                 |
|   \\\\  /    A nd           | Website:  www.openfoam.com                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       """ + cls + """;
    location    "LOCATION_PLACEHOLDER";
    object      """ + obj + """;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //
"""

TEMPLATES = {
    # -------------------------------------------------------------------------
    # FLUID FILES
    # -------------------------------------------------------------------------
    "fluid/constant/thermophysicalProperties": get_header("dictionary", "thermophysicalProperties") + """
thermoType
{
    type            heRhoThermo;
    mixture         pureMixture;
    transport       const;
    thermo          hConst;
    equationOfState perfectGas;
    specie          specie;
    energy          sensibleEnthalpy;
}
mixture
{
    specie          { molWeight 28.9; }
    equationOfState { R 287; }
    thermo          { Cp 1004.4; Hf 0; }
    transport       { mu 1.8e-05; Pr 0.7; }
}""",
    
    "fluid/constant/turbulenceProperties": get_header("dictionary", "turbulenceProperties") + """
simulationType  RAS;
RAS { RASModel kEpsilon; turbulence on; printCoeffs on; }""",
    
    "fluid/system/fvSchemes": get_header("dictionary", "fvSchemes") + """
ddtSchemes { default steadyState; }
gradSchemes { default Gauss linear; }
divSchemes { default bounded Gauss upwind; }
laplacianSchemes { default Gauss linear orthogonal; }
interpolationSchemes { default linear; }
snGradSchemes { default orthogonal; }""",
    
    "fluid/system/fvSolution": get_header("dictionary", "fvSolution") + """
solvers {
    "p_rgh.*" { solver PCG; preconditioner DIC; tolerance 1e-6; relTol 0.01; }
    "(U|T|k|epsilon).*" { solver PBiCGStab; preconditioner DILU; tolerance 1e-6; relTol 0.1; }
}
SIMPLE { nNonOrthogonalCorrectors 0; pRefCell 0; pRefValue 1e5; }
relaxationFactors { fields { p_rgh 0.3; rho 1.0; } equations { U 0.7; T 0.5; k 0.7; epsilon 0.7; } }""",

    "fluid/0/T": get_header("volScalarField", "T") + """
dimensions [0 0 0 1 0 0 0];
internalField uniform 300;
boundaryField
{
    ".*_to_.*" // Regex matches ALL CHT boundaries automatically!
    {
        type            compressible::turbulentTemperatureCoupledBaffleMixed;
        Tnbr            T;
        kappaMethod     fluidThermo;
        value           $internalField;
    }
    // TODO: Define your outer boundary inlets/outlets/walls here
    ".*" { type zeroGradient; } 
}""",

    "fluid/0/U": get_header("volVectorField", "U") + """
dimensions[0 1 -1 0 0 0 0];
internalField uniform (0 0 0);
boundaryField
{
    ".*_to_.*" { type noSlip; }
    ".*" { type noSlip; } // TODO: Define Inlet
}""",

    "fluid/0/p_rgh": get_header("volScalarField", "p_rgh") + """
dimensions[1 -1 -2 0 0 0 0];
internalField uniform 1e5;
boundaryField
{
    ".*_to_.*" { type fixedFluxPressure; value $internalField; }
    ".*" { type fixedFluxPressure; value $internalField; } // TODO: Define Outlet
}""",

    "fluid/0/p": get_header("volScalarField", "p") + """
dimensions[1 -1 -2 0 0 0 0];
internalField uniform 1e5;
boundaryField { ".*" { type calculated; value $internalField; } }""",

    "fluid/0/k": get_header("volScalarField", "k") + """
dimensions[0 2 -2 0 0 0 0];
internalField uniform 0.1;
boundaryField { ".*" { type kqRWallFunction; value $internalField; } }""",

    "fluid/0/epsilon": get_header("volScalarField", "epsilon") + """
dimensions [0 2 -3 0 0 0 0];
internalField uniform 0.01;
boundaryField { ".*" { type epsilonWallFunction; value $internalField; } }""",

    "fluid/0/alphat": get_header("volScalarField", "alphat") + """
dimensions [1 -1 -1 0 0 0 0];
internalField uniform 0;
boundaryField { ".*" { type compressible::alphatWallFunction; PrandtlNum 0.85; value uniform 0; } }""",

    "fluid/0/nut": get_header("volScalarField", "nut") + """
dimensions [0 2 -1 0 0 0 0];
internalField uniform 0;
boundaryField { ".*" { type nutkWallFunction; value uniform 0; } }""",

    # -------------------------------------------------------------------------
    # SOLID FILES
    # -------------------------------------------------------------------------
    "solid/constant/thermophysicalProperties": get_header("dictionary", "thermophysicalProperties") + """
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
    specie          { molWeight 50; }
    equationOfState { rho 2700; }     // TODO: Update density for specific solid
    thermo          { Cp 870; Hf 0; } // TODO: Update Cp for specific solid
    transport       { kappa 200; }    // TODO: Update conductivity for specific solid
}""",

    "solid/system/fvSchemes": get_header("dictionary", "fvSchemes") + """
ddtSchemes { default steadyState; }
gradSchemes { default Gauss linear; }
divSchemes { default bounded Gauss upwind; }
laplacianSchemes { default Gauss linear orthogonal; }
interpolationSchemes { default linear; }
snGradSchemes { default orthogonal; }""",

    "solid/system/fvSolution": get_header("dictionary", "fvSolution") + """
solvers { "(T|h).*" { solver PCG; preconditioner DIC; tolerance 1e-6; relTol 0; } }
SIMPLE { nNonOrthogonalCorrectors 0; }
relaxationFactors { equations { T 1.0; h 1.0; } }""",

    "solid/0/T": get_header("volScalarField", "T") + """
dimensions [0 0 0 1 0 0 0];
internalField uniform 300;
boundaryField
{
    ".*_to_.*" // Regex matches ALL CHT boundaries automatically (solid-to-fluid AND solid-to-solid)
    {
        type            compressible::turbulentTemperatureCoupledBaffleMixed;
        Tnbr            T;
        kappaMethod     solidThermo;
        value           $internalField;
    }
    // TODO: Define boundaries touching the outer environment or heat sources
    ".*" { type zeroGradient; }
}"""
}

# =============================================================================
# 3. HELPER FUNCTIONS
# =============================================================================
def write_file(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)

def build_template_folder():
    """Generates the generic 'template' folder physically on disk."""
    print("Building generic 'template/' directory...")
    for rel_path, content in TEMPLATES.items():
        write_file(f"template/{rel_path}", content)

def deploy_to_region(region_name, region_type):
    """Copies template files to the specific region in 0, constant, and system."""
    print(f"Deploying {region_type} template to component: '{region_name}'...")
    
    # Target root folders
    for folder in ["0", "constant", "system"]:
        template_dir = f"template/{region_type}/{folder}"
        target_dir = f"{folder}/{region_name}"
        
        if not os.path.exists(template_dir):
            continue
            
        os.makedirs(target_dir, exist_ok=True)
        
        for filename in os.listdir(template_dir):
            template_file = os.path.join(template_dir, filename)
            target_file = os.path.join(target_dir, filename)
            
            # Read template, replace LOCATION_PLACEHOLDER with actual location, and write
            with open(template_file, "r") as f:
                content = f.read()
            
            content = content.replace("LOCATION_PLACEHOLDER", f"{folder}/{region_name}")
            
            with open(target_file, "w") as f:
                f.write(content)

def setup_global_files():
    """Sets up controlDict, g, and dynamically generates regionProperties."""
    print("Setting up global files (regionProperties, controlDict, g)...")
    
    # 1. regionProperties
    fluid_str = " ".join(FLUID_REGIONS)
    solid_str = " ".join(SOLID_REGIONS)
    rp_content = get_header("dictionary", "regionProperties").replace("LOCATION_PLACEHOLDER", "constant") + f"""
regions
{{
    fluid       ({fluid_str});
    solid       ({solid_str});
}}
"""
    write_file("constant/regionProperties", rp_content)

    # 2. constant/g
    g_content = get_header("uniformDimensionedVectorField", "g").replace("LOCATION_PLACEHOLDER", "constant") + """
dimensions      [0 1 -2 0 0 0 0];
value           (0 -9.81 0);
"""
    write_file("constant/g", g_content)

    # 3. system/controlDict
    cd_content = get_header("dictionary", "controlDict").replace("LOCATION_PLACEHOLDER", "system") + """
application     chtMultiRegionSimpleFoam;
startFrom       startTime;
startTime       0;
stopAt          endTime;
endTime         1000;
deltaT          1;
writeControl    timeStep;
writeInterval   100;
purgeWrite      2;
writeFormat     ascii;
writePrecision  6;
writeCompression off;
timeFormat      general;
timePrecision   6;
runTimeModifiable true;
"""
    write_file("system/controlDict", cd_content)

# =============================================================================
# 4. MAIN EXECUTION
# =============================================================================
if __name__ == "__main__":
    print("--- CHT Case Setup Script ---")
    
    # Step 1: Create physical template folder
    build_template_folder()
    
    # Step 2: Deploy to Fluid regions
    for fluid in FLUID_REGIONS:
        deploy_to_region(fluid, "fluid")
        
    # Step 3: Deploy to Solid regions
    for solid in SOLID_REGIONS:
        deploy_to_region(solid, "solid")
        
    # Step 4: Setup global OpenFOAM files
    setup_global_files()
    
    print("\n✅ Deployment Complete!")
    print("Next Steps:")
    print("  1. Check 0/air/U and 0/air/p_rgh to set up your inlet/outlet boundaries.")
    print("  2. Open constant/*/thermophysicalProperties to set exact Thermal Pad / Board / SOC properties (Cp, kappa, rho).")
    print("  3. Run: chtMultiRegionSimpleFoam")

