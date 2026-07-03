// Server-side loader for an import bundle on disk. This is the file-backed
// path used for local testing; the production path loads bundles into
// PostgreSQL (see apps/web/prisma/schema.prisma). Both read the same bundle
// format, so swapping the source later does not change the UI.

import { readFile } from "node:fs/promises";
import path from "node:path";

import type {
  BundleManifest,
  LoadedBundle,
  Question,
  QuestionGroup,
} from "./types";

// Bundle location can be overridden with QBANK_BUNDLE_DIR; defaults to the
// checked-in sample bundle under apps/web/content/bundle.
export function bundleDir(): string {
  return (
    process.env.QBANK_BUNDLE_DIR ??
    path.join(process.cwd(), "content", "bundle")
  );
}

async function readJsonl<T>(file: string): Promise<T[]> {
  let raw: string;
  try {
    raw = await readFile(file, "utf-8");
  } catch {
    return [];
  }
  return raw
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
    .map((line) => JSON.parse(line) as T);
}

let cache: Promise<LoadedBundle> | null = null;

export function loadBundle(): Promise<LoadedBundle> {
  if (!cache) {
    cache = load();
  }
  return cache;
}

async function load(): Promise<LoadedBundle> {
  const dir = bundleDir();
  const manifest = JSON.parse(
    await readFile(path.join(dir, "manifest.json"), "utf-8"),
  ) as BundleManifest;
  const questions = await readJsonl<Question>(path.join(dir, "questions.jsonl"));
  const groups = await readJsonl<QuestionGroup>(path.join(dir, "groups.jsonl"));
  return { manifest, questions, groups };
}

export function assetPath(filename: string): string {
  // Guard against path traversal: assets always live directly under assets/.
  const safe = path.basename(filename);
  return path.join(bundleDir(), "assets", safe);
}
