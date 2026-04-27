import os
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext

# =============================================================================
# CORE LOGIC 
# =============================================================================

def get_regions_from_mesh(case_dir, log_func):
    """
    Scans the constant/ directory and uses keyword matching to 
    intelligently sort components into fluids and solids.
    """
    fluids, solids = [],[]
    constant_path = os.path.join(case_dir, "constant")

    if not os.path.exists(constant_path):
        return None, None

    # --- Pre-defined Material Keywords ---
    FLUID_KEYWORDS =["air", "water", "fluid", "gas", "liquid", "coolant", "oil"]
    SOLID_KEYWORDS =["steel", "copper", "aluminum", "board", "soc", "thermalpad",
                     "case", "solid", "heatsink", "fin", "pcb", "chip",
                      "iron", "glass", "plastic"]

    for item in os.listdir(constant_path):
        item_path = os.path.join(constant_path, item)

        # Check if it's a valid region (must be a directory and have a polyMesh inside)
        if os.path.isdir(item_path) and os.path.exists(os.path.join(item_path, "polyMesh")):
            region_name_lower = item.lower()

            # 1. Check if it matches any Fluid keywords
            if any(kw in region_name_lower for kw in FLUID_KEYWORDS):
                fluids.append(item)

            # 2. Check if it matches any Solid keywords
            elif any(kw in region_name_lower for kw in SOLID_KEYWORDS):
                solids.append(item)

            # 3. Fallback if it matches neither (defaults to solid)
            else:
                log_func(f" [Warning] Unrecognized material in name '{item}'. Defaulting to Solid.")
                solids.append(item)

    return fluids, solids


def fix_boundary_types(case_dir, regions, log_func):
    """
    Scans the polyMesh/boundary file for every region.
    Changes 'type patch;' to 'type wall;' for defaultFaces and generic CAD walls.
    """
    log_func("\n -> Auto-fixing mesh boundary types (patch -> wall)...")
    for region in regions:
        b_file = os.path.join(case_dir, "constant", region, "polyMesh", "boundary")
        if not os.path.exists(b_file):
            continue

        with open(b_file, 'r') as f:
            lines = f.readlines()

        changed = False
        for i in range(len(lines)):
            if "type" in lines[i] and "patch;" in lines[i]:
                # Traverse upwards to find the boundary name
                b_name = ""
                for j in range(i-1, max(-1, i-5), -1):
                    if lines[j].strip() == "{":
                        if j - 1 >= 0:
                            b_name = lines[j-1].strip()
                        break

                # If it's not an inlet or outlet, it should be a wall!
                b_name_lower = b_name.lower()
                if "inlet" not in b_name_lower and "outlet" not in b_name_lower and "_to_" not in b_name_lower:
                    lines[i] = lines[i].replace("patch;", "wall;")
                    changed = True
                    log_func(f"      [{region}] Converted boundary '{b_name}' to type wall.")

        if changed:
            with open(b_file, 'w') as f:
                f.writelines(lines)

def deploy_template(template_dir, case_dir, region_name, region_type, log_func):
    log_func(f" -> Deploying {region_type} physics to: {region_name}")
    for folder in["0", "constant", "system"]:
        src_dir = os.path.join(template_dir, region_type, folder)
        dest_dir = os.path.join(case_dir, folder, region_name)
        if not os.path.exists(src_dir): continue
        os.makedirs(dest_dir, exist_ok=True)
        for file_name in os.listdir(src_dir):
            src_file = os.path.join(src_dir, file_name)
            dest_file = os.path.join(dest_dir, file_name)
            with open(src_file, "r") as f:
                content = f.read()

            # =================================================================
            # NEW: Logic to handle coupled boundary placeholders
            # =================================================================
            if '".*_to_.*"' in content:
                # Replace the placeholder with a wildcard expression for the current region
                # e.g., for region 'air', this becomes '"air_to_.*"'
                replacement_string = f'"{region_name}_to_.*"'
                content = content.replace('".*_to_.*"', replacement_string)
                log_func(f"      [{region_name}/{file_name}] Set up coupled boundary condition as {replacement_string}")
            else :
                log_func(f"no [ .*_to_.* ] in the openfoam init file ")
            # =================================================================

            content = content.replace("LOCATION_PLACEHOLDER", f"{folder}/{region_name}")
            content = content.replace("FLUID_PLACEHOLDER", f"{region_name}")
            content = content.replace("SOLID_PLACEHOLDER", f"{region_name}")
            with open(dest_file, "w") as f:
                f.write(content)

def deploy_global_files(template_dir, case_dir, fluids, solids, log_func):
    log_func(" -> Deploying global files (controlDict, g, regionProperties)")
    for folder in["constant", "system"]:
        src_dir = os.path.join(template_dir, "global", folder)
        dest_folder = os.path.join(case_dir, folder)
        os.makedirs(dest_folder, exist_ok=True)
        for file_name in os.listdir(src_dir):
            src_file = os.path.join(src_dir, file_name)
            dest_file = os.path.join(dest_folder, file_name)
            with open(src_file, "r") as f: content = f.read()
            if file_name == "regionProperties":
                content = content.replace("FLUID_PLACEHOLDER", " ".join(fluids))
                content = content.replace("SOLID_PLACEHOLDER", " ".join(solids))
            content = content.replace("LOCATION_PLACEHOLDER", folder)
            with open(dest_file, "w") as f: f.write(content)

# =============================================================================
# GUI APPLICATION
# =============================================================================
class OpenFOAMDeployerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("OpenFOAM CHT Template Deployer")
        self.root.geometry("650x450")
        self.template_dir_var = tk.StringVar()
        self.case_dir_var = tk.StringVar()
        self.create_widgets()

    def create_widgets(self):
        input_frame = tk.Frame(self.root, padx=10, pady=10)
        input_frame.pack(fill="x")
        tk.Label(input_frame, text="Template Folder:", width=15, anchor="w").grid(row=0, column=0, pady=5)
        tk.Entry(input_frame, textvariable=self.template_dir_var, width=50).grid(row=0, column=1, pady=5, padx=5)
        tk.Button(input_frame, text="Browse...", command=self.browse_template).grid(row=0, column=2, pady=5)
        tk.Label(input_frame, text="Case Folder:", width=15, anchor="w").grid(row=1, column=0, pady=5)
        tk.Entry(input_frame, textvariable=self.case_dir_var, width=50).grid(row=1, column=1, pady=5, padx=5)
        tk.Button(input_frame, text="Browse...", command=self.browse_case).grid(row=1, column=2, pady=5)
        tk.Button(input_frame, text="Apply Template & Fix Mesh", bg="green", fg="white",
                  font=("Arial", 11, "bold"), command=self.run_deployment).grid(row=2, column=0, columnspan=3, pady=15, sticky="we")
        log_frame = tk.Frame(self.root, padx=10, pady=5)
        log_frame.pack(fill="both", expand=True)
        tk.Label(log_frame, text="Execution Logs:", anchor="w").pack(fill="x")
        self.log_text = scrolledtext.ScrolledText(log_frame, height=10, state='disabled', bg="#1e1e1e", fg="#00ff00")
        self.log_text.pack(fill="both", expand=True)

    def log(self, message):
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')
        self.root.update()

    def browse_template(self):
        folder = filedialog.askdirectory(title="Select OpenFOAM Template Folder")
        if folder: self.template_dir_var.set(folder)

    def browse_case(self):
        folder = filedialog.askdirectory(title="Select OpenFOAM Case Folder")
        if folder: self.case_dir_var.set(folder)

    def run_deployment(self):
        template_dir = self.template_dir_var.get()
        case_dir = self.case_dir_var.get()
        if not template_dir or not case_dir:
            messagebox.showerror("Error", "Please select both Template and Case folders.")
            return

        self.log("=== Starting OpenFOAM CHT Deployment ===")
        fluids, solids = get_regions_from_mesh(case_dir , self.log)
        if not fluids and not solids:
            self.log("ERROR: No polyMesh regions found. Run splitMeshRegions first.")
            return

        self.log(f"Detected Fluid regions: {fluids}")
        self.log(f"Detected Solid regions: {solids}")

        try:
            # 1. Fix mesh boundary dictionary types
            fix_boundary_types(case_dir, fluids + solids, self.log)

            # 2. Deploy Physics
            for f in fluids: deploy_template(template_dir, case_dir, f, "fluid", self.log)
            for s in solids: deploy_template(template_dir, case_dir, s, "solid", self.log)
            deploy_global_files(template_dir, case_dir, fluids, solids, self.log)

            self.log("\n✅ Success! Mesh fixed and Case fully configured.")
        except Exception as e:
            self.log(f"\n❌ FATAL ERROR: {str(e)}")

if __name__ == "__main__":
    root = tk.Tk()
    app = OpenFOAMDeployerGUI(root)
    root.mainloop()
