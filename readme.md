### protocol

1. build template

2. prepare cad file

3. use gmsh script gen .msh mesh file

4. use gmshToFoam turn into openfoam formate

5. run "transferPoint -scale 0.001" to set unit as mm

6. run  "splitMeshRegion -cellZone -overwrite"

7. run apply case to set init condition 
