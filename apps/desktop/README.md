# MindWeaver Desktop

Tauri-based desktop shell wrapping the web frontend (`apps/web`) and managing
the local backend (`services/api`) as a sidecar process.

## Status (Stage 18)

Packaging scaffolding. The Tauri project layout is prepared; building an
installer requires the Rust toolchain (`cargo tauri build`).

## Layout

- `src-tauri/tauri.conf.json` - window config, sidecar registration
- `src-tauri/Cargo.toml`      - Rust shell dependencies
- `src/main.rs`               - shell entry: spawns API sidecar, opens window

## Development

```sh
# 1. start the stack manually (dev mode uses devUrl)
make dev-api
make dev-web

# 2. open the desktop shell against it
cd apps/desktop && cargo tauri dev
```

## Building an installer

```sh
uv sync --project services/api            # lockfile for sidecar bundling
npm run web:build                          # frontend assets
cd apps/desktop && cargo tauri build       # produces .deb/.AppImage/.msi/.dmg
```
