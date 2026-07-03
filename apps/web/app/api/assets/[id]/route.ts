import { readFile, readdir } from "node:fs/promises";
import path from "node:path";

import { bundleDir } from "@/lib/bundle";

// Serves an original asset file by asset id. Files are named <asset-id>.<ext>
// under the bundle's assets/ directory; we resolve the id to its stored file.
export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const safeId = path.basename(id); // no traversal
  const assetsDir = path.join(bundleDir(), "assets");

  let filename: string | undefined;
  try {
    const entries = await readdir(assetsDir);
    filename = entries.find((f) => f === safeId || f.startsWith(`${safeId}.`));
  } catch {
    return new Response("assets unavailable", { status: 404 });
  }
  if (!filename) {
    return new Response("asset not found", { status: 404 });
  }

  const data = await readFile(path.join(assetsDir, filename));
  const ext = path.extname(filename).slice(1).toLowerCase();
  const type =
    ext === "jpg" || ext === "jpeg"
      ? "image/jpeg"
      : ext === "png"
        ? "image/png"
        : ext === "gif"
          ? "image/gif"
          : "application/octet-stream";
  return new Response(new Uint8Array(data), {
    headers: { "Content-Type": type, "Cache-Control": "no-store" },
  });
}
