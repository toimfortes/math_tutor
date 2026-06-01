import { execSync } from "node:child_process";
import { mkdirSync, rmSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

// Build a real practice bank (gold -> oer -> generate -> promote -> export) so
// the e2e can drive the live /practice surface. Runs before Playwright starts
// the backend, so PRACTICE_BANK_PATH already points at a valid file.
const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, "../..");
const artifacts = path.resolve(here, ".artifacts");
mkdirSync(artifacts, { recursive: true });

const db = path.join(artifacts, "content.sqlite3");
const practice = path.join(artifacts, "practice.json");
rmSync(db, { force: true });

const run = (args) =>
  execSync(`python -m backend.content_pipeline.ingest ${args}`, { cwd: repoRoot, stdio: "inherit" });
run(`gold --db ${db}`);
run(`oer --db ${db}`);
run(`generate-candidates --db ${db} --per-skill 3`);
run(`promote --db ${db}`);
run(`export-practice --db ${db} --output ${practice}`);
console.log(`practice bank built: ${practice}`);
