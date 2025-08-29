#!/usr/bin/env node
/**
 * Tig Sync (Node)
 * Synchronize manual edits from project to .tig submodule and create a "manual:" commit.
 * Mirrors tig_sync.py behavior and CLI.
 */

const fs = require('fs');
const path = require('path');
const { execFileSync, execSync } = require('child_process');

function exists(p) {
  try { fs.accessSync(p, fs.constants.F_OK); return true; } catch { return false; }
}

function readDirRecursive(dir, filterDirs = () => true) {
  const results = [];
  const stack = [dir];
  while (stack.length) {
    const current = stack.pop();
    const entries = fs.readdirSync(current, { withFileTypes: true });
    for (const ent of entries) {
      const full = path.join(current, ent.name);
      if (ent.isDirectory()) {
        if (filterDirs(ent.name, full)) stack.push(full);
      } else if (ent.isFile()) {
        results.push(full);
      }
    }
  }
  return results;
}

function rel(from, to) { return path.relative(from, to); }

class TigSync {
  constructor(projectDir = process.cwd(), verbose = false) {
    this.projectDir = projectDir;
    this.tigDir = path.join(projectDir, '.tig');
    this.verbose = verbose;

    this.files_synced = [];
    this.files_added = [];
    this.files_modified = [];
    this.files_deleted = [];
    this.force = false;
  }

  validateSetup() {
    if (!exists(this.tigDir)) {
      console.log('❌ No .tig directory found');
      console.log('💡 Run a Claude session first to initialize Tig');
      return false;
    }
    if (!exists(path.join(this.tigDir, '.git'))) {
      console.log('❌ .tig is not a git repository');
      console.log("💡 Run 'uv run tig_submodule_setup.py' to fix this");
      return false;
    }
    try {
      const out = execFileSync('git', ['status', '--porcelain'], { cwd: this.tigDir, encoding: 'utf8' });
      if (out.trim() && !this.force) {
        console.log('⚠️  Uncommitted changes in .tig directory');
        console.log('💡 Commit or stash changes first, or use --force');
        return false;
      }
    } catch (e) {
      console.log('❌ Failed to check git status in .tig');
      return false;
    }
    return true;
  }

  findModifiedFiles(specificFiles) {
    const modified = [];
    const newFiles = [];
    const deleted = [];

    let filesToCheck = [];
    if (specificFiles && specificFiles.length) {
      filesToCheck = specificFiles.slice();
    } else {
      // Collect files tracked in .tig (excluding .git, cache, shadow and metadata files)
      const tigFiles = readDirRecursive(this.tigDir, (name, full) => !['.git', 'cache', 'shadow'].includes(name));
      for (const f of tigFiles) {
        const rp = rel(this.tigDir, f);
        const base = path.basename(rp);
        if (['micro_index.json', 'session_state.json', 'config.json', '.git', '.gitignore'].includes(base)) continue;
        filesToCheck.push(rp);
      }

      // Also detect new files in project
      const projectFiles = readDirRecursive(this.projectDir, (name, full) => !name.startsWith('.'));
      const allowed = new Set(['.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.c', '.cpp', '.go', '.rs', '.txt', '.md', '.json', '.xml', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.html', '.css', '.scss', '.sass', '.less']);
      for (const f of projectFiles) {
        const rp = rel(this.projectDir, f);
        // Skip .tig subtree and any hidden paths
        if (rp.startsWith('.tig' + path.sep)) continue;
        const bn = path.basename(f);
        if (bn === '.DS_Store' || bn === 'Thumbs.db') continue;
        const ext = path.extname(f);
        if (allowed.has(ext) || ['.gitignore', 'Makefile', 'Dockerfile'].includes(bn)) {
          const tigPath = path.join(this.tigDir, rp);
          if (!exists(tigPath) && !filesToCheck.includes(rp)) newFiles.push(rp);
        }
      }
    }

    // Check each file for modifications
    for (const rp of filesToCheck) {
      const mainPath = path.join(this.projectDir, rp);
      const tigPath = path.join(this.tigDir, rp);
      if (!exists(mainPath)) {
        deleted.push(rp);
      } else if (!exists(tigPath)) {
        newFiles.push(rp);
      } else {
        try {
          const a = fs.readFileSync(mainPath);
          const b = fs.readFileSync(tigPath);
          if (!a.equals(b)) modified.push(rp);
        } catch (e) {
          if (this.verbose) console.log(`⚠️  Error comparing ${rp}: ${e.message || e}`);
          modified.push(rp);
        }
      }
    }

    return [modified, newFiles, deleted];
  }

  syncFileToTig(rp, isDeletion = false) {
    const mainPath = path.join(this.projectDir, rp);
    const tigPath = path.join(this.tigDir, rp);
    try {
      if (isDeletion) {
        if (exists(tigPath)) fs.unlinkSync(tigPath);
        if (this.verbose) console.log(`  ✓ Removed: ${rp}`);
        return true;
      }
      fs.mkdirSync(path.dirname(tigPath), { recursive: true });
      fs.copyFileSync(mainPath, tigPath);
      if (this.verbose) console.log(`  ✓ Synced: ${rp}`);
      return true;
    } catch (e) {
      console.log(`  ✗ Failed to sync ${rp}: ${e.message || e}`);
      return false;
    }
  }

  sync({ files = [], message = null, force = false } = {}) {
    this.force = !!force;
    if (!this.validateSetup()) return false;

    console.log('🔄 Tig Sync: Synchronizing manual edits');
    console.log('');
    const [modified, newFiles, deleted] = this.findModifiedFiles(files);
    this.files_modified = modified;
    this.files_added = newFiles;
    this.files_deleted = deleted;

    if (!modified.length && !newFiles.length && !deleted.length) {
      console.log('✅ No changes to sync - .tig is up to date');
      return true;
    }

    console.log('📁 Files to sync:');
    for (const f of modified) console.log(`  - ${f} (modified)`);
    for (const f of newFiles) console.log(`  - ${f} (new file)`);
    for (const f of deleted) console.log(`  - ${f} (deleted)`);
    console.log('');

    let successCount = 0;
    for (const f of [...modified, ...newFiles]) if (this.syncFileToTig(f)) { this.files_synced.push(f); successCount++; }
    for (const f of deleted) if (this.syncFileToTig(f, true)) successCount++;

    if (successCount === 0) {
      console.log('❌ No files were successfully synced');
      return false;
    }

    // Create commit
    try {
      execFileSync('git', ['add', '-A'], { cwd: this.tigDir, stdio: 'inherit' });
      let commitMessage;
      if (!message) {
        const parts = [];
        if (this.files_modified.length) parts.push(`modified ${this.files_modified.length} file(s)`);
        if (this.files_added.length) parts.push(`added ${this.files_added.length} file(s)`);
        if (this.files_deleted.length) parts.push(`deleted ${this.files_deleted.length} file(s)`);
        commitMessage = `manual: Sync ${parts.join(', ')}`;
      } else {
        commitMessage = `manual: ${message}`;
      }
      execFileSync('git', ['commit', '-m', commitMessage], { cwd: this.tigDir, stdio: 'ignore' });
      const commitHash = execFileSync('git', ['rev-parse', 'HEAD'], { cwd: this.tigDir, encoding: 'utf8' }).trim();

      console.log('');
      console.log(`✅ Synced ${successCount} file(s) to .tig`);
      console.log(`📝 Created manual sync commit: ${commitHash.slice(0, 8)}`);
      console.log("💡 Run 'tig blame' to see updated attributions");
      return true;
    } catch (e) {
      console.log(`❌ Failed to create commit: ${e.message || e}`);
      return false;
    }
  }
}

function parseArgs(argv) {
  const args = argv.slice(2);
  const out = { files: [], message: null, force: false, verbose: false };
  for (let i = 0; i < args.length; i++) {
    const a = args[i];
    if (a === '-m' || a === '--message') {
      i++; out.message = args[i] || '';
    } else if (a === '-f' || a === '--force') {
      out.force = true;
    } else if (a === '-v' || a === '--verbose') {
      out.verbose = true;
    } else {
      out.files.push(a);
    }
  }
  return out;
}

function main(argv) {
  const opts = parseArgs(argv);
  const syncer = new TigSync(process.cwd(), opts.verbose);
  const ok = syncer.sync({ files: opts.files, message: opts.message, force: opts.force });
  process.exit(ok ? 0 : 1);
}

if (require.main === module) {
  main(process.argv);
}

