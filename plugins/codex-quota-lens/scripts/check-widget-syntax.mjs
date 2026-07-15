#!/usr/bin/env node

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const html = readFileSync(join(root, "assets", "widget", "quota-dashboard-v2.html"), "utf8");
const match = html.match(/<script type="module">([\s\S]*?)<\/script>/);

if (!match) throw new Error("Widget module script was not found.");
new Function(match[1]);
process.stdout.write("Widget syntax is valid.\n");
