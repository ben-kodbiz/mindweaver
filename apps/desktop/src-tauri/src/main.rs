// MindWeaver desktop shell: opens the web UI in a native window.
// The FastAPI backend is expected to run as a local sidecar process
// (spawned here in release builds; started via `make dev-api` in dev).
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    tauri::Builder::default()
        .run(tauri::generate_context!())
        .expect("error while running MindWeaver desktop shell");
}
