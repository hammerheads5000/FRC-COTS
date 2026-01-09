# FRC COTS Fusion 360 Add-In

## ⚙️ Smarter FRC Robot CAD Workflows

FRC COTS is a Fusion 360 add-in that gives robotics teams a clean, modern interface for browsing and inserting **COTS parts** directly into designs.
No more digging through Data Panels or re-creating parts someone already modeled. Just click → insert → joint → done.

Designed by **FRC Team 5000 — The Hammerheads — Logan de Laar**

---

## What It Does

- Browses all `.f3d` parts inside a cloud project named **FRC_COTS**
- Supports **folder navigation**, **search**, and **favorites**
- Shows **preview icons** if available
- Inserts parts into the active design with **one click**
- Automatically creates **rigid joints** aligned to:
  - Circular edges
  - Cylindrical faces
  - Planar faces (center keypoint)
  - Joint origins
- Works on **macOS and Windows**
- Beautiful UI with **Dark / Light theme toggle**

---

## 📁 How to Organize Your COTS Library

Create a project in Fusion 360 called:

```
FRC_COTS
```

Inside that project, add your `.f3d` CAD files in whatever folder structure you want:

```
FRC_COTS/
  Motors/
    Kraken_X60.f3d
    NEO.f3d
  Bearings/
    6804.f3d
  Gearboxes/
    MaxPlanetary.f3d
```

These folders become categories in the add-in.

(Optional) Preview icons can be added here inside the add-in folder:

```
FRC-COTS/icons/<PartName>.png
```

---

## Installation

### Recommended Method: GitHub Release ZIP

Download the latest `FRC-COTS.zip` from the Releases section on GitHub and extract it.
After extracting, rename the top-level folder to **FRC-COTS** (exact spelling, including hyphen).

Place the folder here depending on OS:

#### Windows
```
%AppData%/Autodesk/Autodesk Fusion 360/API/AddIns/FRC-COTS
```

#### macOS
```
~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/FRC-COTS
```

Ensure these files exist in that folder:

```
FRC-COTS/
  FRC-COTS.py
  FRC-COTS.manifest
  frc_cots_palette.html
  icons/
```

---

## Enabling in Fusion 360

1. Launch Fusion 360
2. Go to **UTILITIES → Add-Ins → Scripts and Add-Ins**
3. Select the **Add-Ins** tab
4. Locate **FRC-COTS**
5. Click **Run**
6. (Optional) Enable **Run on Startup**

A new button will appear:

> **Design Workspace → Insert Panel → FRC COTS Library**

---

## Usage

1. In the canvas, select circular edges / cylindrical faces / planar faces where a part should attach
2. Click a part in the COTS Library UI
3. The add-in:
   - Inserts a **reference occurrence**
   - **Ungrounds** the component if needed
   - Adds a **rigid joint** so position can be adjusted later

Favorites and theme settings persist across sessions.

---

## Joint Origins

1. If a part has a joint origin defined in it (the first one found) then it is inserted using the joint origin.  It points the joint origin positive z-axis toward the mating part.
2. If no joint origin exists then it is inserted with the coordinate origin as the center and the positive z-axis toward the mating part.

---

## Dynamic Spacers

1. Spacer and Shaft parts can be defined as 'dynamic spacers' so their length can be customized during insertion.
2. Some parts that are already setup as dynamic spacers can be found in the `spacers` directory of the Add-In files.
3. To create a dynamic spacer you do the following:
    - Make a part that is a short section of the spacer or shaft.  For shaft I used 2" lengths and for spacers I used 1/4" lengths.  It doesn't matter what length.  I chose those so the thumbnails looked good.
    - Each end of the part should be a planar face that is capable of being "Press/Pulled".
    - Create a joint origin at one end of the part with the z-direction of the joint origin facing outward.
    - Run the `Make Spacer` command found under the `Utilities` Panel.  Check the box to make this part a dynamic spacer.  This sets an attribute on the part file that is hidden but allows it to be dectected as a dynamic spacer. Unchecking the box removes the attribute.
    - Hide the joint origin and the coordinate origin if it is showing and save the design.
    - It should now be usable as a dynamic spacer.  
    - Just insert it from the FRC_COTS palette and it should bring up a different dialog to manipulate it.

---

## Tested With

- Autodesk Fusion 360 (latest public release)
- macOS Sonoma

Works in:
- Root assembly insertions
- Normal CAD workflows

---

## Roadmap

Planned improvements:

- Automatic preview icon generation
- Multi-insert (one part to multiple targets)
- Configurable joint types
- Make configurable files work
- Insert custom length spacers (round and hex)

---

## Author

**Logan de Laar**  
**FRC Team 5000 — The Hammerheads**  
Hingham High School


---

## License

MIT — free for all FRC teams 
