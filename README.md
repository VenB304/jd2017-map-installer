# Just Dance 2017 Map Installer

A Windows desktop application that automates importing custom maps into **Just Dance 2017 PC**. Built on the proven modular architecture of the [jd2021-map-installer](https://github.com/VenB304/jd2021-map-installer), adapted for JD2017's UbiArt engine requirements.

## ✨ Features

- **Zero Legacy Shell-outs**: IPK packaging, texture conversion, and FAT rebuilding implemented natively in Python
- **Pure Python Texture Pipeline**: Lossless Switch/WiiU→PC texture conversion and uncompressed DDS compilation without external CLI tools
- **Automated Scene Generation**: Programmatic recreation of AugustoDoidin's PC MainScene Maker
- **SkuScene Auto-Patching**: Automatic Actor injection into both `skuscene_maps_pc_all` and `skuscene_maps_pc_ww` ISC files
- **Secure FAT Rebuilding**: Native `secure_fat.gf` index generation after each map installation
- **Multi-Source Downloads**: Supports JDU, JDNext, JDLO, and manual file sources
- **Dark-Themed PyQt6 GUI**: Modern dashboard with real-time logging and progress tracking

## 🚀 Quick Start

```bash
# 1. Run setup (installs Python deps, Playwright, vgmstream)
setup.bat

# 2. Launch the installer
RUN.bat
```

## 📋 Prerequisites

- **Just Dance 2017 PC** installation
- Delete bundles 0–96 from the game directory (keep `bundle_pc.ipk` and `bundle_logic.ipk`)
- Python 3.12+ (auto-provisioned by `setup.bat` if missing)

## 🏗️ Architecture

```
jd2017_installer/
├── core/           # Config, exceptions, logging, path discovery
├── extractors/     # IPK unpacking, JDU/JDLO/JDNext downloaders
├── parsers/        # Binary CKD parsing, data normalization
├── installers/     # Scene generation, texture encoding, IPK packing,
│                   #   SkuScene patching, secure FAT building
├── ui/             # PyQt6 dashboard and worker threads
└── utils/          # Shared helpers
```

## 🙏 Modding Community & Technical Credits

This project natively integrates and builds upon the excellent reverse-engineered formulas, structures, and script tools developed by the Just Dance PC modding community:

* **AugustoDoidin (augusto#6995 on Discord)**: Developer of the original `PC_MainScene_Maker_by_AugustoDoidin.py`. We have natively implemented this scene generator formula to create all required UbiArt scene, sequence, and template configurations for Just Dance 2017 PC.
* **Wukko (https://github.com/wukko)**: Developer of the `ubiart-secure-fat` library. We have natively integrated the `generateSecureFat.py` indexing algorithm to construct `secure_fat.gf` natively.
* **BLDS**: Developer of `Just Dance Tools 1.9.0`. We natively integrated the UbiArt PC texture wrapper logic (`scriptDDStoCKD.bms` / `scriptCKDtoRAW.bms`) and VGMstream/Oggenc converter formulas inside our pure Python lossless converters and uncompressed texture compilers.
* **PartyService (https://github.com/PartyService)**: Authors of `ubiart-archive-tools` and the QuickBMS IPK script. We utilized the specifications of the UbiArt IPK format to build our pure Python native UbiArt IPK Reader & Packer.
* **rama0dev (https://github.com/rama0dev)**: Developer of Just Dance Helper Discord Bot, from which asset downloads, coach vectors, and webm DASH video qualities are fetched.
* **Ovo and the JDLO Team (https://jdlo.ovosimpatico.com/)**: Developers of the Just Dance Legacy Online (JDLO) servers and custom Just Dance 2017 PC CDN mods, from which customized catalogs are scraped.

## 📄 License

This project is provided as-is for educational and personal modding purposes.
