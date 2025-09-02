# Arma PBO Tools (Linux GUI + Wrappers)

A simple Tk GUI and helper wrappers that make Mikero’s Windows tools usable on Linux with Wine. Extract and pack `.pbo` missions, deRap `.bin/.rap` configs to `.cpp`, inject a basic respawn block, and fall back to a built-in uncompressed PBO extractor when needed — all without hand-crafting `winepath` commands.

> Works great on Ubuntu and Pop!\_OS. Uses only system packages, Wine, and the official Mikero installers you run under Wine.

<img width="1394" height="830" alt="image" src="https://github.com/user-attachments/assets/8e455b76-5b16-4e79-a914-071c92edd278" />

---

## Why you should care

* **Stop fighting paths.** The wrappers convert Linux paths to Windows paths for Wine automatically.
* **One-click setup.** Buttons install Wine helpers, launch Mikero installers, and link the installed EXEs.
* **CLI and GUI.** You get a friendly GUI and real shell commands `cpbo` and `unrap` in `~/.local/bin`.
* **Safer first run.** The app verifies the required Mikero runtime DLLs and tells you exactly what is missing.
* **Keeps your layout.** It looks for your `MPMissions` folder automatically.
* **Emergency fallback.** It includes a native extractor for **uncompressed** PBOs when you cannot use cpbo yet.
* **Mission quality of life.** Quickly inject a working respawn section into `description.ext` with a button.

---

## What it does (summary)

<img width="1118" height="542" alt="image" src="https://github.com/user-attachments/assets/07b724eb-cb21-4b04-818f-bdf0ed7ac760" />
<img width="1830" height="727" alt="image" src="https://github.com/user-attachments/assets/1fb4b2f7-6cb1-4008-a5a6-4ef0d8d28aa8" />
<img width="1843" height="916" alt="image" src="https://github.com/user-attachments/assets/deeff7c6-596f-4f4e-a51e-10d4de583bcb" />


* Installs small bash **wrappers** named `cpbo` and `unrap` in `~/.local/bin`.
  These wrappers:

  * Change directory to the installed EXE
  * Convert Linux paths to Windows paths with `winepath`
  * Emulate `cpbo -e` and `cpbo -p` if you only have `ExtractPbo.exe` plus `MakePbo.exe`
* Launches the official **Mikero installers** under your selected Wine prefix
* **Finds and links** the installed EXEs, saving their paths in `~/.local/share/arma_pbo_tools/*.path`
* Verifies presence of **DePbo** and **DeOgg** runtime DLLs next to the tools
* Provides buttons to:

  * Extract PBO with cpbo
  * Pack a mission folder to PBO with cpbo + MakePbo
  * DeRap `.bin/.rap/.cfg` to `.cpp` with unRap
  * Inject a basic respawn config into `description.ext`
  * Run a fallback extractor for **uncompressed** PBOs only
* Offers logging, copy to clipboard, and save to file

---

## Requirements

* A Debian/Ubuntu-based distro (Pop!\_OS is fine)
* `apt` available
* Wine. The GUI can install:

  * `wine-stable`
  * `winbind`
  * `cabextract`
  * `p7zip-full`
* Mikero’s tools installed under Wine:

  * ExtractPbo
  * MakePbo (if you want packing)
  * DeRap
  * DePbo runtime
  * DeOgg runtime

> The app can download and launch the official Mikero installers for you under Wine. You accept those licenses when you run them. This project does not redistribute Mikero binaries.

---

## Quick start

1. **Run the app**

   ```bash
   python3 arma_pbo_tools.py
   ```

   You will see “Arma PBO Tools - Install + Extract (cpbo preferred)”.

2. **Install Wine + helpers**
   Click **Install Wine + helpers**. A terminal will open and run:

   ```
   sudo apt update
   sudo apt install -y wine-stable winbind cabextract p7zip-full
   ```

   Close the terminal when finished.

3. **Pick or create a Wine prefix**

   * Use the **Browse…** button to select your prefix, or
   * Click **Create 64-bit Prefix (\~/.wine64) & Use**
     Then click **Use This Prefix**.

4. **Install Mikero tools**
   Click these buttons and follow each Windows installer:

   * **Install ExtractPbo**
   * **Install DeRap**
   * **Install DePbo (runtime)**
   * **Install DeOgg (runtime)**
   * If you plan to pack PBOs, install **MakePbo** as part of the same Mikero suite

5. **Link and create wrappers**

   * Click **Link ExtractPbo & DeRap**
   * Click **Create/Repair Wrappers**

6. **Ensure PATH picks up `~/.local/bin`**
   If you see a PATH note in the log, add:

   ```bash
   echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
   source ~/.bashrc
   ```

You are ready. The **Status** row should show Wine, cpbo, and unRap as ✓.

---

## Typical usage

### With the GUI

* **Extract a PBO**

  1. Click **Browse…** next to “PBO file” and choose `SomeMission.Abel.pbo`
  2. Choose an **Output / Mission folder**
  3. Click **Extract via tools (cpbo)**

* **Pack a mission folder**

  1. Set **Output / Mission folder** to your extracted mission directory
  2. Click **Pack folder → .pbo (cpbo)**
  3. Choose a destination like `~/.../MPMissions/SomeMission.Abel.pbo`

* **DeRap configs**

  1. Click **DeRap .bin → .cpp (unRap)**
  2. Select a `.bin`, `.rap`, or `.cfg` file

* **Inject respawn**

  1. Click **Inject Respawn (description.ext)**
  2. Pick your mission folder
  3. A stub is appended to `description.ext`:

     ```cpp
     // --- injected by tool ---
     respawn = 3;
     respawnDelay = 5;
     respawnDialog = 0;
     // --- end injected ---
     ```

     Then place a marker named `respawn_west` (or `respawn_east`, etc.) in the editor.

* **Fallback extractor (uncompressed only)**

  1. Set the PBO and output folder
  2. Click **Fallback: Extract UNCOMPRESSED**
     Use this only if cpbo is not ready and the PBO is not compressed.

### From the shell (wrappers)

Once wrappers are created and your PATH includes `~/.local/bin`:

```bash
# Extract
cpbo -e /path/to/mission.pbo /path/to/output/dir

# Pack (requires MakePbo.exe installed)
cpbo -p /path/to/mission_folder /path/to/output/mission.pbo

# DeRap
unrap /path/to/config.bin
```

Wrappers handle Wine path conversion and run the tools in the correct directory.

---

## Default MPMissions locations

The app tries to find a reasonable default, for example:

```
~/.local/share/Steam/steamapps/common/ARMA Cold War Assault/MPMissions
~/.steam/steam/steamapps/common/Arma Cold War Assault/MPMissions
~/Steam/steamapps/common/Arma Cold War Assault/MPMissions
~/.wine64/drive_c/Program Files (x86)/Bohemia Interactive/Arma Cold War Assault/MPMissions
```

You can always override paths in the GUI.

---

## Troubleshooting

* **Wine shows ✗**

  * Install Wine via the button or:

    ```bash
    sudo apt update
    sudo apt install -y wine-stable winbind cabextract p7zip-full
    ```

* **cpbo or unRap shows ✗**

  * Click **Install ExtractPbo** and **Install DeRap**
  * Then click **Link ExtractPbo & DeRap** and **Create/Repair Wrappers**

* **“Missing runtime DLLs detected”**

  * Install **DePbo (runtime)** and **DeOgg (runtime)** under the same prefix
  * Click **Link ExtractPbo & DeRap** again
  * The app checks for files like `DePbo64.dll` and `DeOgg64.dll` next to the EXEs

* **`MakePbo.exe not found` when packing**

  * Install Mikero **MakePbo** into the same directory as ExtractPbo

* **PATH note about `~/.local/bin`**

  * Add it:

    ```bash
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
    source ~/.bashrc
    ```

* **Installer download fails**

  * Some links may require login or change over time. The log will show HTTP details.
    You can also download installers yourself and run them with Wine in your chosen prefix.

* **Fallback extractor errors**

  * The built-in extractor only supports **uncompressed** PBO entries. For compressed PBOS, use cpbo.

---

## Uninstall

Remove the app data and wrappers:

```bash
rm -rf ~/.local/share/arma_pbo_tools
rm -f  ~/.local/bin/cpbo ~/.local/bin/unrap ~/.local/bin/unpbo
```

This does not remove Wine prefixes or any Mikero tools you installed inside Wine.

---

## Technical details

This section explains what the script is doing behind the scenes.

### Paths and state

* App data directory: `~/.local/share/arma_pbo_tools`

  * `cpbo.path` - absolute path to the chosen ExtractPbo or cpbo EXE
  * `unrap.path` - absolute path to the chosen DeRap/UnRap EXE
  * `wineprefix.path` - the Wine prefix to use
* Wrapper install dir: `~/.local/bin`
  The script writes three small bash scripts: `cpbo`, `unrap`, `unpbo` (stub).

### Wine prefix selection

* Reads `wineprefix.path` or falls back to `WINEPREFIX` or `~/.wine`
* Can create a 64-bit prefix at `~/.wine64` by calling `wineboot` with `WINEARCH=win64`

### Finding the EXEs

* After you run an installer, **Link ExtractPbo & DeRap** calls:

  * `find_best_tool(prefix, target)` which scans `Program Files*/Mikero*/**/*.exe`
  * Scores candidates so that `ExtractPbo.exe` and `DeRap.exe` in `.../bin/` are favored
* Saves the chosen paths to `cpbo.path` and `unrap.path`

### Runtime verification

* `verify_runtime(exe_path, ...)` looks for DLLs next to the EXE:

  * DePbo64.dll or DePbo.dll
  * deOgg64.dll or DeOgg64.dll or deOgg.dll
* If missing, the GUI shows a clear warning with next steps

### Wrappers

The script writes two bash wrappers:

* **`cpbo`**

  * Changes directory to the EXE folder
  * Converts every Unix path to a Wine path via `winepath -w`
    Falls back to `"Z:${p//\//\\}"` if needed
  * If the target EXE is `ExtractPbo.exe`, it **emulates**:

    * `cpbo -e <pbo> [outdir]` by calling `ExtractPbo.exe <pbo> <outdir>`
    * `cpbo -p <folder> <out.pbo>` by calling `MakePbo.exe <folder> <out.pbo>` if present
  * If the target is a real `cpbo.exe`, it passes arguments through

* **`unrap`**

  * Changes directory to the EXE folder
  * Converts all non-flag arguments to Windows paths
  * Executes the EXE via Wine

Both wrappers set `WINEPREFIX` from `~/.local/share/arma_pbo_tools/wineprefix.path` if present.

### GUI threading and logs

* Long operations run on background threads and push text to a `queue.Queue`
* The GUI drains the queue on a timer and appends to a `tk.Text` log pane
* Buttons provide “Copy Log” and “Save Log”

### Fallback extractor

* Implements a minimal `.pbo` reader that supports **uncompressed** entries only:

  * Reads header entries as C-strings, then 20-byte metadata blocks
  * Rejects entries with `packing != 0`
  * Streams each file to the output folder
  * Updates a GUI progress bar using a simple average of file and byte fractions

### Respawn injector

* Opens or creates `description.ext` and removes any lines starting with
  `respawn`, `respawnDelay`, or `respawnDialog`
* Appends:

  ```cpp
  respawn = 3;
  respawnDelay = 5;
  respawnDialog = 0;
  ```
* You still need to add a map marker named `respawn_west` or equivalent in the editor

### Notable files and constants

* Default installer URLs:

  * `EXTRACTPBO_URL`, `DERAP_URL`, `DEPBO_URL`, `DEOGG_URL`
* Default Steam and Wine mission locations in `MPMISSIONS_CANDIDATES`
* `APT_PKGS` for Wine and helpers on Debian/Ubuntu

---

## FAQ

**Does this include Mikero tools?**
No. It helps you install and link them under Wine. You control which version you install and where.

**Can I use a different Wine prefix?**
Yes. Pick any prefix folder, then click **Use This Prefix**.

**Will the wrappers work in fresh terminals?**
Yes, after you add `~/.local/bin` to PATH as shown above.

**Why does fallback extraction fail on some PBOs?**
Those PBOs contain compressed entries. Use cpbo with the proper DePbo and DeOgg runtimes installed.

---

## License

This script is provided as-is. You are responsible for complying with the licenses of any third-party tools you install and run with it.
