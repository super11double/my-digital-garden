#!/usr/bin/env node
/**
 * scripts/generate-notes.js
 *  - Scans notes/ for markdown files
 *  - Picks files whose frontmatter `share` is true (or assumes true if frontmatter parsing fails but `share` present as a string)
 *  - Emits notes.json at repo root as an array: [{ title, path }, ...]
 *
 * Usage:
 *   npm install --save-dev gray-matter fast-glob
 *   node scripts/generate-notes.js
 */

const fs = require('fs').promises;
const path = require('path');
const matter = require('gray-matter');
const fg = require('fast-glob');

(async function main() {
  try {
    const repoRoot = path.resolve(__dirname, '..');
    const notesGlob = ['notes/**/*.md', 'notes/**/*.mdx', 'notes/**/*.markdown'];

    // Find files
    const files = await fg(notesGlob, { cwd: repoRoot, dot: true, onlyFiles: true, unique: true });

    const results = [];

    for (const rel of files) {
      const abs = path.join(repoRoot, rel);
      let raw;
      try {
        raw = await fs.readFile(abs, 'utf8');
      } catch (e) {
        console.warn(`Failed to read ${rel}: ${e.message}`);
        continue;
      }

      let fm;
      try {
        fm = matter(raw);
      } catch (e) {
        console.warn(`Failed to parse frontmatter for ${rel}: ${e.message}`);
        // If frontmatter parsing fails, try a lightweight heuristic to find share: true
        const shareMatch = /(?:^|\n)share\s*:\s*(true|"true"|'true')/i.test(raw);
        if (!shareMatch) continue;
        fm = { data: {} };
      }

      const front = fm.data || {};

      // Accept boolean true or string 'true'
      const isShared = front.share === true || String(front.share).toLowerCase() === 'true' || ('share' in front && front.share == null && /(?:^|\n)share\s*:\s*true/i.test(raw));
      // Also accept older malformed frontmatter like `"share: true":` by regex
      const malformedShare = /\"?share\s*:\s*true\"?/.test(raw);
      if (!(isShared || malformedShare)) continue;

      // Determine title: frontmatter.title > filename (without ext)
      const parsed = path.parse(rel);
      const fileNameNoExt = parsed.name;
      const title = front.title || front.name || fileNameNoExt;

      // Build path like 'notes/爱情' (relative path without extension, using forward slashes)
      const withoutExt = rel.replace(/\\/g, '/').replace(/\.[^.\/]+$/, '');
      const notePath = withoutExt; // e.g., notes/爱情

      results.push({ title, path: notePath });
    }

    // Optional: sort by title (comment out if undesired)
    results.sort((a, b) => String(a.title).localeCompare(String(b.title), 'zh-Hans-CN', { numeric: true }));

    // Backup existing notes.json if present
    const outPath = path.join(repoRoot, 'notes.json');
    try {
      await fs.access(outPath);
      const ts = new Date().toISOString().replace(/[:.]/g, '-');
      const bakPath = path.join(repoRoot, `notes.json.bak.${ts}`);
      await fs.rename(outPath, bakPath);
      console.log(`Existing notes.json backed up to ${path.basename(bakPath)}`);
    } catch (e) {
      // file doesn't exist – ignore
    }

    // Write new notes.json
    const payload = JSON.stringify(results, null, 2) + '\n';
    await fs.writeFile(outPath, payload, 'utf8');
    console.log(`Wrote ${results.length} notes to notes.json`);
  } catch (err) {
    console.error('Error generating notes.json:', err);
    process.exit(1);
  }
})();
