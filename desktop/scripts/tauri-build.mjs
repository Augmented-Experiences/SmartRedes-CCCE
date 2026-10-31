#!/usr/bin/env node
/**
 * Ejecuta `tauri build --verbose` sin tragarse stdout/stderr.
 * Escribe copia en desktop/tauri-build.log; si falla, corre cargo en src-tauri.
 */
import { spawn } from "node:child_process";
import { createWriteStream } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const DESKTOP = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const TAURI_CLI = resolve(DESKTOP, "node_modules/@tauri-apps/cli/tauri.js");
const LOG_PATH = resolve(DESKTOP, "tauri-build.log");
const CARGO_LOG_PATH = resolve(DESKTOP, "cargo-build.log");

function tee(stream, chunk, logStream) {
  stream.write(chunk);
  logStream.write(chunk);
}

function runProcess(label, cmd, args, cwd, logPath) {
  return new Promise((resolvePromise) => {
    const logStream = createWriteStream(logPath, { flags: "w" });
    const header = `=== ${label} ${new Date().toISOString()} ===\n`;
    logStream.write(header);
    process.stderr.write(`\n>> ${label}\n>> Log: ${logPath}\n\n`);

    const child = spawn(cmd, args, {
      cwd,
      env: {
        ...process.env,
        RUST_BACKTRACE: process.env.RUST_BACKTRACE || "full",
        CARGO_TERM_COLOR: "always",
      },
      stdio: ["inherit", "pipe", "pipe"],
      windowsHide: false,
      shell: false,
    });

    child.stdout?.on("data", (chunk) => tee(process.stdout, chunk, logStream));
    child.stderr?.on("data", (chunk) => tee(process.stderr, chunk, logStream));

    child.on("error", (err) => {
      const msg = `\nERROR al lanzar ${label}: ${err.message}\n`;
      process.stderr.write(msg);
      logStream.write(msg);
      logStream.end(() => resolvePromise(1));
    });

    child.on("close", (code) => {
      const tail = `\n=== ${label} terminó con código ${code ?? "?"} ===\n`;
      logStream.write(tail);
      logStream.end(() => resolvePromise(code ?? 1));
    });
  });
}

const code = await runProcess(
  "tauri build --verbose",
  process.execPath,
  [TAURI_CLI, "build", "--verbose", "--verbose"],
  DESKTOP,
  LOG_PATH
);

if (code === 0) {
  process.exit(0);
}

process.stderr.write(
  "\n--- tauri build falló. Ejecutando cargo build --release en src-tauri para ver el error de Rust ---\n"
);

const cargoCode = await runProcess(
  "cargo build --release -vv",
  "cargo",
  ["build", "--release", "-vv"],
  resolve(DESKTOP, "src-tauri"),
  CARGO_LOG_PATH
);

process.stderr.write("\n--- Resumen ---\n");
process.stderr.write(`  tauri-build.log  → ${LOG_PATH}\n`);
process.stderr.write(`  cargo-build.log  → ${CARGO_LOG_PATH}\n`);
process.stderr.write(
  "Causas frecuentes: capabilities/default.json inválido, falta sidecar backend-*.exe, iconos.\n"
);

process.exit(cargoCode !== 0 ? cargoCode : code);
