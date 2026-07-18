import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const source = path.resolve(here, "../src");
const allowedExternal = "schemas/freeciv-events/v1/";
const forbidden = [
  "src/freeciv_agent", "benchmarks/freeciv", "/oracle/", "/planning/",
  "/beliefs/", "/monitoring/", "/execution/", "/harness/",
];
const files = [];
const walk = (directory) => {
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const target = path.join(directory, entry.name);
    if (entry.isDirectory()) walk(target);
    else if (/\.(ts|tsx)$/.test(entry.name) && !target.includes(`${path.sep}test${path.sep}`)
      && !entry.name.endsWith(".test.ts") && !entry.name.endsWith(".test.tsx")) files.push(target);
  }
};
walk(source);

const violations = [];
for (const file of files) {
  const content = fs.readFileSync(file, "utf8");
  const imports = [...content.matchAll(/(?:from\s+|import\s*)["']([^"']+)["']/g)]
    .map((match) => match[1]);
  for (const specifier of imports) {
    const normalized = specifier.replaceAll("\\", "/");
    if (forbidden.some((part) => normalized.includes(part))) {
      violations.push(`${path.relative(source, file)}: ${specifier}`);
    }
    const permittedFixture = normalized.includes("Autotests/fixtures/freeciv-events/v1/");
    if (normalized.startsWith("../") && !normalized.includes(allowedExternal) && !permittedFixture) {
      violations.push(`${path.relative(source, file)}: external import ${specifier}`);
    }
  }
}
if (violations.length) throw new Error(`UI dependency boundary violated:\n${violations.join("\n")}`);
console.log(JSON.stringify({ files: files.length, violations: 0 }));
