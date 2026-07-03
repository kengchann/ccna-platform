import type { ContentBlock } from "@/lib/types";

// Renders canonical content blocks faithfully: prose as paragraphs, verbatim
// (CLI/config) in a monospace <pre> with whitespace preserved exactly, tables
// as HTML tables, and images from the asset API. Never reflows verbatim text.
export function ContentBlocks({ blocks }: { blocks: ContentBlock[] }) {
  return (
    <>
      {blocks.map((block, i) => {
        switch (block.kind) {
          case "text":
            return (
              <p key={i} className="block-text">
                {block.text}
              </p>
            );
          case "verbatim":
            return (
              <pre key={i} className="block-verbatim">
                <code>{block.text}</code>
              </pre>
            );
          case "image":
            return (
              <figure key={i} className="block-image">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={`/api/assets/${block.asset_id}`}
                  alt={block.caption ?? "figure"}
                />
                {block.caption ? <figcaption>{block.caption}</figcaption> : null}
              </figure>
            );
          case "table":
            return (
              <table key={i} className="block-table">
                <tbody>
                  {block.rows.map((row, r) => (
                    <tr key={r}>
                      {row.map((cell, c) => (
                        <td key={c}>{cell}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            );
        }
      })}
    </>
  );
}
