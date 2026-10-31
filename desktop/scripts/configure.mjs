#!/usr/bin/env node
// ============================================================
// configure.mjs — Genera los archivos variables del launcher Tauri
// a partir de desktop/smartsuite.config.json:
//   - src-tauri/tauri.conf.json
//   - src-tauri/appconfig.json
//   - src-tauri/Cargo.toml (name/description/bin)
//   - src-tauri/capabilities/default.json
//   - package.json (npm name/description)
//   - ui/index.html (splash), ui/ccce-theme.css, ui/accent.css
//
// Se ejecuta automáticamente antes de 'npm run build' / 'npm run dev'.
// ============================================================
import { readFileSync, writeFileSync, copyFileSync, mkdirSync, existsSync, rmSync } from "node:fs";
import { execSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const DESKTOP = resolve(HERE, "..");
const cfgPath = resolve(DESKTOP, "smartsuite.config.json");
const cfg = JSON.parse(readFileSync(cfgPath, "utf8"));

function req(name) {
  if (!cfg[name]) throw new Error(`smartsuite.config.json: falta '${name}'`);
  return cfg[name];
}

const publisher = req("publisher");
const productName = req("productName");
const version = cfg.version || "1.0.0";
const identifier = req("identifier");
const dataDirName = req("dataDirName");
const accent = cfg.accent || "#2E9E3F";

/** Identificador Rust/npm estable (co.org.ccce.smartgastos → smartgastos). */
function cargoPackageName() {
  if (cfg.cargoPackageName) return String(cfg.cargoPackageName).toLowerCase();
  const last = identifier.split(".").pop() || "smartapp";
  return last.replace(/[^a-z0-9_]/gi, "").toLowerCase() || "smartapp";
}

/** Marca en splash: SmartGastos → Smart + Gastos (acento). */
function brandHtml(name) {
  if (/^Smart[A-ZÁÉÍÓÚÑ]/.test(name) && name.length > 5) {
    const tail = name.slice(5);
    return `Smart<span class="accent">${escapeHtml(tail)}</span>`;
  }
  return `<span class="accent">${escapeHtml(name)}</span>`;
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

const pkg = cargoPackageName();
const splashSubtitle =
  cfg.splashSubtitle || cfg.shortDescription || `Preparando ${productName}...`;

/** Bundle formats valid on the machine running the build (Tauri CLI is host-specific). */
function bundleTargetsForHost() {
  switch (process.platform) {
    case "win32":
      return ["msi", "nsis"];
    case "darwin":
      return ["dmg"];
    default:
      return ["deb", "rpm", "appimage"];
  }
}

const bundleTargets = bundleTargetsForHost();

function rustHostTriple() {
  try {
    const out = execSync("rustc -vV", {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
    });
    const line = out.split("\n").find((l) => l.startsWith("host: "));
    return line ? line.slice("host: ".length).trim() : null;
  } catch {
    return null;
  }
}

function expectedSidecarRelative() {
  const triple = rustHostTriple();
  if (!triple) return null;
  const ext = process.platform === "win32" ? ".exe" : "";
  return `src-tauri/binaries/backend-${triple}${ext}`;
}

function assertSidecarForTauri() {
  const rel = expectedSidecarRelative();
  if (!rel) {
    console.error("");
    console.error("ERROR: no se pudo obtener el target de Rust (rustc -vV).");
    console.error("       Instale Rust y reinicie la terminal: rustup default stable-msvc");
    process.exit(1);
  }
  const full = resolve(DESKTOP, rel);
  if (existsSync(full)) {
    console.log(`configure.mjs: sidecar OK (${rel.replace(/\\/g, "/")})`);
    return;
  }
  mkdirSync(resolve(DESKTOP, "src-tauri/binaries"), { recursive: true });
  console.error("");
  console.error("ERROR: Falta el sidecar del backend para Tauri (bundle.externalBin).");
  console.error("");
  console.error(`  Archivo esperado:`);
  console.error(`    ${rel}`);
  console.error("");
  console.error("  Genérelo antes de npm run build (PyInstaller + copia a binaries/):");
  if (process.platform === "win32") {
    console.error(
      "    powershell -ExecutionPolicy Bypass -File desktop\\scripts\\build-backend.ps1"
    );
    console.error("  Para MSI/NSIS en un solo paso:");
    console.error(
      "    powershell -ExecutionPolicy Bypass -File desktop\\scripts\\build-backend.ps1 -Installer"
    );
  } else {
    console.error("    ./desktop/scripts/build-backend.sh");
  }
  console.error("");
  console.error(
    "  Sin ese binario, tauri-build falla al empaquetar externalBin: binaries/backend."
  );
  process.exit(1);
}

// --- 1) tauri.conf.json ---
const tauriConf = {
  $schema: "https://schema.tauri.app/config/2",
  productName,
  version,
  identifier,
  build: { frontendDist: "../ui" },
  app: {
    withGlobalTauri: true,
    windows: [
      {
        label: "main",
        title: (cfg.window && cfg.window.title) || productName,
        width: (cfg.window && cfg.window.width) || 1200,
        height: (cfg.window && cfg.window.height) || 800,
        minWidth: (cfg.window && cfg.window.minWidth) || 900,
        minHeight: (cfg.window && cfg.window.minHeight) || 600,
        resizable: true,
        center: true,
        dragDropEnabled: false,
      },
    ],
    security: { csp: null },
  },
  bundle: {
    active: true,
    targets: bundleTargets,
    icon: [
      "icons/32x32.png",
      "icons/128x128.png",
      "icons/128x128@2x.png",
      "icons/icon.icns",
      "icons/icon.ico",
    ],
    externalBin: ["binaries/backend"],
    macOS: {
      entitlements: "entitlements.plist",
    },
    category: cfg.category || "Business",
    shortDescription: cfg.shortDescription || productName,
    longDescription: cfg.longDescription || productName,
  },
  plugins: {},
};
writeFileSync(
  resolve(DESKTOP, "src-tauri/tauri.conf.json"),
  JSON.stringify(tauriConf, null, 2) + "\n"
);

// --- 2) appconfig.json (lo lee Rust vía include_str!) ---
const tiers = ((cfg.ollama && cfg.ollama.tiers) || [{ maxRamGb: 0, model: "llama3.2:3b" }]).map(
  (t) => ({
    maxRamGb: Number(t.maxRamGb) || 0,
    model: String(t.model),
    extraModels: Array.isArray(t.extraModels) ? t.extraModels.map(String) : [],
    id: String(t.id || ""),
    label: String(t.label || t.model),
  })
);
const extraModels = ((cfg.ollama && cfg.ollama.extraModels) || []).map(String);
const accessCfg = cfg.access || {};
const appConfig = {
  productName,
  dataDirName,
  ollamaTiers: tiers,
  extraModels,
  access: {
    blockBelowGb: Number(accessCfg.blockBelowGb) || 7,
    warnBelowGb: Number(accessCfg.warnBelowGb) || 13,
  },
};
writeFileSync(
  resolve(DESKTOP, "src-tauri/appconfig.json"),
  JSON.stringify(appConfig, null, 2) + "\n"
);

// --- 3) Cargo.toml ---
const cargoDescription = cfg.longDescription || cfg.shortDescription || productName;
const cargoToml = `[package]
name = "${pkg}"
version = "${version}"
description = "${cargoDescription.replace(/"/g, '\\"')}"
authors = ["${publisher.replace(/"/g, '\\"')}"]
edition = "2021"
rust-version = "1.77"

[build-dependencies]
tauri-build = { version = "2", features = [] }

[dependencies]
tauri = { version = "2", features = [] }
tauri-plugin-shell = "2"
serde = { version = "1", features = ["derive"] }
serde_json = "1"
sysinfo = "0.33"
ureq = { version = "2", default-features = false, features = ["native-tls"] }
zip = "0.6"
flate2 = "1"
tar = "0.4"

[[bin]]
name = "${pkg}"
path = "src/main.rs"

[profile.release]
panic = "abort"
codegen-units = 1
lto = true
opt-level = "s"
strip = true
`;
writeFileSync(resolve(DESKTOP, "src-tauri/Cargo.toml"), cargoToml);

// --- 4) capabilities/default.json (sin $schema: gen/ no existe hasta el primer build) ---
const capabilities = {
  identifier: "default",
  description: `Permisos base para la ventana principal de ${productName}.`,
  windows: ["main"],
  permissions: [
    "core:default",
    "core:webview:default",
    "shell:allow-kill",
    "shell:allow-stdin-write",
    {
      identifier: "shell:allow-spawn",
      allow: [
        {
          name: "backend",
          sidecar: true,
          args: true,
        },
      ],
    },
  ],
};
writeFileSync(
  resolve(DESKTOP, "src-tauri/capabilities/default.json"),
  JSON.stringify(capabilities, null, 2) + "\n"
);

// --- 5) package.json (npm) ---
const pkgJsonPath = resolve(DESKTOP, "package.json");
const pkgJson = JSON.parse(readFileSync(pkgJsonPath, "utf8"));
pkgJson.name = `${pkg}-desktop`;
pkgJson.version = version;
pkgJson.description = `Instalador/app de escritorio nativo de ${productName} (Tauri) — ${publisher}`;
writeFileSync(pkgJsonPath, JSON.stringify(pkgJson, null, 2) + "\n");

// --- 6) Splash UI ---
mkdirSync(resolve(DESKTOP, "ui"), { recursive: true });
copyFileSync(resolve(DESKTOP, "brand/ccce-theme.css"), resolve(DESKTOP, "ui/ccce-theme.css"));
writeFileSync(
  resolve(DESKTOP, "ui/accent.css"),
  `/* Generado por configure.mjs — acento por-herramienta */\n:root { --ccce-accent: ${accent}; }\n`
);

const favSrc = [
  resolve(DESKTOP, "..", "app", "favicon.ico"),
  resolve(DESKTOP, "src-tauri", "icons", "icon.ico"),
].find((p) => existsSync(p));
if (favSrc) {
  copyFileSync(favSrc, resolve(DESKTOP, "ui/favicon.ico"));
}

const markSrc = [
  resolve(DESKTOP, "brand/ccce-mark.png"),
  resolve(DESKTOP, "..", "icon.png"),
].find((p) => existsSync(p));
let logoHtml = "";
if (markSrc) {
  copyFileSync(markSrc, resolve(DESKTOP, "ui/splash-mark.png"));
  logoHtml += `<img class="splash-mark" src="splash-mark.png" alt="" />\n  `;
}

const logoRel = cfg.splashLogo || "../app/logo-ccce.png";
const logoCandidates = [
  resolve(DESKTOP, logoRel),
  resolve(DESKTOP, "..", "app", "logo-ccce.png"),
  resolve(DESKTOP, "..", "app", "logo-ccce-full.png"),
  resolve(DESKTOP, "..", "icon.png"),
];
const logoSrc = logoCandidates.find((p) => existsSync(p));
if (logoSrc) {
  const logoExtension = logoSrc.slice(logoSrc.lastIndexOf(".")) || ".png";
  const splashLogoFile = `splash-logo${logoExtension}`;
  copyFileSync(logoSrc, resolve(DESKTOP, "ui", splashLogoFile));
  logoHtml += `<img class="splash-logo" src="${splashLogoFile}" alt="${escapeHtml(productName)}" />\n  `;
}

const splashTpl = readFileSync(resolve(DESKTOP, "ui/splash.template.html"), "utf8");
const splashHtml = splashTpl
  .replaceAll("{{PRODUCT_NAME}}", escapeHtml(productName))
  .replaceAll("{{PUBLISHER}}", escapeHtml(publisher))
  .replaceAll("{{BRAND_HTML}}", brandHtml(productName))
  .replaceAll("{{SPLASH_SUBTITLE}}", escapeHtml(splashSubtitle))
  .replaceAll("{{LOGO_HTML}}", logoHtml);
writeFileSync(resolve(DESKTOP, "ui/index.html"), splashHtml);

// One splash logo only: official CCCE isotipo. Assets may have already
// copied splash-mark / color wordmark above; overwrite template + index.
{
  const canonicalTplPath = resolve(DESKTOP, "brand/splash.template.html");
  const splashTplPath = resolve(DESKTOP, "ui/splash.template.html");
  if (existsSync(canonicalTplPath)) {
    copyFileSync(canonicalTplPath, splashTplPath);
  } else if (existsSync(splashTplPath)) {
    let t = readFileSync(splashTplPath, "utf8");
    t = t.replace(/<img[^>]*splash-mark[^>]*>\s*/gi, "");
    t = t.replace(/\.splash-mark\s*\{[^}]*\}/g, "");
    t = t.replace(
      /\.splash-logo\s*\{[^}]*\}/,
      ".splash-logo { height: 64px; width: auto; max-width: min(280px, 70vw); object-fit: contain; display: block; }"
    );
    writeFileSync(splashTplPath, t);
  }
  const staleMark = resolve(DESKTOP, "ui/splash-mark.png");
  if (existsSync(staleMark)) {
    rmSync(staleMark, { force: true });
  }
  let logoHtmlOne = "";
  const whitePng = resolve(DESKTOP, "brand/logo-ccce-white.png");
  if (existsSync(whitePng)) {
    copyFileSync(whitePng, resolve(DESKTOP, "ui/splash-logo.png"));
    logoHtmlOne = `<img class="splash-logo" src="splash-logo.png" alt="${escapeHtml(productName)}" />\n  `;
  }
  const tplOne = readFileSync(splashTplPath, "utf8");
  const htmlOne = tplOne
    .replaceAll("{{PRODUCT_NAME}}", escapeHtml(productName))
    .replaceAll("{{BRAND_HTML}}", brandHtml(productName))
    .replaceAll("{{SPLASH_SUBTITLE}}", escapeHtml(splashSubtitle))
    .replaceAll("{{PUBLISHER}}", escapeHtml(publisher))
    .replaceAll("{{LOGO_HTML}}", logoHtmlOne)
    .replace(/<img[^>]*splash-mark[^>]*>\s*/gi, "");
  writeFileSync(resolve(DESKTOP, "ui/index.html"), htmlOne);
}


// --- 7) Cargo.lock: alinear nombre del paquete si cambió ---
const lockPath = resolve(DESKTOP, "src-tauri/Cargo.lock");
try {
  let lock = readFileSync(lockPath, "utf8");
  const lockNameRe = /^name = "([^"]+)"$/m;
  if (lock.includes('name = "smartcaja"') && pkg !== "smartcaja") {
    lock = lock.replaceAll('name = "smartcaja"', `name = "${pkg}"`);
    writeFileSync(lockPath, lock);
  } else if (lock.includes(`name = "${pkg}"`) === false && lockNameRe.test(lock)) {
    const firstPkg = lock.match(lockNameRe);
    if (firstPkg && firstPkg[1] !== pkg) {
      lock = lock.replaceAll(`name = "${firstPkg[1]}"`, `name = "${pkg}"`);
      writeFileSync(lockPath, lock);
    }
  }
} catch {
  // lock se regenerará en el primer cargo build
}

console.log(
  `configure.mjs: '${productName}' (${pkg}) - accent ${accent}, dataDir ${dataDirName}, bundles [${bundleTargets.join(", ")}] (${process.platform})`
);

assertSidecarForTauri();
