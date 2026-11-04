// App de escritorio nativa SmartSuite (Tauri v2)
#![cfg_attr(
    all(not(debug_assertions), target_os = "windows"),
    windows_subsystem = "windows"
)]

use std::io::{BufRead, Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Mutex, OnceLock};
use std::time::{Duration, Instant};

#[cfg(windows)]
use std::os::windows::process::CommandExt;

use tauri::{Emitter, Manager, RunEvent, Url, WindowEvent};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;
#[cfg(windows)]
const CREATE_NEW_PROCESS_GROUP: u32 = 0x0000_0200;
const SHUTDOWN_WAIT_ATTEMPTS: u32 = 25;

const OLLAMA_PORT: u16 = 11434;
const OLLAMA_HOST: &str = "127.0.0.1:11434";
const OLLAMA_API: &str = "http://127.0.0.1:11434";

#[derive(serde::Deserialize, Clone)]
#[serde(rename_all = "camelCase")]
struct Tier {
    max_ram_gb: f64,
    model: String,
    #[serde(default)]
    extra_models: Vec<String>,
    #[serde(default)]
    id: String,
    #[serde(default)]
    label: String,
}

#[derive(serde::Deserialize, Clone)]
#[serde(rename_all = "camelCase")]
struct AccessPolicy {
    #[serde(default = "default_block_below_gb")]
    block_below_gb: f64,
    #[serde(default = "default_warn_below_gb")]
    warn_below_gb: f64,
}

fn default_block_below_gb() -> f64 {
    7.0
}

fn default_warn_below_gb() -> f64 {
    13.0
}

impl Default for AccessPolicy {
    fn default() -> Self {
        Self {
            block_below_gb: 7.0,
            warn_below_gb: 13.0,
        }
    }
}

#[derive(serde::Deserialize)]
#[serde(rename_all = "camelCase")]
struct AppConfig {
    product_name: String,
    data_dir_name: String,
    ollama_tiers: Vec<Tier>,
    /// Legacy. SmartCaja no baja extras globales: solo extraModels del tramo (vacío).
    #[serde(default)]
    #[allow(dead_code)]
    extra_models: Vec<String>,
    #[serde(default)]
    access: AccessPolicy,
}

static APP_CONFIG_JSON: &str = include_str!("../appconfig.json");

fn app_config() -> &'static AppConfig {
    static CFG: OnceLock<AppConfig> = OnceLock::new();
    CFG.get_or_init(|| serde_json::from_str(APP_CONFIG_JSON).expect("appconfig.json invalido"))
}

struct BackendState(Mutex<Option<CommandChild>>);
struct OllamaChild {
    pid: u32,
    child: Child,
}
struct OllamaState(Mutex<Option<OllamaChild>>);
struct ShutdownState(AtomicBool);
struct BootstrapStarted(Mutex<Instant>);
#[derive(Clone)]
struct ShutdownTarget {
    label: &'static str,
    pid: u32,
    port: Option<u16>,
}
struct PendingStops(Mutex<Vec<ShutdownTarget>>);
struct Navigated(Mutex<bool>);
struct LastProbe(Mutex<String>);

#[derive(Clone, serde::Serialize)]
#[serde(rename_all = "camelCase")]
struct Status {
    phase: String,
    message: String,
    percent: i32,
    backend_url: Option<String>,
    can_continue: bool,
    ollama_done: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    backend_error: Option<String>,
}

impl Status {
    fn initial() -> Self {
        Status {
            phase: "starting".into(),
            message: "Iniciando servicios...".into(),
            percent: -1,
            backend_url: None,
            can_continue: false,
            ollama_done: false,
            backend_error: None,
        }
    }
}

struct AppStatus(Mutex<Status>);
struct BackendPort(u16);

fn persist_status_snapshot(snapshot: &Status) {
    let path = user_data_dir().join("desktop_status.json");
    if let Ok(json) = serde_json::to_string(snapshot) {
        let _ = std::fs::write(path, json);
    }
}

fn update_status(app: &tauri::AppHandle, f: impl FnOnce(&mut Status)) {
    let snapshot = {
        let state = app.state::<AppStatus>();
        let mut s = state.0.lock().unwrap();
        f(&mut s);
        s.clone()
    };
    persist_status_snapshot(&snapshot);
    let _ = app.emit("status", snapshot);
}

#[tauri::command]
fn current_status(state: tauri::State<AppStatus>) -> Status {
    state.0.lock().unwrap().clone()
}

#[tauri::command]
fn navigate_to_backend(
    app: tauri::AppHandle,
    port: tauri::State<BackendPort>,
) -> Result<(), String> {
    open_splash_on_backend(&app, port.0)
}

#[tauri::command]
fn retry_backend(app: tauri::AppHandle, port: tauri::State<BackendPort>) -> Result<String, String> {
    let p = port.0;
    if try_mark_backend_ready(&app, p) {
        navigate_main_to_backend(&app, p)?;
        Ok(backend_app_url(p))
    } else {
        let detail = app.state::<LastProbe>().0.lock().unwrap().clone();
        Err(format!(
            "El servidor aun no responde con la UI. Diagnostico: {}",
            detail
        ))
    }
}

fn hidden_command(program: impl AsRef<std::ffi::OsStr>) -> Command {
    let mut cmd = Command::new(program);
    #[cfg(windows)]
    cmd.creation_flags(CREATE_NO_WINDOW);
    cmd
}

fn ollama_command() -> Command {
    hidden_command("ollama")
}

fn ollama_command_at(bin: &Path) -> Command {
    hidden_command(bin)
}

/// Shared suite engine + models for SmartGastos / SmartRedes / SmartCaja.
const SUITE_DIR_NAME: &str = "SmartSuite";
const LEGACY_APP_DIR_NAMES: &[&str] = &["SmartGastos", "SmartRedes", "SmartCaja"];
const OWNED_PID_FILE: &str = "owned.pid";
const MIGRATE_LOCK_FILE: &str = "migrate.lock";

fn platform_data_root() -> PathBuf {
    #[cfg(target_os = "windows")]
    {
        std::env::var("APPDATA")
            .map(PathBuf::from)
            .unwrap_or_else(|_| home_dir().join("AppData").join("Roaming"))
    }
    #[cfg(target_os = "macos")]
    {
        home_dir()
            .join("Library")
            .join("Application Support")
    }
    #[cfg(all(unix, not(target_os = "macos")))]
    {
        std::env::var("XDG_DATA_HOME")
            .map(PathBuf::from)
            .unwrap_or_else(|_| home_dir().join(".local").join("share"))
    }
}

fn ollama_engine_home() -> PathBuf {
    platform_data_root().join(SUITE_DIR_NAME).join("ollama")
}

/// Per-app markers (active model / profile) stay under the app data dir.
fn ollama_app_state_dir() -> PathBuf {
    user_data_dir().join("ollama")
}

fn ollama_runtime_dir() -> PathBuf {
    ollama_engine_home().join("runtime")
}

fn ollama_models_dir() -> PathBuf {
    ollama_engine_home().join("models")
}

fn ollama_download_dir() -> PathBuf {
    ollama_engine_home().join("download")
}

fn ollama_owned_pid_path() -> PathBuf {
    ollama_engine_home().join(OWNED_PID_FILE)
}

fn legacy_app_base_dir(app_name: &str) -> PathBuf {
    platform_data_root().join(app_name)
}

fn legacy_ollama_homes() -> Vec<PathBuf> {
    LEGACY_APP_DIR_NAMES
        .iter()
        .map(|name| legacy_app_base_dir(name).join("ollama"))
        .collect()
}

fn ollama_bin_name() -> &'static str {
    #[cfg(windows)]
    {
        "ollama.exe"
    }
    #[cfg(not(windows))]
    {
        "ollama"
    }
}

fn is_ollama_binary(path: &Path) -> bool {
    if !path.is_file() {
        return false;
    }
    let Some(name) = path.file_name().and_then(|n| n.to_str()) else {
        return false;
    };
    // active_model.txt lives beside the engine in legacy homes; it is not a binary.
    if name.eq_ignore_ascii_case("active_model.txt") {
        return false;
    }
    name.eq_ignore_ascii_case(ollama_bin_name())
}

fn skip_ollama_walk_dir(name: &std::ffi::OsStr) -> bool {
    name.to_str()
        .map(|n| n.eq_ignore_ascii_case("models"))
        .unwrap_or(false)
}

fn find_portable_ollama(root: &Path) -> Option<PathBuf> {
    if !root.exists() {
        return None;
    }
    let preferred = [
        root.join(ollama_bin_name()),
        root.join("bin").join(ollama_bin_name()),
        root.join("runtime").join(ollama_bin_name()),
        root.join("runtime").join("bin").join(ollama_bin_name()),
        root.join("Ollama").join(ollama_bin_name()),
    ];
    for p in preferred {
        if is_ollama_binary(&p) {
            return Some(p);
        }
    }
    fn walk(dir: &Path, depth: u8) -> Option<PathBuf> {
        if depth == 0 {
            return None;
        }
        let entries = std::fs::read_dir(dir).ok()?;
        let mut dirs = Vec::new();
        for ent in entries.flatten() {
            let p = ent.path();
            if is_ollama_binary(&p) {
                return Some(p);
            }
            if p.is_dir() {
                let name = p.file_name().unwrap_or_default();
                if skip_ollama_walk_dir(name) {
                    continue;
                }
                dirs.push(p);
            }
        }
        for d in dirs {
            if let Some(found) = walk(&d, depth - 1) {
                return Some(found);
            }
        }
        None
    }
    walk(root, 5)
}

fn paths_same_file(a: &Path, b: &Path) -> bool {
    if let (Ok(ca), Ok(cb)) = (std::fs::canonicalize(a), std::fs::canonicalize(b)) {
        return ca == cb;
    }
    #[cfg(windows)]
    {
        a.to_string_lossy().eq_ignore_ascii_case(&b.to_string_lossy())
    }
    #[cfg(not(windows))]
    {
        a == b
    }
}

fn binary_image_is_running(bin: &Path) -> bool {
    let mut system = sysinfo::System::new();
    system.refresh_processes(sysinfo::ProcessesToUpdate::All, true);
    for proc in system.processes().values() {
        if let Some(exe) = proc.exe() {
            if paths_same_file(exe, bin) {
                return true;
            }
        }
    }
    false
}

fn should_skip_engine_migrate_entry(name: &str) -> bool {
    name.eq_ignore_ascii_case("models")
        || name.eq_ignore_ascii_case("active_model.txt")
        || name.eq_ignore_ascii_case("active_profile.json")
        || name.eq_ignore_ascii_case(OWNED_PID_FILE)
        || name.eq_ignore_ascii_case("logs")
        || name.eq_ignore_ascii_case(MIGRATE_LOCK_FILE)
}

fn copy_dir_recursive(src: &Path, dest: &Path) -> Result<(), String> {
    std::fs::create_dir_all(dest).map_err(|e| e.to_string())?;
    for ent in std::fs::read_dir(src).map_err(|e| e.to_string())? {
        let ent = ent.map_err(|e| e.to_string())?;
        let from = ent.path();
        let to = dest.join(ent.file_name());
        if from.is_dir() {
            copy_dir_recursive(&from, &to)?;
        } else {
            std::fs::copy(&from, &to).map_err(|e| e.to_string())?;
        }
    }
    Ok(())
}

fn move_path_preserving(src: &Path, dest: &Path) -> Result<(), String> {
    if let Some(parent) = dest.parent() {
        std::fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    if dest.exists() {
        if src.is_dir() && dest.is_dir() {
            for ent in std::fs::read_dir(src).map_err(|e| e.to_string())? {
                let ent = ent.map_err(|e| e.to_string())?;
                move_path_preserving(&ent.path(), &dest.join(ent.file_name()))?;
            }
            let _ = std::fs::remove_dir(src);
            return Ok(());
        }
        // Shared file already exists: keep it and leave the legacy source.
        return Ok(());
    }
    match std::fs::rename(src, dest) {
        Ok(()) => Ok(()),
        Err(_) => {
            if src.is_dir() {
                copy_dir_recursive(src, dest)?;
                std::fs::remove_dir_all(src).map_err(|e| e.to_string())?;
                Ok(())
            } else {
                std::fs::copy(src, dest).map_err(|e| e.to_string())?;
                std::fs::remove_file(src).map_err(|e| e.to_string())?;
                Ok(())
            }
        }
    }
}

fn adopt_engine_tree(legacy_home: &Path, shared: &Path) -> Result<(), String> {
    let _ = std::fs::create_dir_all(shared);
    for ent in std::fs::read_dir(legacy_home).map_err(|e| e.to_string())? {
        let ent = ent.map_err(|e| e.to_string())?;
        let name = ent.file_name();
        let name_s = name.to_string_lossy();
        if should_skip_engine_migrate_entry(&name_s) {
            continue;
        }
        move_path_preserving(&ent.path(), &shared.join(&name))?;
    }
    Ok(())
}

fn adopt_legacy_engine_tree(legacy_home: &Path) -> Result<(), String> {
    let shared = ollama_engine_home();
    ollama_log(&format!(
        "Adoptando motor legacy {} -> {}",
        legacy_home.display(),
        shared.display()
    ));
    adopt_engine_tree(legacy_home, &shared)
}

/// True when no portable binary exists yet, so the zip/tgz download may run.
fn portable_zip_needed(shared: &Path, legacy_homes: &[PathBuf]) -> bool {
    if find_portable_ollama(shared).is_some() {
        return false;
    }
    for home in legacy_homes {
        if find_portable_ollama(home).is_some() {
            return false;
        }
    }
    true
}

fn resolve_portable_ollama_binary() -> Option<PathBuf> {
    let shared = ollama_engine_home();
    if let Some(bin) = find_portable_ollama(&shared) {
        return Some(bin);
    }
    for legacy in legacy_ollama_homes() {
        if !legacy.exists() || paths_same_file(&legacy, &shared) {
            continue;
        }
        let Some(bin) = find_portable_ollama(&legacy) else {
            continue;
        };
        if binary_image_is_running(&bin) {
            ollama_log(&format!(
                "Usando Ollama legacy en ejecucion (sin mover ni descargar): {}",
                bin.display()
            ));
            return Some(bin);
        }
        match adopt_legacy_engine_tree(&legacy) {
            Ok(()) => {
                if let Some(moved) = find_portable_ollama(&shared) {
                    return Some(moved);
                }
            }
            Err(e) => ollama_log(&format!("No se pudo adoptar motor legacy: {}", e)),
        }
        return Some(bin);
    }
    None
}

fn migrate_lock_is_stale(lock_path: &Path) -> bool {
    let Ok(text) = std::fs::read_to_string(lock_path) else {
        return false;
    };
    let Ok(pid) = text.trim().parse::<u32>() else {
        return false;
    };
    pid != 0 && !process_is_alive(pid)
}

fn try_acquire_migrate_lock(lock_path: &Path) -> bool {
    let started = Instant::now();
    loop {
        match std::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(lock_path)
        {
            Ok(mut file) => {
                let _ = writeln!(file, "{}", std::process::id());
                return true;
            }
            Err(_) => {
                if migrate_lock_is_stale(lock_path) {
                    let _ = std::fs::remove_file(lock_path);
                    if started.elapsed() >= Duration::from_secs(60) {
                        ollama_log("migrate.lock ocupado >60s; se continua sin bloqueo exclusivo");
                        return false;
                    }
                    continue;
                }
                if started.elapsed() >= Duration::from_secs(60) {
                    ollama_log("migrate.lock ocupado >60s; se continua sin bloqueo exclusivo");
                    return false;
                }
                std::thread::sleep(Duration::from_millis(200));
            }
        }
    }
}

fn release_migrate_lock(lock_path: &Path, held: bool) {
    if held {
        let _ = std::fs::remove_file(lock_path);
    }
}

fn merge_model_entry(src: &Path, dest: &Path) {
    if !src.is_file() {
        return;
    }
    let Ok(src_meta) = std::fs::metadata(src) else {
        return;
    };
    let src_len = src_meta.len();
    if let Some(parent) = dest.parent() {
        let _ = std::fs::create_dir_all(parent);
    }
    if dest.exists() {
        if let Ok(dest_meta) = std::fs::metadata(dest) {
            if dest_meta.is_file() && dest_meta.len() == src_len {
                let _ = std::fs::remove_file(src);
            }
        }
        return;
    }
    if std::fs::rename(src, dest).is_ok() {
        return;
    }
    let Some(name) = dest.file_name().and_then(|n| n.to_str()) else {
        return;
    };
    let tmp = dest.with_file_name(format!("{name}.partial-migrate"));
    if std::fs::copy(src, &tmp).is_err() {
        let _ = std::fs::remove_file(&tmp);
        return;
    }
    if dest.exists() {
        let _ = std::fs::remove_file(&tmp);
        if let Ok(dest_meta) = std::fs::metadata(dest) {
            if dest_meta.is_file() && dest_meta.len() == src_len {
                let _ = std::fs::remove_file(src);
            }
        }
        return;
    }
    if std::fs::rename(&tmp, dest).is_err() {
        let _ = std::fs::remove_file(&tmp);
        return;
    }
    let _ = std::fs::remove_file(src);
}

fn walk_merge_models(src: &Path, dest_models: &Path, rel: &Path) {
    let dest = dest_models.join(rel);
    if src.is_file() {
        merge_model_entry(src, &dest);
        return;
    }
    if !src.is_dir() {
        return;
    }
    let _ = std::fs::create_dir_all(&dest);
    let Ok(entries) = std::fs::read_dir(src) else {
        return;
    };
    for ent in entries.flatten() {
        walk_merge_models(&ent.path(), dest_models, &rel.join(ent.file_name()));
    }
}

fn import_models_tree(src_models: &Path, dest_models: &Path) {
    if !src_models.is_dir() {
        return;
    }
    let _ = std::fs::create_dir_all(dest_models);
    for sub in ["blobs", "manifests"] {
        let src_sub = src_models.join(sub);
        if src_sub.exists() {
            walk_merge_models(&src_sub, dest_models, Path::new(sub));
        }
    }
}

fn import_models_from_home(src_models: &Path, dest_models: &Path) {
    if !src_models.is_dir() || paths_same_file(src_models, dest_models) {
        return;
    }
    ollama_log(&format!(
        "Importando modelos {} -> {}",
        src_models.display(),
        dest_models.display()
    ));
    import_models_tree(src_models, dest_models);
}

fn import_legacy_models_into_shared() {
    let dest = ollama_models_dir();
    let engine = ollama_engine_home();
    let _ = std::fs::create_dir_all(&engine);
    let _ = std::fs::create_dir_all(&dest);
    let lock_path = engine.join(MIGRATE_LOCK_FILE);
    let held = try_acquire_migrate_lock(&lock_path);
    let mut sources: Vec<PathBuf> = legacy_ollama_homes()
        .into_iter()
        .map(|home| home.join("models"))
        .collect();
    let app_models = ollama_app_state_dir().join("models");
    if !sources.iter().any(|path| paths_same_file(path, &app_models)) {
        sources.push(app_models);
    }
    for src in sources {
        import_models_from_home(&src, &dest);
    }
    release_migrate_lock(&lock_path, held);
}

fn ollama_tags_include(body: &str, model: &str) -> bool {
    let Ok(value) = serde_json::from_str::<serde_json::Value>(body) else {
        return false;
    };
    let Some(models) = value.get("models").and_then(|m| m.as_array()) else {
        return false;
    };
    models.iter().any(|entry| {
        entry.get("name").and_then(|name| name.as_str()) == Some(model)
    })
}

fn fetch_ollama_tags() -> Option<String> {
    let resp = ureq::get(&format!("{}/api/tags", OLLAMA_API))
        .timeout(Duration::from_secs(3))
        .call()
        .ok()?;
    if resp.status() != 200 {
        return None;
    }
    resp.into_string().ok()
}

fn ensure_unix_executable(path: &Path) {
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        if let Ok(meta) = std::fs::metadata(path) {
            let mut perms = meta.permissions();
            perms.set_mode(perms.mode() | 0o755);
            let _ = std::fs::set_permissions(path, perms);
        }
    }
    let _ = path;
}

fn binary_runs(bin: &Path) -> bool {
    ollama_command_at(bin)
        .arg("--version")
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .map(|s| s.success())
        .unwrap_or(false)
}

fn system_ollama_available() -> bool {
    ollama_command()
        .arg("--version")
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .map(|s| s.success())
        .unwrap_or(false)
}

fn ollama_http_agent() -> ureq::Agent {
    ureq::AgentBuilder::new()
        .timeout_connect(Duration::from_secs(30))
        .timeout_read(Duration::from_secs(6 * 3600))
        .timeout_write(Duration::from_secs(120))
        .user_agent("SmartCaja-CCS portable-ollama")
        .build()
}

fn ollama_http_healthy() -> bool {
    match ureq::get(&format!("{}/api/tags", OLLAMA_API))
        .timeout(Duration::from_secs(3))
        .call()
    {
        Ok(r) => r.status() == 200,
        Err(_) => false,
    }
}

fn official_ollama_archives() -> Vec<(&'static str, &'static str)> {
    // Official portable archives (zip / tgz). Current Linux latest is tar.zst;
    // tgz is tried first and skipped on 404. Never run the Windows system installer.
    let mut urls = Vec::new();
    if cfg!(all(windows, target_arch = "x86_64")) {
        urls.push((
            "https://github.com/ollama/ollama/releases/latest/download/ollama-windows-amd64.zip",
            "ollama-windows-amd64.zip",
        ));
    } else if cfg!(all(windows, target_arch = "aarch64")) {
        urls.push((
            "https://github.com/ollama/ollama/releases/latest/download/ollama-windows-arm64.zip",
            "ollama-windows-arm64.zip",
        ));
    } else if cfg!(all(target_os = "linux", target_arch = "x86_64")) {
        urls.push((
            "https://github.com/ollama/ollama/releases/latest/download/ollama-linux-amd64.tgz",
            "ollama-linux-amd64.tgz",
        ));
        urls.push((
            "https://github.com/ollama/ollama/releases/latest/download/ollama-linux-amd64.tar.zst",
            "ollama-linux-amd64.tar.zst",
        ));
    } else if cfg!(all(target_os = "linux", target_arch = "aarch64")) {
        urls.push((
            "https://github.com/ollama/ollama/releases/latest/download/ollama-linux-arm64.tgz",
            "ollama-linux-arm64.tgz",
        ));
        urls.push((
            "https://github.com/ollama/ollama/releases/latest/download/ollama-linux-arm64.tar.zst",
            "ollama-linux-arm64.tar.zst",
        ));
    } else if cfg!(target_os = "macos") {
        urls.push((
            "https://github.com/ollama/ollama/releases/latest/download/ollama-darwin.tgz",
            "ollama-darwin.tgz",
        ));
    }
    urls
}

fn prepend_dir_to_path(dir: &Path) {
    let extra = dir.to_string_lossy().into_owned();
    let merged = match std::env::var_os("PATH") {
        Some(existing) => {
            let mut v = std::ffi::OsString::from(extra);
            #[cfg(windows)]
            v.push(";");
            #[cfg(not(windows))]
            v.push(":");
            v.push(existing);
            v
        }
        None => extra.into(),
    };
    std::env::set_var("PATH", merged);
}

fn apply_portable_env(bin: &Path) {
    if let Some(dir) = bin.parent() {
        prepend_dir_to_path(dir);
        if dir.file_name().and_then(|n| n.to_str()) == Some("bin") {
            if let Some(root) = dir.parent() {
                prepend_dir_to_path(root);
            }
        }
    }
    let models = ollama_models_dir();
    let _ = std::fs::create_dir_all(&models);
    std::env::set_var("OLLAMA_MODELS", models);
    std::env::set_var("OLLAMA_HOST", OLLAMA_HOST);
}

fn configure_serve_command(cmd: &mut Command, bin: Option<&Path>) {
    let models = ollama_models_dir();
    let _ = std::fs::create_dir_all(&models);
    if let Some(path) = bin {
        apply_portable_env(path);
    }
    cmd.arg("serve")
        .env("OLLAMA_HOST", OLLAMA_HOST)
        .env("OLLAMA_MODELS", models)
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    #[cfg(windows)]
    {
        cmd.creation_flags(CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP);
    }
    #[cfg(unix)]
    {
        use std::os::unix::process::CommandExt;
        cmd.process_group(0);
    }
}

fn record_owned_ollama(app: &tauri::AppHandle, child: Child) {
    let pid = child.id();
    let home = ollama_engine_home();
    let _ = std::fs::create_dir_all(&home);
    let _ = std::fs::write(ollama_owned_pid_path(), format!("{pid}\n"));
    let ollama_state = app.state::<OllamaState>();
    *ollama_state.0.lock().unwrap() = Some(OllamaChild { pid, child });
    ollama_log(&format!(
        "Ollama compartido SmartSuite iniciado (pid {pid}); permanece al cerrar {}",
        app_config().product_name
    ));
}

fn spawn_owned_ollama(app: &tauri::AppHandle, bin: Option<&Path>) -> bool {
    let mut cmd = match bin {
        Some(path) => ollama_command_at(path),
        None => ollama_command(),
    };
    configure_serve_command(&mut cmd, bin);
    match cmd.spawn() {
        Ok(child) => {
            record_owned_ollama(app, child);
            true
        }
        Err(e) => {
            ollama_log(&format!("No se pudo iniciar ollama serve: {}", e));
            false
        }
    }
}

fn wait_for_healthy_ollama(attempts: u32) -> bool {
    for _ in 0..attempts {
        if ollama_http_healthy() {
            return true;
        }
        std::thread::sleep(Duration::from_millis(500));
    }
    false
}

fn start_and_wait_ollama(app: &tauri::AppHandle, bin: Option<&Path>, message: &str) -> bool {
    update_status(app, |s| {
        s.phase = "ollama".into();
        s.message = message.into();
        s.percent = -1;
    });
    if !spawn_owned_ollama(app, bin) {
        return false;
    }
    let ok = wait_for_healthy_ollama(40);
    if ok {
        ollama_log(&format!(
            "Ollama HTTP API lista en 127.0.0.1:{}",
            OLLAMA_PORT
        ));
    } else {
        ollama_log("Ollama arranco pero /api/tags no respondio a tiempo");
    }
    ok
}

fn extract_archive(archive: &Path, dest: &Path) -> Result<(), String> {
    let _ = std::fs::create_dir_all(dest);
    let name = archive
        .file_name()
        .map(|s| s.to_string_lossy().to_lowercase())
        .unwrap_or_default();
    let archive_s = archive.to_string_lossy().into_owned();
    let dest_s = dest.to_string_lossy().into_owned();

    let run = |mut cmd: Command| -> Result<(), String> {
        let status = cmd
            .stdout(Stdio::null())
            .stderr(Stdio::piped())
            .status()
            .map_err(|e| format!("no se pudo extraer: {}", e))?;
        if status.success() {
            Ok(())
        } else {
            Err(format!("extractor salio con {}", status))
        }
    };

    if name.ends_with(".zip") {
        let mut tar = hidden_command("tar");
        tar.args(["-xf", &archive_s, "-C", &dest_s]);
        if tar.status().map(|s| s.success()).unwrap_or(false) {
            return Ok(());
        }
        #[cfg(windows)]
        {
            let script = format!(
                "Expand-Archive -LiteralPath '{}' -DestinationPath '{}' -Force",
                archive_s.replace('\'', "''"),
                dest_s.replace('\'', "''")
            );
            let mut cmd = hidden_command("powershell");
            cmd.args([
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                &script,
            ]);
            return run(cmd);
        }
        #[cfg(not(windows))]
        {
            return Err("no hay extractor zip".into());
        }
    }

    if name.ends_with(".tar.zst") || name.ends_with(".tzst") {
        let mut cmd = hidden_command("tar");
        cmd.args(["--zstd", "-xf", &archive_s, "-C", &dest_s]);
        if run(cmd).is_ok() {
            return Ok(());
        }
        let piped = format!(
            "zstd -dc '{}' | tar -xf - -C '{}'",
            archive_s.replace('\'', "'\\''"),
            dest_s.replace('\'', "'\\''")
        );
        let mut cmd = hidden_command("sh");
        cmd.args(["-c", &piped]);
        return run(cmd);
    }

    if name.ends_with(".tgz") || name.ends_with(".tar.gz") {
        let mut cmd = hidden_command("tar");
        cmd.args(["-xzf", &archive_s, "-C", &dest_s]);
        return run(cmd);
    }

    if name.ends_with(".tar") {
        let mut cmd = hidden_command("tar");
        cmd.args(["-xf", &archive_s, "-C", &dest_s]);
        return run(cmd);
    }

    Err(format!("formato de archivo no soportado: {}", name))
}

fn download_url_with_progress(
    app: &tauri::AppHandle,
    url: &str,
    dest: &Path,
) -> Result<(), String> {
    if let Some(parent) = dest.parent() {
        let _ = std::fs::create_dir_all(parent);
    }
    ollama_log(&format!("Descargando {}", url));
    let resp = ollama_http_agent()
        .get(url)
        .call()
        .map_err(|e| format!("descarga Ollama: {}", e))?;
    if resp.status() >= 400 {
        return Err(format!("descarga Ollama HTTP {}", resp.status()));
    }
    let total = resp
        .header("Content-Length")
        .and_then(|v| v.parse::<u64>().ok())
        .unwrap_or(0);
    let mut reader = resp.into_reader();
    let tmp = dest.with_extension("partial");
    let mut file =
        std::fs::File::create(&tmp).map_err(|e| format!("no se pudo crear descarga: {}", e))?;
    let mut buf = [0u8; 64 * 1024];
    let mut copied: u64 = 0;
    let mut last_pct: i32 = -1;
    loop {
        let n = reader
            .read(&mut buf)
            .map_err(|e| format!("lectura descarga: {}", e))?;
        if n == 0 {
            break;
        }
        file.write_all(&buf[..n])
            .map_err(|e| format!("escritura descarga: {}", e))?;
        copied += n as u64;
        let pct: i32 = if total > 0 {
            ((copied.min(total) * 100) / total) as i32
        } else {
            -1
        };
        if pct != last_pct {
            last_pct = pct;
            let msg = if pct >= 0 {
                format!("Descargando Ollama (motor de IA) - {}%", pct)
            } else {
                format!(
                    "Descargando Ollama (motor de IA) - {} MB...",
                    copied / (1024 * 1024)
                )
            };
            update_status(app, |s| {
                s.phase = "downloading".into();
                s.message = msg;
                s.percent = pct;
            });
        }
    }
    drop(file);
    std::fs::rename(&tmp, dest).map_err(|e| format!("no se pudo finalizar descarga: {}", e))?;
    Ok(())
}

fn install_portable_ollama(app: &tauri::AppHandle) -> Result<PathBuf, String> {
    let archives = official_ollama_archives();
    if archives.is_empty() {
        return Err("no hay paquete portable de Ollama para esta plataforma".into());
    }
    let download_dir = ollama_download_dir();
    let runtime = ollama_runtime_dir();
    let _ = std::fs::create_dir_all(&download_dir);
    let mut last_err = String::from("sin intentos");
    for (url, filename) in archives {
        update_status(app, |s| {
            s.phase = "downloading".into();
            s.message = "Descargando Ollama (motor de IA portatil)...".into();
            s.percent = -1;
        });
        let archive = download_dir.join(filename);
        match download_url_with_progress(app, url, &archive) {
            Ok(()) => {
                update_status(app, |s| {
                    s.phase = "ollama".into();
                    s.message = "Extrayendo Ollama...".into();
                    s.percent = -1;
                });
                ollama_log(&format!("Extrayendo {} -> {}", archive.display(), runtime.display()));
                let _ = std::fs::remove_dir_all(&runtime);
                let _ = std::fs::create_dir_all(&runtime);
                match extract_archive(&archive, &runtime) {
                    Ok(()) => {
                        if let Some(bin) = find_portable_ollama(&runtime) {
                            ensure_unix_executable(&bin);
                            if binary_runs(&bin) {
                                let _ = std::fs::remove_file(&archive);
                                ollama_log(&format!("Ollama portable listo: {}", bin.display()));
                                return Ok(bin);
                            }
                            last_err = format!("binario extraido no ejecuta: {}", bin.display());
                        } else {
                            last_err = "el archivo no contiene el binario ollama".into();
                        }
                    }
                    Err(e) => last_err = e,
                }
            }
            Err(e) => {
                last_err = e;
                let _ = std::fs::remove_file(&archive);
            }
        }
    }
    Err(last_err)
}

fn home_dir() -> PathBuf {
    #[cfg(windows)]
    {
        std::env::var("USERPROFILE")
            .map(PathBuf::from)
            .unwrap_or_else(|_| PathBuf::from("."))
    }
    #[cfg(not(windows))]
    {
        std::env::var("HOME")
            .map(PathBuf::from)
            .unwrap_or_else(|_| PathBuf::from("."))
    }
}

fn user_data_dir() -> PathBuf {
    platform_data_root().join(app_config().data_dir_name.as_str())
}

fn log_dir() -> PathBuf {
    let dir = user_data_dir().join("logs");
    let _ = std::fs::create_dir_all(&dir);
    dir
}

fn ollama_log(line: &str) {
    let path = log_dir().join("ollama.log");
    if let Ok(mut f) = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
    {
        let _ = writeln!(f, "{}", line);
    }
}

/// Mismo archivo que los mensajes de Ollama (`logs/ollama.log` bajo APPDATA/SmartGastos).
fn backend_log(line: &str) {
    ollama_log(line);
}

fn process_is_alive(pid: u32) -> bool {
    let pid = sysinfo::Pid::from_u32(pid);
    let mut system = sysinfo::System::new();
    system.refresh_processes(sysinfo::ProcessesToUpdate::Some(&[pid]), true);
    system.process(pid).is_some()
}

fn port_is_released(port: u16) -> bool {
    if TcpStream::connect(("127.0.0.1", port)).is_ok() {
        return false;
    }
    TcpListener::bind(("127.0.0.1", port)).is_ok()
}

fn kill_pid_tree(pid: u32) {
    #[cfg(windows)]
    {
        let _ = hidden_command("taskkill")
            .args(["/PID", &pid.to_string(), "/T", "/F"])
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status();
    }
    #[cfg(unix)]
    {
        let pg = format!("-{}", pid);
        let _ = hidden_command("kill")
            .args(["-TERM", &pg])
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status();
        std::thread::sleep(Duration::from_millis(400));
        let _ = hidden_command("kill")
            .args(["-KILL", &pg])
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status();
    }
}

/// Mata listeners huérfanos (uvicorn hijo de PyInstaller) en el puerto del sidecar.
fn kill_listeners_on_port(port: u16) {
    #[cfg(windows)]
    {
        let Ok(output) = hidden_command("netstat")
            .args(["-ano", "-p", "tcp"])
            .output()
        else {
            return;
        };
        let text = String::from_utf8_lossy(&output.stdout);
        let port_s = port.to_string();
        let mut pids = std::collections::BTreeSet::new();
        for line in text.lines() {
            let cols: Vec<&str> = line.split_whitespace().collect();
            if cols.len() < 5 || !cols.iter().any(|c| *c == "LISTENING") {
                continue;
            }
            let local = cols[1];
            let local_port = local.rsplit(':').next().unwrap_or("");
            if local_port != port_s {
                continue;
            }
            if let Ok(pid) = cols[cols.len() - 1].parse::<u32>() {
                if pid > 0 {
                    pids.insert(pid);
                }
            }
        }
        for pid in pids {
            kill_pid_tree(pid);
        }
    }
    #[cfg(unix)]
    {
        if let Ok(output) = hidden_command("lsof")
            .args(["-iTCP", &format!(":{}", port), "-sTCP:LISTEN", "-t"])
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .output()
        {
            let text = String::from_utf8_lossy(&output.stdout);
            for line in text.lines() {
                if let Ok(pid) = line.trim().parse::<u32>() {
                    if pid > 0 {
                        kill_pid_tree(pid);
                    }
                }
            }
        }
    }
}

fn register_shutdown_target(app: &tauri::AppHandle, target: ShutdownTarget) {
    let pending = app.state::<PendingStops>();
    let mut targets = pending.0.lock().unwrap();
    if !targets
        .iter()
        .any(|known| known.label == target.label && known.pid == target.pid)
    {
        targets.push(target);
    }
}

fn complete_shutdown_target(app: &tauri::AppHandle, target: &ShutdownTarget) {
    let pending = app.state::<PendingStops>();
    pending
        .0
        .lock()
        .unwrap()
        .retain(|known| known.label != target.label || known.pid != target.pid);
}

fn shutdown_target_released(target: &ShutdownTarget) -> (bool, bool) {
    let pid_dead = !process_is_alive(target.pid);
    let port_released = target.port.map(port_is_released).unwrap_or(true);
    (pid_dead, port_released)
}

fn wait_for_owned_shutdown(app: &tauri::AppHandle, target: &ShutdownTarget) -> bool {
    let mut pid_dead = false;
    let mut port_released = target.port.is_none();
    for i in 0..SHUTDOWN_WAIT_ATTEMPTS {
        (pid_dead, port_released) = shutdown_target_released(target);
        if pid_dead && port_released {
            ollama_log(&format!(
                "{}: pid={} terminado; puerto {:?} sin listener y enlazable",
                target.label, target.pid, target.port
            ));
            complete_shutdown_target(app, target);
            return true;
        }
        // PyInstaller deja hijos (uvicorn). Si el PID padre ya murió, no retener
        // la ventana por TIME_WAIT / un listener huérfano.
        if pid_dead && i >= 5 {
            ollama_log(&format!(
                "{}: pid={} muerto; se cierra sin esperar el puerto {:?}",
                target.label, target.pid, target.port
            ));
            complete_shutdown_target(app, target);
            return true;
        }
        std::thread::sleep(Duration::from_millis(100));
    }
    ollama_log(&format!(
        "WARNING {}: espera agotada pid_dead={} port_released={} pid={} port={:?}",
        target.label, pid_dead, port_released, target.pid, target.port
    ));
    complete_shutdown_target(app, target);
    true
}

fn wait_for_pending_shutdown(app: &tauri::AppHandle) -> bool {
    for i in 0..SHUTDOWN_WAIT_ATTEMPTS {
        let targets = app.state::<PendingStops>().0.lock().unwrap().clone();
        if targets.is_empty() {
            return true;
        }
        for target in targets {
            let (pid_dead, port_released) = shutdown_target_released(&target);
            if pid_dead && (port_released || i >= 5) {
                complete_shutdown_target(app, &target);
            }
        }
        std::thread::sleep(Duration::from_millis(100));
    }
    let targets = app.state::<PendingStops>().0.lock().unwrap().clone();
    for target in &targets {
        let (pid_dead, port_released) = shutdown_target_released(target);
        ollama_log(&format!(
            "WARNING cierre pendiente {}: pid_dead={} port_released={} pid={} port={:?}",
            target.label, pid_dead, port_released, target.pid, target.port
        ));
        if pid_dead {
            complete_shutdown_target(app, target);
        }
    }
    true
}

fn stop_backend_child_registered(
    app: &tauri::AppHandle,
    child: CommandChild,
    port: Option<u16>,
) -> bool {
    let pid = child.pid();
    let target = ShutdownTarget {
        label: "kill_backend_child",
        pid,
        port,
    };
    ollama_log(&format!(
        "kill_backend_child: terminando sidecar backend (pid={})",
        pid
    ));
    kill_pid_tree(pid);
    if let Some(listen_port) = port {
        kill_listeners_on_port(listen_port);
    }
    if let Err(e) = child.kill() {
        ollama_log(&format!("kill_backend_child: kill pid={} {}", pid, e));
    }
    let stopped = wait_for_owned_shutdown(app, &target);
    if stopped {
        ollama_log("kill_backend_child: OK");
    }
    stopped
}

fn kill_backend_child(app: &tauri::AppHandle, port: Option<u16>) -> bool {
    let child = {
        let state = app.state::<BackendState>();
        let mut slot = state.0.lock().unwrap();
        let child = slot.take();
        if let Some(child) = child.as_ref() {
            register_shutdown_target(
                app,
                ShutdownTarget {
                    label: "kill_backend_child",
                    pid: child.pid(),
                    port,
                },
            );
        }
        child
    };
    if let Some(child) = child {
        stop_backend_child_registered(app, child, port)
    } else {
        true
    }
}

fn stop_ollama_child_registered(
    _app: &tauri::AppHandle,
    ollama: OllamaChild,
    _port: Option<u16>,
) -> bool {
    // Shared SmartSuite engine: other apps reuse this daemon. Do not kill it.
    ollama_log(&format!(
        "Ollama compartido permanece activo (pid {}); no se detiene al cerrar",
        ollama.pid
    ));
    // Dropping Child closes the handle and does not terminate the process.
    drop(ollama.child);
    true
}

fn kill_ollama_child(app: &tauri::AppHandle, port: Option<u16>) -> bool {
    let ollama = app.state::<OllamaState>().0.lock().unwrap().take();
    if let Some(ollama) = ollama {
        stop_ollama_child_registered(app, ollama, port)
    } else {
        true
    }
}

fn shutdown_requested(app: &tauri::AppHandle) -> bool {
    app.state::<ShutdownState>().0.load(Ordering::Acquire)
}

fn ignore_stale_early_close(app: &tauri::AppHandle) -> bool {
    let splash_started = *app.state::<Navigated>().0.lock().unwrap();
    let started = *app.state::<BootstrapStarted>().0.lock().unwrap();
    !splash_started && started.elapsed() < Duration::from_secs(2)
}

fn shutdown_app(app: &tauri::AppHandle, reason: &str) -> bool {
    if app.state::<ShutdownState>().0.swap(true, Ordering::AcqRel) {
        return wait_for_pending_shutdown(app);
    }
    ollama_log(&format!("shutdown_app: {}", reason));
    let backend_port = app.try_state::<BackendPort>().map(|port| port.0);
    let backend_stopped = kill_backend_child(app, backend_port);
    let ollama_stopped = kill_ollama_child(app, Some(OLLAMA_PORT));
    let pending_stopped = wait_for_pending_shutdown(app);
    let stopped = backend_stopped && ollama_stopped && pending_stopped;
    if stopped {
        ollama_log("shutdown_app: backend terminado; Ollama compartido sigue en ejecucion");
    } else {
        ollama_log(
            "WARNING shutdown_app: timeout parcial; se cierra la ventana de todos modos",
        );
    }
    true
}

fn pick_port() -> u16 {
    for p in [7860u16, 7861, 7862, 7863] {
        if TcpListener::bind(("127.0.0.1", p)).is_ok() {
            return p;
        }
    }
    TcpListener::bind(("127.0.0.1", 0))
        .and_then(|l| l.local_addr())
        .map(|a| a.port())
        .unwrap_or(7860)
}

fn backend_app_url(port: u16) -> String {
    format!("http://127.0.0.1:{}/", port)
}

fn splash_url(port: u16) -> String {
    format!("http://127.0.0.1:{}/__splash/", port)
}

fn wait_for_health(app: &tauri::AppHandle, port: u16, attempts: u32) -> bool {
    let health_url = format!("http://127.0.0.1:{}/api/health", port);
    for _ in 0..attempts {
        if shutdown_requested(app) {
            return false;
        }
        match ureq::get(&health_url).call() {
            Ok(r) if r.status() == 200 => {
                ollama_log("GET /api/health 200 — sidecar arriba");
                return true;
            }
            Ok(r) => ollama_log(&format!("GET /api/health status {}", r.status())),
            Err(e) => ollama_log(&format!("GET /api/health error: {}", e)),
        }
        std::thread::sleep(Duration::from_millis(500));
    }
    false
}

fn navigate_webview_external(app: &tauri::AppHandle, url_str: &str) -> Result<(), String> {
    let parsed = Url::parse(url_str).map_err(|e| format!("URL invalida: {}", e))?;
    let window = app
        .get_webview_window("main")
        .ok_or_else(|| "ventana main no encontrada".to_string())?;
    window
        .navigate(parsed)
        .map_err(|e| format!("navigate fallo: {}", e))?;
    ollama_log(&format!("WebView navigate OK -> {}", url_str));
    Ok(())
}

fn open_splash_on_backend(app: &tauri::AppHandle, port: u16) -> Result<(), String> {
    if shutdown_requested(app) {
        return Err("cierre en curso".into());
    }
    let url = splash_url(port);
    let handle = app.clone();
    ollama_log(&format!("abriendo splash same-origin: {}", url));
    app.run_on_main_thread(move || {
        if shutdown_requested(&handle) {
            ollama_log("open_splash_on_backend: cancelado por cierre");
            return;
        }
        let navigated_state = handle.state::<Navigated>();
        let mut navigated = navigated_state.0.lock().unwrap();
        if *navigated {
            return;
        }
        if let Err(e) = navigate_webview_external(&handle, &url) {
            ollama_log(&format!("open_splash_on_backend navigate: {}", e));
            return;
        }
        *navigated = true;
        drop(navigated);
        if let Some(w) = handle.get_webview_window("main") {
            let _ = w.show();
            let _ = w.set_focus();
        } else {
            ollama_log("open_splash_on_backend: ventana main no encontrada despues de navigate");
        }
    })
    .map_err(|e| format!("open_splash_on_backend: run_on_main_thread {}", e))?;
    ollama_log("open_splash_on_backend: run_on_main_thread OK");
    Ok(())
}

struct ProbeResult {
    ok: bool,
    detail: String,
}

fn probe_backend(port: u16) -> ProbeResult {
    let health_url = format!("http://127.0.0.1:{}/api/health", port);
    let root_url = backend_app_url(port);
    let health_status = match ureq::get(&health_url).call() {
        Ok(r) => r.status(),
        Err(e) => {
            return ProbeResult {
                ok: false,
                detail: format!("GET /api/health error: {}", e),
            };
        }
    };
    if health_status != 200 {
        return ProbeResult {
            ok: false,
            detail: format!("GET /api/health status {}", health_status),
        };
    }

    let ui_url = format!("http://127.0.0.1:{}/api/desktop-ui", port);
    if let Ok(r) = ureq::get(&ui_url).call() {
        if r.status() == 200 {
            if let Ok(body) = r.into_string() {
                ollama_log(&format!("/api/desktop-ui: {}", body));
                if body.contains("\"indexExists\":false") || body.contains("\"indexExists\": false")
                {
                    return ProbeResult {
                        ok: false,
                        detail: "sidecar sin app/index.html empaquetado (rebuild PyInstaller)"
                            .into(),
                    };
                }
            }
        }
    }

    match ureq::get(&root_url).call() {
        Ok(r) => {
            let status = r.status();
            let body = r.into_string().unwrap_or_default();
            let snippet: String = body.chars().take(120).collect();
            if status == 200 && (body.contains("<!DOCTYPE") || body.contains("<html")) {
                ProbeResult {
                    ok: true,
                    detail: "health 200 + HTML en /".into(),
                }
            } else {
                ProbeResult {
                    ok: false,
                    detail: format!("GET / status {} (no HTML). head={:?}", status, snippet),
                }
            }
        }
        Err(e) => ProbeResult {
            ok: false,
            detail: format!("GET / error: {}", e),
        },
    }
}

fn wait_for_backend_ready(app: &tauri::AppHandle, port: u16, attempts: u32) -> bool {
    for _ in 0..attempts {
        if shutdown_requested(app) {
            return false;
        }
        let probe = probe_backend(port);
        *app.state::<LastProbe>().0.lock().unwrap() = probe.detail.clone();
        if probe.ok {
            ollama_log(&format!("sidecar listo: {}", probe.detail));
            return true;
        }
        std::thread::sleep(Duration::from_millis(500));
    }
    false
}

fn apply_backend_ready(app: &tauri::AppHandle, port: u16) {
    let url = backend_app_url(port);
    update_status(app, |s| {
        if s.phase == "blocked" {
            s.can_continue = false;
            return;
        }
        s.backend_url = Some(url);
        s.can_continue = true;
        s.backend_error = None;
        if s.ollama_done {
            s.phase = "ready".into();
            s.percent = 100;
            s.message = "Abriendo la aplicación...".into();
        }
        // No pisar el progreso de descarga/extracción/arranque/pull de Ollama.
    });
}

fn try_mark_backend_ready(app: &tauri::AppHandle, port: u16) -> bool {
    let probe = probe_backend(port);
    *app.state::<LastProbe>().0.lock().unwrap() = probe.detail.clone();
    ollama_log(&format!("probe try_mark_backend_ready: {}", probe.detail));
    if probe.ok {
        apply_backend_ready(app, port);
        true
    } else {
        false
    }
}

fn navigate_main_to_backend(app: &tauri::AppHandle, port: u16) -> Result<(), String> {
    let probe = probe_backend(port);
    *app.state::<LastProbe>().0.lock().unwrap() = probe.detail.clone();
    ollama_log(&format!(
        "navigate_main_to_backend probe: ok={} {}",
        probe.ok, probe.detail
    ));
    if !probe.ok {
        update_status(app, |s| {
            s.phase = "warning".into();
            s.backend_error = Some(format!(
                "El servidor local no respondio: {}. Revise logs/ollama.log.",
                probe.detail
            ));
        });
        ollama_log("navigate_main_to_backend: omitido (health/UI probe fallo)");
        return Err(probe.detail);
    }
    let _ = try_mark_backend_ready(app, port);
    let url_str = backend_app_url(port);
    navigate_webview_external(app, &url_str)?;
    Ok(())
}

fn ram_gb() -> f64 {
    let mut sys = sysinfo::System::new();
    sys.refresh_memory();
    sys.total_memory() as f64 / 1024.0 / 1024.0 / 1024.0
}

fn profile_for_ram() -> Tier {
    let gb = ram_gb();
    let cfg = app_config();
    let mut chosen = None;
    for t in &cfg.ollama_tiers {
        if t.max_ram_gb > 0.0 && gb < t.max_ram_gb {
            chosen = Some(t.clone());
            break;
        }
    }
    let mut profile = chosen
        .or_else(|| cfg.ollama_tiers.last().cloned())
        .unwrap_or_else(|| Tier {
            max_ram_gb: 0.0,
            model: "llama3.2:3b".to_string(),
            extra_models: Vec::new(),
            id: "estandar".to_string(),
            label: "Estándar".to_string(),
        });
    if profile.id.is_empty() {
        profile.id = "auto".to_string();
    }
    if profile.label.is_empty() {
        profile.label = profile.model.clone();
    }
    ollama_log(&format!(
        "perfil {} ({:.1} GB RAM) modelo={} extras={:?}",
        profile.label, gb, profile.model, profile.extra_models
    ));
    profile
}

#[allow(dead_code)]
fn model_for_ram() -> String {
    profile_for_ram().model
}

fn low_ram_override() -> bool {
    for key in ["SMARTSUITE_ALLOW_LOW_RAM", "SMARTCAJA_ALLOW_LOW_RAM"] {
        if let Ok(v) = std::env::var(key) {
            let t = v.trim().to_ascii_lowercase();
            if t == "1" || t == "true" || t == "yes" || t == "on" {
                return true;
            }
        }
    }
    false
}

fn ram_access_level(gb: f64) -> &'static str {
    if low_ram_override() || gb <= 0.0 {
        return "ok";
    }
    let access = &app_config().access;
    let block_at = if access.block_below_gb > 0.0 {
        access.block_below_gb
    } else {
        7.0
    };
    let warn_at = if access.warn_below_gb > 0.0 {
        access.warn_below_gb
    } else {
        13.0
    };
    if gb < block_at {
        "block"
    } else if gb < warn_at {
        "warn"
    } else {
        "ok"
    }
}

fn blocked_ram_message(gb: f64) -> String {
    format!(
        "Este equipo no cumple el mínimo. Se midieron {:.1} GB de RAM y se necesitan al menos 8 GB.",
        gb
    )
}

fn active_model_path() -> PathBuf {
    ollama_app_state_dir().join("active_model.txt")
}

fn active_profile_path() -> PathBuf {
    ollama_app_state_dir().join("active_profile.json")
}

fn write_active_profile_files(
    model_path: &Path,
    profile_path: &Path,
    profile: &Tier,
    ram_gb: f64,
    access: &str,
) {
    if let Some(dir) = model_path.parent() {
        let _ = std::fs::create_dir_all(dir);
    }
    if let Some(dir) = profile_path.parent() {
        let _ = std::fs::create_dir_all(dir);
    }
    let _ = std::fs::write(model_path, format!("{}\n", profile.model));
    let payload = serde_json::json!({
        "id": profile.id,
        "label": profile.label,
        "model": profile.model,
        "extraModels": profile.extra_models,
        "ramGb": ram_gb,
        "access": access,
    });
    if let Ok(text) = serde_json::to_string_pretty(&payload) {
        let _ = std::fs::write(profile_path, text);
    }
}

fn persist_active_profile(profile: &Tier) {
    let gb = ram_gb();
    write_active_profile_files(
        &active_model_path(),
        &active_profile_path(),
        profile,
        gb,
        ram_access_level(gb),
    );
}

fn pull_model_with_progress(app: &tauri::AppHandle, model: &str) -> bool {
    if let Some(body) = fetch_ollama_tags() {
        if ollama_tags_include(&body, model) {
            ollama_log(&format!(
                "Modelo {model} ya esta en /api/tags; se omite la descarga"
            ));
            return true;
        }
    }
    let body = format!("{{\"name\":\"{}\"}}", model);
    let resp = ureq::post(&format!("{}/api/pull", OLLAMA_API))
        .set("Content-Type", "application/json")
        .send_string(&body);
    let resp = match resp {
        Ok(r) => r,
        Err(_) => return false,
    };
    let reader = std::io::BufReader::new(resp.into_reader());
    let mut ok = false;
    for line in reader.lines() {
        let line = match line {
            Ok(l) => l,
            Err(_) => break,
        };
        if line.trim().is_empty() {
            continue;
        }
        let v: serde_json::Value = match serde_json::from_str(&line) {
            Ok(v) => v,
            Err(_) => continue,
        };
        if v.get("error").is_some() {
            ok = false;
            break;
        }
        let status = v.get("status").and_then(|s| s.as_str()).unwrap_or("");
        let total = v.get("total").and_then(|t| t.as_u64());
        let completed = v.get("completed").and_then(|c| c.as_u64());
        let pct: i32 = match (total, completed) {
            (Some(t), Some(c)) if t > 0 => ((c.min(t) * 100) / t) as i32,
            _ => -1,
        };
        let msg = if pct >= 0 {
            format!("Descargando el modelo {} - {}%", model, pct)
        } else {
            format!("Preparando el modelo {} ({})...", model, status)
        };
        ollama_log(&msg);
        update_status(app, |s| {
            s.phase = "downloading".into();
            s.message = msg.clone();
            s.percent = pct;
        });
        if status == "success" {
            ok = true;
        }
    }
    ok
}

fn finish_ollama_bootstrap(app: &tauri::AppHandle, backend_port: u16) {
    ollama_log("== finish_ollama_bootstrap (post extra_models del perfil)");
    {
        let blocked = app.state::<AppStatus>().0.lock().unwrap().phase == "blocked";
        if blocked {
            update_status(app, |s| {
                s.can_continue = false;
                s.ollama_done = false;
            });
            return;
        }
    }
    let _ = try_mark_backend_ready(app, backend_port);

    update_status(app, |s| {
        if s.phase == "blocked" {
            s.can_continue = false;
            s.ollama_done = false;
            return;
        }
        s.ollama_done = true;
        s.backend_error = None;
        if s.can_continue {
            s.percent = 100;
            s.phase = "ready".into();
            s.message = "Abriendo la aplicación...".into();
            if s.backend_url.is_none() {
                s.backend_url = Some(backend_app_url(backend_port));
            }
        } else {
            let detail = app.state::<LastProbe>().0.lock().unwrap().clone();
            ollama_log(&format!(
                "UI aun no lista (se sigue esperando, sin mostrar el error): {}",
                detail
            ));
            s.percent = -1;
            s.phase = "loading-ui".into();
            s.message = "Cargando la aplicación...".into();
        }
    });
    ollama_log("ollama_done=true; splash espera can_continue y luego location.replace('/')");
}

fn ensure_ollama_api(app: &tauri::AppHandle) -> bool {
    import_legacy_models_into_shared();

    if ollama_http_healthy() {
        ollama_log(
            "Ollama ya responde en 127.0.0.1:11434; se reutiliza sin reiniciar",
        );
        update_status(app, |s| {
            s.phase = "ollama".into();
            s.message = "Usando Ollama que ya esta en ejecucion.".into();
            s.percent = -1;
        });
        return true;
    }

    if let Some(bin) = resolve_portable_ollama_binary() {
        ensure_unix_executable(&bin);
        if binary_runs(&bin) {
            ollama_log(&format!("Arrancando Ollama portable: {}", bin.display()));
            return start_and_wait_ollama(app, Some(&bin), "Iniciando Ollama portable...");
        }
        ollama_log(&format!(
            "Ollama portable encontrado pero no ejecuta (no se descarga otro zip): {}",
            bin.display()
        ));
        if system_ollama_available() {
            ollama_log(
                "Arrancando Ollama del PATH; OLLAMA_MODELS apunta al motor compartido y permanece al cerrar",
            );
            return start_and_wait_ollama(app, None, "Iniciando el servicio de IA...");
        }
        update_status(app, |s| {
            s.phase = "warning".into();
            s.message = "Ollama portable no pudo iniciar. La app abrira sin IA.".into();
            s.percent = -1;
        });
        return false;
    }

    if system_ollama_available() {
        ollama_log(
            "Arrancando Ollama del PATH; OLLAMA_MODELS apunta al motor compartido y permanece al cerrar",
        );
        return start_and_wait_ollama(app, None, "Iniciando el servicio de IA...");
    }

    if !portable_zip_needed(&ollama_engine_home(), &legacy_ollama_homes()) {
        ollama_log("Hay un Ollama portable y no se descarga el zip");
        update_status(app, |s| {
            s.phase = "warning".into();
            s.message = "Ollama portable no pudo iniciar. La app abrira sin IA.".into();
            s.percent = -1;
        });
        return false;
    }

    update_status(app, |s| {
        s.phase = "downloading".into();
        s.message = "Ollama no esta instalado. Descargando motor de IA portatil...".into();
        s.percent = -1;
    });
    match install_portable_ollama(app) {
        Ok(bin) => start_and_wait_ollama(app, Some(&bin), "Iniciando el servicio de IA..."),
        Err(e) => {
            ollama_log(&format!("No se pudo instalar Ollama portable: {}", e));
            update_status(app, |s| {
                s.phase = "warning".into();
                s.message = "No se pudo descargar Ollama. La app abrira sin IA.".into();
                s.percent = -1;
            });
            false
        }
    }
}

fn pull_required_models(app: &tauri::AppHandle) {
    if !ollama_http_healthy() {
        ollama_log("Omitiendo pull: API Ollama no disponible");
        return;
    }
    let profile = profile_for_ram();
    persist_active_profile(&profile);
    update_status(app, |s| {
        s.phase = "downloading".into();
        s.message = format!(
            "Descargando el modelo {} (solo la primera vez)...",
            profile.model
        );
        s.percent = -1;
    });
    if pull_model_with_progress(app, &profile.model) {
        ollama_log(&format!(
            "Modelo {} listo en /api/tags; chat debe usar este si el agente pide otro",
            profile.model
        ));
        update_status(app, |s| {
            s.message = format!("Modelo {} listo.", profile.model);
            s.percent = 100;
        });
    }
    ollama_log(&format!(
        "Modelo activo (RAM): {} extras={:?}",
        profile.model, profile.extra_models
    ));
    for extra in &profile.extra_models {
        update_status(app, |s| {
            s.phase = "downloading".into();
            s.message = format!("Descargando componente de IA {}...", extra);
            s.percent = -1;
        });
        if pull_model_with_progress(app, extra) {
            ollama_log(&format!("Modelo adicional '{}' listo.", extra));
            update_status(app, |s| {
                s.message = format!("Componente {} listo.", extra);
                s.percent = 100;
            });
        }
    }
}

fn bootstrap_ollama(app: tauri::AppHandle, backend_port: u16) {
    std::thread::spawn(move || {
        if shutdown_requested(&app) {
            return;
        }
        let gb = ram_gb();
        let profile = profile_for_ram();
        if ram_access_level(gb) == "block" {
            persist_active_profile(&profile);
            let msg = blocked_ram_message(gb);
            ollama_log(&msg);
            update_status(&app, |s| {
                s.phase = "blocked".into();
                s.message = msg;
                s.percent = -1;
                s.can_continue = false;
                s.ollama_done = false;
            });
            return;
        }
        update_status(&app, |s| {
            s.phase = "ollama".into();
            s.message = "Verificando el motor de IA (Ollama)...".into();
            s.percent = -1;
        });
        ollama_log(&format!(
            "== {}: bootstrap Ollama portable (sin MSI, sin reinicio) ==",
            app_config().product_name
        ));

        let _ = ensure_ollama_api(&app);
        if shutdown_requested(&app) {
            return;
        }
        pull_required_models(&app);

        ollama_log("bootstrap Ollama terminado; la app continua sin reiniciar");
        finish_ollama_bootstrap(&app, backend_port);
    });
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(BackendState(Mutex::new(None)))
        .manage(OllamaState(Mutex::new(None)))
        .manage(ShutdownState(AtomicBool::new(false)))
        .manage(BootstrapStarted(Mutex::new(Instant::now())))
        .manage(PendingStops(Mutex::new(Vec::new())))
        .manage(AppStatus(Mutex::new(Status::initial())))
        .manage(Navigated(Mutex::new(false)))
        .manage(LastProbe(Mutex::new(String::new())))
        .invoke_handler(tauri::generate_handler![
            current_status,
            retry_backend,
            navigate_to_backend
        ])
        .setup(|app| {
            let handle = app.handle().clone();
            *handle.state::<BootstrapStarted>().0.lock().unwrap() = Instant::now();
            *handle.state::<Navigated>().0.lock().unwrap() = false;
            persist_status_snapshot(&Status::initial());

            kill_backend_child(&handle, None);
            let port = pick_port();
            app.manage(BackendPort(port));
            ollama_log(&format!("Puerto backend elegido: {}", port));

            let data_dir = user_data_dir().to_string_lossy().to_string();
            let ollama_models = ollama_models_dir().to_string_lossy().to_string();
            let ram_profile = profile_for_ram();
            let ram_model = ram_profile.model.clone();
            let ram_profile_id = ram_profile.id.clone();
            persist_active_profile(&ram_profile);
            if ram_access_level(ram_gb()) == "block" {
                let msg = blocked_ram_message(ram_gb());
                update_status(&handle, |s| {
                    s.phase = "blocked".into();
                    s.message = msg;
                    s.percent = -1;
                    s.can_continue = false;
                    s.ollama_done = false;
                });
            }
            ollama_log(&format!(
                "sidecar env OLLAMA_URL={} OLLAMA_MODEL={} OLLAMA_PROFILE={}",
                OLLAMA_API,
                ram_model,
                ram_profile_id
            ));
            let backend_state = app.state::<BackendState>();
            if backend_state.0.lock().unwrap().is_some() {
                ollama_log("WARN: sidecar ya registrado; omitiendo segundo spawn");
            }
            let sidecar = app.shell().sidecar("backend");
            match sidecar {
                Ok(cmd) => match cmd
                    .env("PORT", port.to_string())
                    .env("DATA_DIR", data_dir)
                    .env("RUN_BY_TAURI", "1")
                    .env("PYTHONIOENCODING", "utf-8")
                    .env("OLLAMA_URL", OLLAMA_API)
                    .env("OLLAMA_HOST", OLLAMA_HOST)
                    .env("OLLAMA_MODELS", ollama_models)
                    .env("OLLAMA_MODEL", ram_model)
                    .env("OLLAMA_PROFILE", ram_profile_id)
                    .spawn()
                {
                    Ok((mut rx, child)) => {
                        let backend_state = app.state::<BackendState>();
                        let mut slot = backend_state.0.lock().unwrap();
                        if shutdown_requested(&handle) {
                            register_shutdown_target(
                                &handle,
                                ShutdownTarget {
                                    label: "kill_backend_child",
                                    pid: child.pid(),
                                    port: Some(port),
                                },
                            );
                            drop(slot);
                            stop_backend_child_registered(&handle, child, Some(port));
                            return Ok(());
                        }
                        if let Some(previous) = slot.take() {
                            ollama_log("WARN: sidecar slot ocupado; matando instancia duplicada");
                            register_shutdown_target(
                                &handle,
                                ShutdownTarget {
                                    label: "kill_backend_child",
                                    pid: previous.pid(),
                                    port: Some(port),
                                },
                            );
                            drop(slot);
                            stop_backend_child_registered(&handle, previous, Some(port));
                            slot = backend_state.0.lock().unwrap();
                            if shutdown_requested(&handle) {
                                register_shutdown_target(
                                    &handle,
                                    ShutdownTarget {
                                        label: "kill_backend_child",
                                        pid: child.pid(),
                                        port: Some(port),
                                    },
                                );
                                drop(slot);
                                stop_backend_child_registered(&handle, child, Some(port));
                                return Ok(());
                            }
                        }
                        slot.replace(child);
                        let sidecar_handle = handle.clone();
                        tauri::async_runtime::spawn(async move {
                            while let Some(event) = rx.recv().await {
                                if let CommandEvent::Stderr(bytes) | CommandEvent::Stdout(bytes) =
                                    event
                                {
                                    backend_log(&String::from_utf8_lossy(&bytes));
                                }
                            }
                            ollama_log("sidecar backend: canal de eventos cerrado (proceso terminó?)");
                            kill_backend_child(&sidecar_handle, Some(port));
                        });
                    }
                    Err(e) => {
                        backend_log(&format!("spawn error: {}", e));
                        update_status(&handle, |s| {
                            s.phase = "warning".into();
                            s.message = format!("No se pudo iniciar el servidor: {}", e);
                            s.backend_error = Some(s.message.clone());
                        });
                    }
                },
                Err(e) => {
                    backend_log(&format!("sidecar missing: {}", e));
                    update_status(&handle, |s| {
                        s.phase = "warning".into();
                        s.message = format!("Backend no encontrado en el instalador: {}", e);
                        s.backend_error = Some(s.message.clone());
                    });
                }
            }

            let splash_handle = handle.clone();
            std::thread::spawn(move || {
                if wait_for_health(&splash_handle, port, 120) {
                    if let Err(e) = open_splash_on_backend(&splash_handle, port) {
                        ollama_log(&format!("open_splash_on_backend: {}", e));
                    }
                } else if !shutdown_requested(&splash_handle) {
                    ollama_log(
                        "ERROR: /api/health no respondio; sidecar caido (revise traceback en este log)",
                    );
                    update_status(&splash_handle, |s| {
                        if s.phase == "blocked" {
                            s.can_continue = false;
                            return;
                        }
                        s.phase = "loading-ui".into();
                        s.percent = -1;
                        s.message = "Cargando la aplicación...".into();
                        s.backend_error = None;
                    });
                }
            });

            bootstrap_ollama(handle.clone(), port);

            let ready_handle = handle.clone();
            std::thread::spawn(move || {
                if wait_for_backend_ready(&ready_handle, port, 3600) {
                    apply_backend_ready(&ready_handle, port);
                }
            });

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error al construir la app de escritorio")
        .run(|app_handle, event| {
            match event {
                RunEvent::ExitRequested { .. } => {
                    let _ = shutdown_app(app_handle, "RunEvent::ExitRequested");
                }
                RunEvent::Exit => {
                    let _ = shutdown_app(app_handle, "RunEvent::Exit");
                }
                RunEvent::WindowEvent { label, event, .. } if label == "main" => {
                    match event {
                        WindowEvent::CloseRequested { api, .. } => {
                            if ignore_stale_early_close(app_handle) {
                                api.prevent_close();
                                ollama_log(
                                    "CloseRequested temprano ignorado hasta iniciar el splash",
                                );
                                return;
                            }
                            let _ = shutdown_app(
                                app_handle,
                                "RunEvent::WindowEvent CloseRequested",
                            );
                            app_handle.exit(0);
                        }
                        WindowEvent::Destroyed => {
                            let _ =
                                shutdown_app(app_handle, "RunEvent::WindowEvent Destroyed");
                            app_handle.exit(0);
                        }
                        _ => {}
                    }
                }
                _ => {}
            }
        });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn finds_ollama_in_bin_subdir() {
        let dir = std::env::temp_dir().join(format!(
            "smartcaja-ollama-find-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        let runtime = dir.join("runtime");
        let bin_dir = runtime.join("bin");
        std::fs::create_dir_all(&bin_dir).unwrap();
        std::fs::create_dir_all(runtime.join("lib").join("ollama")).unwrap();
        let bin = bin_dir.join(ollama_bin_name());
        std::fs::write(&bin, b"fake-ollama").unwrap();
        let found = find_portable_ollama(&runtime).expect("debe encontrar binario");
        assert_eq!(found, bin);
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn official_archives_are_portable_not_msi() {
        let urls = official_ollama_archives();
        assert!(
            !urls.is_empty(),
            "esta plataforma debe tener zip/tgz/tar.zst"
        );
        for (url, name) in urls {
            let lower = format!("{} {}", url, name).to_lowercase();
            assert!(!lower.contains("ollamasetup"), "{}", name);
            assert!(!lower.contains(".msi"), "{}", name);
            assert!(
                name.ends_with(".zip")
                    || name.ends_with(".tgz")
                    || name.ends_with(".tar.zst")
                    || name.ends_with(".tar.gz"),
                "{}",
                name
            );
        }
    }

    fn scratch_dir(label: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!(
            "smartredes-{label}-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        std::fs::create_dir_all(&dir).unwrap();
        dir
    }

    fn sample_tier() -> Tier {
        Tier {
            max_ram_gb: 13.0,
            model: "llama3.2:3b".into(),
            extra_models: Vec::new(),
            id: "estandar".into(),
            label: "Estándar".into(),
        }
    }

    #[test]
    fn engine_home_is_smartsuite_and_active_model_stays_in_app_dir() {
        let engine = ollama_engine_home();
        let root = platform_data_root();
        assert_eq!(engine, root.join("SmartSuite").join("ollama"));
        assert_eq!(active_model_path(), user_data_dir().join("ollama").join("active_model.txt"));
        assert_eq!(
            active_profile_path(),
            user_data_dir().join("ollama").join("active_profile.json")
        );
        assert!(active_model_path().starts_with(user_data_dir()));
        assert!(!active_model_path().starts_with(&engine));
        assert_eq!(
            ollama_owned_pid_path(),
            engine.join("owned.pid")
        );
        assert_eq!(ollama_models_dir(), engine.join("models"));

        let dir = scratch_dir("state");
        let profile = sample_tier();
        write_active_profile_files(
            &dir.join("active_model.txt"),
            &dir.join("active_profile.json"),
            &profile,
            16.0,
            "ok",
        );
        assert_eq!(
            std::fs::read_to_string(dir.join("active_model.txt")).unwrap(),
            "llama3.2:3b\n"
        );
        assert!(dir.join("active_profile.json").is_file());
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn legacy_ollama_exe_suppresses_zip_download() {
        let root = scratch_dir("zip");
        let shared = root.join("SmartSuite").join("ollama");
        let legacy = root.join("SmartGastos").join("ollama");
        std::fs::create_dir_all(legacy.join("models")).unwrap();
        std::fs::write(legacy.join("models").join(ollama_bin_name()), b"not-the-engine").unwrap();
        std::fs::write(legacy.join("active_model.txt"), b"llama3.2:3b\n").unwrap();
        let homes = vec![legacy.clone()];
        assert!(
            portable_zip_needed(&shared, &homes),
            "models/ and active_model.txt must not count as the engine"
        );
        assert!(find_portable_ollama(&legacy).is_none());

        std::fs::create_dir_all(legacy.join("runtime")).unwrap();
        std::fs::write(legacy.join("runtime").join(ollama_bin_name()), b"fake").unwrap();
        assert!(!portable_zip_needed(&shared, &homes));

        std::fs::create_dir_all(shared.join("runtime")).unwrap();
        std::fs::write(shared.join("runtime").join(ollama_bin_name()), b"shared").unwrap();
        assert!(!portable_zip_needed(&shared, &[]));
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn legacy_engine_moves_without_models_or_app_state() {
        let root = scratch_dir("adopt");
        let legacy = root.join("SmartGastos").join("ollama");
        let shared = root.join("SmartSuite").join("ollama");
        let bin = legacy.join("runtime").join(ollama_bin_name());
        std::fs::create_dir_all(bin.parent().unwrap()).unwrap();
        std::fs::write(&bin, b"ollama-bin").unwrap();
        let blob = legacy.join("models").join("blobs").join("sha256-abc");
        std::fs::create_dir_all(blob.parent().unwrap()).unwrap();
        std::fs::write(&blob, b"blob-bytes").unwrap();
        std::fs::write(legacy.join("active_model.txt"), b"llama3.2:3b\n").unwrap();
        std::fs::write(legacy.join("active_profile.json"), b"{}\n").unwrap();
        std::fs::write(legacy.join("owned.pid"), b"99\n").unwrap();
        std::fs::create_dir_all(legacy.join("logs")).unwrap();
        std::fs::write(legacy.join("logs").join("ollama.log"), b"log").unwrap();

        adopt_engine_tree(&legacy, &shared).unwrap();

        assert_eq!(
            std::fs::read(shared.join("runtime").join(ollama_bin_name())).unwrap(),
            b"ollama-bin"
        );
        assert!(!bin.exists());
        assert_eq!(std::fs::read(&blob).unwrap(), b"blob-bytes");
        assert!(legacy.join("active_model.txt").is_file());
        assert!(legacy.join("active_profile.json").is_file());
        assert!(legacy.join("owned.pid").is_file());
        assert!(legacy.join("logs").join("ollama.log").is_file());
        assert!(!shared.join("models").exists());
        assert!(!shared.join("active_model.txt").exists());
        assert!(!shared.join("owned.pid").exists());
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn import_moves_blobs_and_respects_existing_sizes() {
        let root = scratch_dir("models");
        let src = root.join("src");
        let dest = root.join("dest");
        let new_blob = src.join("blobs").join("sha256-new");
        let same_src = src.join("blobs").join("sha256-same");
        let diff_src = src.join("blobs").join("sha256-diff");
        let manifest = src
            .join("manifests")
            .join("registry.ollama.ai")
            .join("library")
            .join("llama3.2")
            .join("3b");
        for path in [&new_blob, &same_src, &diff_src, &manifest] {
            std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        }
        std::fs::write(&new_blob, b"aaaa").unwrap();
        std::fs::write(&same_src, b"zz").unwrap();
        std::fs::write(&diff_src, b"short").unwrap();
        std::fs::write(&manifest, b"manifest").unwrap();
        std::fs::create_dir_all(dest.join("blobs")).unwrap();
        std::fs::write(dest.join("blobs").join("sha256-same"), b"zz").unwrap();
        std::fs::write(dest.join("blobs").join("sha256-diff"), b"longer!").unwrap();

        import_models_tree(&src, &dest);

        assert_eq!(
            std::fs::read(dest.join("blobs").join("sha256-new")).unwrap(),
            b"aaaa"
        );
        assert!(!new_blob.exists());
        assert!(!same_src.exists());
        assert_eq!(
            std::fs::read(dest.join("blobs").join("sha256-same")).unwrap(),
            b"zz"
        );
        assert_eq!(std::fs::read(&diff_src).unwrap(), b"short");
        assert_eq!(
            std::fs::read(dest.join("blobs").join("sha256-diff")).unwrap(),
            b"longer!"
        );
        let moved_manifest = dest
            .join("manifests")
            .join("registry.ollama.ai")
            .join("library")
            .join("llama3.2")
            .join("3b");
        assert_eq!(std::fs::read(moved_manifest).unwrap(), b"manifest");
        assert!(!manifest.exists());
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn installed_tag_suppresses_pull() {
        let body = r#"{"models":[{"name":"llama3.2:3b"},{"name":"llama3.1:8b"}]}"#;
        assert!(ollama_tags_include(body, "llama3.2:3b"));
        assert!(!ollama_tags_include(body, "llama3.2:1b"));
        assert!(!ollama_tags_include(body, "library/llama3.2:3b"));
    }

    #[test]
    fn stale_migrate_lock_is_replaced() {
        let dir = scratch_dir("lock");
        let lock = dir.join("migrate.lock");
        std::fs::write(&lock, "4294967295\n").unwrap();
        assert!(try_acquire_migrate_lock(&lock));
        let text = std::fs::read_to_string(&lock).unwrap();
        assert_eq!(text.trim(), std::process::id().to_string());
        release_migrate_lock(&lock, true);
        assert!(!lock.exists());
        let _ = std::fs::remove_dir_all(&dir);
    }
}
