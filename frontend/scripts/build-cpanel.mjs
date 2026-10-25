// Build locally/CI. This writes only the repository's static release folder.
import { cp, lstat, mkdir, realpath, rm } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { build } from "vite";

const frontend = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repository = await realpath(path.resolve(frontend, ".."));
const destination = path.join(repository, "deploy", "frontend");
process.env.VITE_API_BASE_URL ||= "https://puspasarirate.my.id/python-test";
process.env.VITE_ENABLE_WEBSOCKETS = "false";
await build({ root: frontend, mode: "production" });
await mkdir(destination, { recursive: true });
if (await realpath(destination) !== destination) throw new Error("Release destination must not be a symlink");
const assets = path.join(destination, "assets");
const info = await lstat(assets).catch(error => { if (error.code !== "ENOENT") throw error; });
if (info?.isSymbolicLink()) throw new Error("Release assets must not be a symlink");
// Verified fixed path: generated assets only; no runtime media/configuration.
await rm(assets, { recursive: true, force: true });
await cp(path.join(frontend, "dist"), destination, { recursive: true });
console.log(`Static bundle prepared: ${destination}`);
