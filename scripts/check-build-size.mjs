import { readdir, stat } from 'node:fs/promises';
import { join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../dist/client/', import.meta.url));
const limits = {
  totalBytes: 2 * 1024 * 1024,
  assetBytes: 450 * 1024,
  scriptAndStyleBytes: 1400 * 1024,
};

async function walk(directory) {
  const files = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) files.push(...(await walk(path)));
    else if (entry.isFile()) files.push(path);
  }
  return files;
}

const files = await walk(root);
const rows = await Promise.all(
  files.map(async (file) => ({ file, bytes: (await stat(file)).size })),
);
const total = rows.reduce((sum, row) => sum + row.bytes, 0);
const code = rows
  .filter(({ file }) => /\.(?:css|js)$/.test(file))
  .reduce((sum, row) => sum + row.bytes, 0);
const oversized = rows.filter(
  ({ file, bytes }) => /\.(?:css|js)$/.test(file) && bytes > limits.assetBytes,
);

console.log(
  `Build size: ${(total / 1024).toFixed(1)} KiB total; ${(code / 1024).toFixed(1)} KiB JS/CSS.`,
);
if (oversized.length) {
  for (const row of oversized) {
    console.error(
      `Asset exceeds ${(limits.assetBytes / 1024).toFixed(0)} KiB: ${relative(root, row.file)} (${(row.bytes / 1024).toFixed(1)} KiB)`,
    );
  }
}
if (total > limits.totalBytes)
  console.error('The complete static dashboard exceeds the 2 MiB budget.');
if (code > limits.scriptAndStyleBytes)
  console.error('JavaScript and CSS exceed the 1.4 MiB budget.');
if (
  oversized.length ||
  total > limits.totalBytes ||
  code > limits.scriptAndStyleBytes
)
  process.exit(1);
