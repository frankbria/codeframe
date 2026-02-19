/**
 * Unified diff parser for the Review & Commit View.
 *
 * Parses git unified diff output into structured data suitable
 * for rendering in DiffViewer and FileTreePanel components.
 */

export interface DiffHunkLine {
  type: 'addition' | 'deletion' | 'context' | 'header';
  content: string;
  oldLineNumber: number | null;
  newLineNumber: number | null;
}

export interface DiffHunk {
  header: string;
  oldStart: number;
  oldCount: number;
  newStart: number;
  newCount: number;
  lines: DiffHunkLine[];
}

export interface DiffFile {
  oldPath: string;
  newPath: string;
  hunks: DiffHunk[];
  insertions: number;
  deletions: number;
  isNew: boolean;
  isDeleted: boolean;
  isRenamed: boolean;
}

/**
 * Parse a unified diff string into structured file sections.
 */
export function parseDiff(diffText: string): DiffFile[] {
  if (!diffText.trim()) return [];

  const files: DiffFile[] = [];
  const lines = diffText.split('\n');
  let i = 0;

  while (i < lines.length) {
    // Find next file header (diff --git a/... b/...)
    if (!lines[i].startsWith('diff --git ')) {
      i++;
      continue;
    }

    const headerMatch = lines[i].match(/^diff --git a\/(.+) b\/(.+)$/);
    if (!headerMatch) {
      i++;
      continue;
    }

    const oldPath = headerMatch[1];
    const newPath = headerMatch[2];
    let isNew = false;
    let isDeleted = false;
    let isRenamed = false;
    i++;

    // Parse file metadata lines (new file, deleted file, index, etc.)
    while (i < lines.length && !lines[i].startsWith('diff --git ') && !lines[i].startsWith('@@')) {
      if (lines[i].startsWith('new file mode')) isNew = true;
      if (lines[i].startsWith('deleted file mode')) isDeleted = true;
      if (lines[i].startsWith('rename from') || lines[i].startsWith('rename to')) isRenamed = true;
      i++;
    }

    const hunks: DiffHunk[] = [];
    let fileInsertions = 0;
    let fileDeletions = 0;

    // Parse hunks
    while (i < lines.length && !lines[i].startsWith('diff --git ')) {
      if (lines[i].startsWith('@@')) {
        const hunkMatch = lines[i].match(/^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$/);
        if (hunkMatch) {
          const oldStart = parseInt(hunkMatch[1], 10);
          const oldCount = hunkMatch[2] !== undefined ? parseInt(hunkMatch[2], 10) : 1;
          const newStart = parseInt(hunkMatch[3], 10);
          const newCount = hunkMatch[4] !== undefined ? parseInt(hunkMatch[4], 10) : 1;
          const hunkHeader = lines[i];
          i++;

          const hunkLines: DiffHunkLine[] = [];
          let oldLine = oldStart;
          let newLine = newStart;

          while (i < lines.length && !lines[i].startsWith('@@') && !lines[i].startsWith('diff --git ')) {
            const line = lines[i];

            if (line.startsWith('+')) {
              hunkLines.push({
                type: 'addition',
                content: line.substring(1),
                oldLineNumber: null,
                newLineNumber: newLine++,
              });
              fileInsertions++;
            } else if (line.startsWith('-')) {
              hunkLines.push({
                type: 'deletion',
                content: line.substring(1),
                oldLineNumber: oldLine++,
                newLineNumber: null,
              });
              fileDeletions++;
            } else if (line.startsWith(' ') || line === '') {
              hunkLines.push({
                type: 'context',
                content: line.startsWith(' ') ? line.substring(1) : line,
                oldLineNumber: oldLine++,
                newLineNumber: newLine++,
              });
            } else if (line.startsWith('\\')) {
              // "\ No newline at end of file" - skip
            } else {
              // Context line without leading space (some diffs)
              hunkLines.push({
                type: 'context',
                content: line,
                oldLineNumber: oldLine++,
                newLineNumber: newLine++,
              });
            }
            i++;
          }

          hunks.push({
            header: hunkHeader,
            oldStart,
            oldCount,
            newStart,
            newCount,
            lines: hunkLines,
          });
        } else {
          i++;
        }
      } else {
        i++;
      }
    }

    files.push({
      oldPath,
      newPath,
      hunks,
      insertions: fileInsertions,
      deletions: fileDeletions,
      isNew,
      isDeleted,
      isRenamed,
    });
  }

  return files;
}

/**
 * Get the display path for a diff file.
 */
export function getFilePath(file: DiffFile): string {
  if (file.isRenamed) return `${file.oldPath} → ${file.newPath}`;
  if (file.isDeleted) return file.oldPath;
  return file.newPath;
}

/**
 * Get the directory portion of a file path.
 */
export function getDirectory(filePath: string): string {
  const lastSlash = filePath.lastIndexOf('/');
  return lastSlash === -1 ? '' : filePath.substring(0, lastSlash);
}

/**
 * Get the filename portion of a file path.
 */
export function getFilename(filePath: string): string {
  const lastSlash = filePath.lastIndexOf('/');
  return lastSlash === -1 ? filePath : filePath.substring(lastSlash + 1);
}
