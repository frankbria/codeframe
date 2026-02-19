import { parseDiff, getFilePath, getDirectory, getFilename } from '@/lib/diffParser';

const SAMPLE_DIFF = `diff --git a/src/main.py b/src/main.py
index abc1234..def5678 100644
--- a/src/main.py
+++ b/src/main.py
@@ -1,4 +1,6 @@
 def hello():
-    return 'hello'
+    return 'hello world'
+
+def greet():
+    return 'hi'
diff --git a/README.md b/README.md
new file mode 100644
--- /dev/null
+++ b/README.md
@@ -0,0 +1,3 @@
+# My Project
+
+A simple project.
`;

const DELETED_FILE_DIFF = `diff --git a/old_file.py b/old_file.py
deleted file mode 100644
index abc1234..0000000
--- a/old_file.py
+++ /dev/null
@@ -1,2 +0,0 @@
-def old_function():
-    pass
`;

describe('parseDiff', () => {
  it('parses a diff with multiple files', () => {
    const files = parseDiff(SAMPLE_DIFF);
    expect(files).toHaveLength(2);
  });

  it('extracts file paths correctly', () => {
    const files = parseDiff(SAMPLE_DIFF);
    expect(files[0].oldPath).toBe('src/main.py');
    expect(files[0].newPath).toBe('src/main.py');
    expect(files[1].newPath).toBe('README.md');
  });

  it('counts insertions and deletions per file', () => {
    const files = parseDiff(SAMPLE_DIFF);
    // main.py: -1 deletion, +3 additions
    expect(files[0].insertions).toBeGreaterThan(0);
    expect(files[0].deletions).toBeGreaterThan(0);
    // README.md: all additions
    expect(files[1].insertions).toBe(3);
    expect(files[1].deletions).toBe(0);
  });

  it('detects new files', () => {
    const files = parseDiff(SAMPLE_DIFF);
    expect(files[1].isNew).toBe(true);
    expect(files[0].isNew).toBe(false);
  });

  it('detects deleted files', () => {
    const files = parseDiff(DELETED_FILE_DIFF);
    expect(files).toHaveLength(1);
    expect(files[0].isDeleted).toBe(true);
  });

  it('parses hunk headers correctly', () => {
    const files = parseDiff(SAMPLE_DIFF);
    expect(files[0].hunks).toHaveLength(1);
    expect(files[0].hunks[0].oldStart).toBe(1);
    expect(files[0].hunks[0].newStart).toBe(1);
  });

  it('identifies line types correctly', () => {
    const files = parseDiff(SAMPLE_DIFF);
    const lines = files[0].hunks[0].lines;
    const additions = lines.filter((l) => l.type === 'addition');
    const deletions = lines.filter((l) => l.type === 'deletion');
    const context = lines.filter((l) => l.type === 'context');

    expect(additions.length).toBeGreaterThan(0);
    expect(deletions.length).toBeGreaterThan(0);
    expect(context.length).toBeGreaterThan(0);
  });

  it('assigns line numbers to additions and deletions', () => {
    const files = parseDiff(SAMPLE_DIFF);
    const lines = files[0].hunks[0].lines;

    const firstAddition = lines.find((l) => l.type === 'addition');
    expect(firstAddition?.newLineNumber).not.toBeNull();
    expect(firstAddition?.oldLineNumber).toBeNull();

    const firstDeletion = lines.find((l) => l.type === 'deletion');
    expect(firstDeletion?.oldLineNumber).not.toBeNull();
    expect(firstDeletion?.newLineNumber).toBeNull();
  });

  it('returns empty array for empty diff', () => {
    expect(parseDiff('')).toEqual([]);
    expect(parseDiff('   ')).toEqual([]);
  });
});

describe('getFilePath', () => {
  it('returns newPath for modified files', () => {
    const files = parseDiff(SAMPLE_DIFF);
    expect(getFilePath(files[0])).toBe('src/main.py');
  });

  it('returns oldPath for deleted files', () => {
    const files = parseDiff(DELETED_FILE_DIFF);
    expect(getFilePath(files[0])).toBe('old_file.py');
  });
});

describe('getDirectory', () => {
  it('extracts directory from path', () => {
    expect(getDirectory('src/components/Button.tsx')).toBe('src/components');
  });

  it('returns empty string for root files', () => {
    expect(getDirectory('README.md')).toBe('');
  });
});

describe('getFilename', () => {
  it('extracts filename from path', () => {
    expect(getFilename('src/components/Button.tsx')).toBe('Button.tsx');
  });

  it('returns full string for root files', () => {
    expect(getFilename('README.md')).toBe('README.md');
  });
});
