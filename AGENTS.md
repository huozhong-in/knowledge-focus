# AGENTS.md

This file provides guidance to Code Agent when working with code in this repository.

## Commands

- `tauri-app/dev.sh`: Start the development server
- `tauri-app/build.sh`: Build the application (TypeScript compilation + Vite build)

## Architecture

- Frontend: React + Vite + TypeScript, with Radix UI and TailwindCSS for styling
- Backend: Tauri (Rust) with Python API integration
- State management: Zustand
- Data visualization: Recharts
- Localization: i18next
- File management: Tauri plugins for file operations

### Key Directories

- `tauri-app/`: Frontend and Tauri configuration
- `tauri-app/src-tauri/`: Tauri backend and configuration
- `api/`: Python backend for file and database management. `api_standalone.sh` for standalone mode,not launched by Tauri as sidecar
- `~/Library/Application\ Support/knowledge-focus.huozhong.in`: Default data directory on macOS, where the application stores its data files `knowledge-focus.db`
- `~/Library/Application\ Support/knowledge-focus.huozhong.in/logs/*.log`: Log files for the Python API, useful for debugging and monitoring

Note: The project uses Bun as a package manager (evident from `beforeDevCommand` and `beforeBuildCommand` in Tauri config).
