import os

def get_header(cls, obj):
    return f"""/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  v2412                                 |
|   \\\\  /    A nd           | Website:  www.openfoam.com                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{{
    version     2.0;
    format      ascii;
    class       {cls};
    location    "LOCATION_PLACEHOLDER";
    object      {obj};
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //
"""

TEMPLATES = {
    # ================= FLUID TEMPLATES =================
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
    specie
    {
        molWeight   28.9;
    }
    equationOfState
    {
        R           287;
    }
    thermodynamics
    {
        Cp          1004.4;
        Hf          0;
    }
    transport
    {
        mu          1.8e-05;
        Pr          0.7;
    }
}
""",

    "fluid/constant/turbulenceProperties": get_header("dictionary", "turbulenceProperties") + """
simulationType  RAS;

RAS
{
    RASModel        kEpsilon;
    turbulence      on;
    printCoeffs     on;
}
""",

    "fluid/system/fvSchemes": get_header("dictionary", "fvSchemes") + """
ddtSchemes
{
    default         steadyState;
}

gradSchemes
{
    default         Gauss linear;
}

divSchemes
{
    default         bounded Gauss upwind;
}

laplacianSchemes
{
    default         Gauss linear orthogonal;
}

interpolationSchemes
{
    default         linear;
}

snGradSchemes
{
    default         orthogonal;
}
""",

    "fluid/system/fvSolution": get_header("dictionary", "fvSolution") + """
solvers
{
    "p_rgh.*"
    {
        solver          PCG;
        preconditioner  DIC;
        tolerance       1e-6;
        relTol          0.01;
    }
    "(U|T|k|epsilon).*"
    {
        solver          PBiCGStab;
        preconditioner  DILU;
        tolerance       1e-6;
        relTol          0.1;
    }
}

SIMPLE
{
    nNonOrthogonalCorrectors 0;
    pRefCell        0;
    pRefValue       1e5;
}

relaxationFactors
{
    fields
    {
        p_rgh       0.3;
        rho         1.0;
    }
    equations
    {
        U           0.7;
        T           0.5;
        k           0.7;
        epsilon     0.7;
    }
}
""",

    "fluid/0/T": get_header("volScalarField", "T") + """
dimensions [0 0 0 1 0 0 0];

internalField   uniform 300;

boundaryField
{
    ".*_to_.*"
    {
        type            compressible::turbulentTemperatureCoupledBaffleMixed;
        Tnbr            T;
        kappaMethod     fluidThermo;
        value           $internalField;
    }
    ".*"
    {
        type            zeroGradient;
    }
}
""",

    "fluid/0/U": get_header("volVectorField", "U") + """
dimensions [0 1 -1 0 0 0 0];

internalField   uniform (0 0 0);

boundaryField
{
    ".*_to_.*"
    {
        type            noSlip;
    }
    ".*"
    {
        type            noSlip;
    }
}
""",

    "fluid/0/p_rgh": get_header("volScalarField", "p_rgh") + """
dimensions      [1 -1 -2 0 0 0 0];

internalField   uniform 1e5;

boundaryField
{
    ".*_to_.*"
    {
        type            fixedFluxPressure;
        value           $internalField;
    }
    ".*"
    {
        type            fixedFluxPressure;
        value           $internalField;
    }
}
""",

    "fluid/0/p": get_header("volScalarField", "p") + """
dimensions      [1 -1 -2 0 0 0 0];

internalField   uniform 1e5;

boundaryField
{
    ".*"
    {
        type            calculated;
        value           $internalField;
    }
}
""",

    "fluid/0/k": get_header("volScalarField", "k") + """
dimensions [0 2 -2 0 0 0 0];

internalField   uniform 0.1;

boundaryField
{
    ".*"
    {
        type            kqRWallFunction;
        value           $internalField;
    }
}
""",

    "fluid/0/epsilon": get_header("volScalarField", "epsilon") + """
dimensions      [0 2 -3 0 0 0 0];

internalField   uniform 0.01;

boundaryField
{
    ".*"
    {
        type            epsilonWallFunction;
        value           $internalField;
    }
}
""",

    "fluid/0/alphat": get_header("volScalarField", "alphat") + """
dimensions [1 -1 -1 0 0 0 0];

internalField   uniform 0;

boundaryField
{
    ".*"
    {
        type            compressible::alphatWallFunction;
        PrandtlNum      0.85;
        value           uniform 0;
    }
}
""",

    "fluid/0/nut": get_header("volScalarField", "nut") + """
dimensions [0 2 -1 0 0 0 0];

internalField   uniform 0;

boundaryField
{
    ".*"
    {
        type            nutkWallFunction;
        value           uniform 0;
    }
}
""",

    # ================= SOLID TEMPLATES =================
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
    specie
    {
        molWeight   50;
    }
    equationOfState
    {
        rho         2700;
    }
    thermodynamics
    {
        Cp          870;
        Hf          0;
    }
    transport
    {
        kappa       200;
    }
}
""",

    "solid/system/fvSchemes": get_header("dictionary", "fvSchemes") + """
ddtSchemes
{
    default         steadyState;
}

gradSchemes
{
    default         Gauss linear;
}

divSchemes
{
    default         bounded Gauss upwind;
}

laplacianSchemes
{
    default         Gauss linear orthogonal;
}

interpolationSchemes
{
    default         linear;
}

snGradSchemes
{
    default         orthogonal;
}
""",

    "solid/system/fvSolution": get_header("dictionary", "fvSolution") + """
solvers
{
    "(T|h).*"
    {
        solver          PCG;
        preconditioner  DIC;
        tolerance       1e-6;
        relTol          0;
    }
}

SIMPLE
{
    nNonOrthogonalCorrectors 0;
}

relaxationFactors
{
    equations
    {
        T           1.0;
        h           1.0;
    }
}
""",

    "solid/0/T": get_header("volScalarField", "T") + """
dimensions [0 0 0 1 0 0 0];

internalField   uniform 300;

boundaryField
{
    ".*_to_.*"
    {
        type            compressible::turbulentTemperatureCoupledBaffleMixed;
        Tnbr            T;
        kappaMethod     solidThermo;
        value           $internalField;
    }
    ".*"
    {
        type            zeroGradient;
    }
}
""",

    "solid/0/p": get_header("volScalarField", "p") + """
dimensions [1 -1 -2 0 0 0 0];

internalField   uniform 1e5;

boundaryField
{
    ".*"
    {
        type            calculated;
        value           $internalField;
    }
}
""",

    # ================= GLOBAL TEMPLATES =================
    "global/constant/g": get_header("uniformDimensionedVectorField", "g") + """
dimensions [0 1 -2 0 0 0 0];

value           (0 -9.81 0);
""",

    "global/system/controlDict": get_header("dictionary", "controlDict") + """
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
""",

    "global/system/changeDictionaryDict": get_header("dictionary", "changeDictionaryDict") + """

T
{
    internalField uniform 300;
    
    boundaryField
    {
        ".*"
        {
            type    zeroGrandient;
            value   uniform 300;
        }

        ".*_to_.*"
        {
            type            compressible::turbulentTemperatureCoupledBaffleMixed;
            Tnbr            T;
            kappaMethod     solidThermo;
            value           uniform 300;
        }
    }

}
""",

    "global/constant/regionProperties": get_header("dictionary", "regionProperties") + """
regions
(
    fluid       (FLUID_PLACEHOLDER)
    solid       (SOLID_PLACEHOLDER)
);
"""
}

print("Building generic 'template/' directory...")
for rel_path, content in TEMPLATES.items():
    path = os.path.join("template", rel_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)
print("Done! You now have a beautifully formatted, reusable 'template' folder.")
