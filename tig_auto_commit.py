#!/usr/bin/env uv run
# /// script
# dependencies = []
# ///
"""
Tig Auto-Commit - Auto-commit context and stage AI files after conversations
"""
import os
import sys
import subprocess
import json
from pathlib import Path

class TigAutoCommit:
    """Handles auto-committing context and staging AI files"""
    
    def __init__(self, project_dir: str = None):
        self.project_dir = project_dir or os.getcwd()
        self.tig_dir = os.path.join(self.project_dir, '.tig')
    
    def auto_commit_after_conversation(self, ai_modified_files: list = None):
        """
        Auto-commit context to .tig submodule and stage AI files in main repo
        
        Args:
            ai_modified_files: List of files modified by AI (relative to project root)
                              If None, will try to detect from session state
        """
        try:
            if not self._is_submodule_configured():
                print("ℹ️  Submodule not configured, skipping auto-commit")
                return False
            
            # Get AI modified files if not provided
            if ai_modified_files is None:
                ai_modified_files = self._detect_ai_modified_files()
            
            print(f"🔧 Auto-commit starting...")
            print(f"📁 AI modified files: {ai_modified_files}")
            
            if not ai_modified_files:
                print("ℹ️  No files to stage")
                return True
            
            # 1. Auto-commit context to .tig submodule
            self._commit_context_to_submodule()
            
            # 2. Stage AI-modified files in main repo (but don't commit)
            self._stage_ai_files_in_main_repo(ai_modified_files)
            
            # 3. Stage submodule update (but don't commit)
            self._stage_submodule_update()
            
            print(f"✅ Context auto-committed, {len(ai_modified_files)} files staged")
            print("💡 Run 'git commit -m \"your message\"' when ready")
            
            return True
            
        except Exception as e:
            print(f"❌ Auto-commit failed: {e}")
            return False
    
    def _is_submodule_configured(self) -> bool:
        """Check if .tig is configured as a submodule"""
        gitmodules_path = os.path.join(self.project_dir, '.gitmodules')
        if os.path.exists(gitmodules_path):
            with open(gitmodules_path, 'r') as f:
                return 'path = .tig' in f.read()
        return False
    
    def _detect_ai_modified_files(self) -> list:
        """Detect files modified by AI from micro_index snapshots"""
        ai_files = []
        
        # Read micro_index.json to get recent snapshots
        micro_index_path = os.path.join(self.tig_dir, 'micro_index.json')
        if os.path.exists(micro_index_path):
            try:
                with open(micro_index_path, 'r') as f:
                    micro_index = json.load(f)
                
                # Get the most recent conversation from snapshots
                snapshots = micro_index.get('snapshots', {})
                if snapshots:
                    # Get unique file paths from all snapshots
                    file_paths = set()
                    for snapshot_data in snapshots.values():
                        file_path = snapshot_data.get('file_path', '')
                        if file_path:
                            rel_path = self._make_relative_path(file_path)
                            if rel_path:
                                file_paths.add(rel_path)
                    
                    ai_files = list(file_paths)
                    
            except Exception as e:
                print(f"⚠️  Could not read micro_index: {e}")
        
        return ai_files
    
    def _make_relative_path(self, file_path: str) -> str:
        """Convert absolute path to relative path from project root"""
        if file_path.startswith('/'):
            if file_path.startswith(self.project_dir):
                return os.path.relpath(file_path, self.project_dir)
        return file_path
    
    def _commit_context_to_submodule(self):
        """Auto-commit conversation context to .tig submodule"""
        # Stage all changes in .tig
        subprocess.run(['git', 'add', '.'], cwd=self.tig_dir, check=True)
        
        # Check if there are changes to commit
        result = subprocess.run(['git', 'diff', '--cached', '--quiet'], 
                              cwd=self.tig_dir, capture_output=True)
        
        if result.returncode != 0:  # There are changes
            subprocess.run(['git', 'commit', '-m', 'tig: Update conversation context'], 
                         cwd=self.tig_dir, check=True)
            print("✅ Context committed to .tig submodule")
        else:
            print("ℹ️  No context changes to commit")
    
    def _stage_ai_files_in_main_repo(self, ai_files: list):
        """Stage AI-modified files in main repository (but don't commit)"""
        staged_files = []
        
        for file_path in ai_files:
            full_path = os.path.join(self.project_dir, file_path)
            if os.path.exists(full_path):
                subprocess.run(['git', 'add', file_path], cwd=self.project_dir, check=True)
                staged_files.append(file_path)
        
        if staged_files:
            print(f"✅ Staged {len(staged_files)} AI-modified files")
        else:
            print("ℹ️  No AI-modified files to stage")
    
    def _stage_submodule_update(self):
        """Stage .tig submodule update in main repository (but don't commit)"""
        subprocess.run(['git', 'add', '.tig'], cwd=self.project_dir, check=True)
        print("✅ Staged .tig submodule update")

def main():
    """Command line interface"""
    if len(sys.argv) > 1:
        # Files provided as arguments
        ai_files = sys.argv[1:]
        auto_commit = TigAutoCommit()
        auto_commit.auto_commit_after_conversation(ai_files)
    else:
        # Auto-detect files
        auto_commit = TigAutoCommit()
        auto_commit.auto_commit_after_conversation()

if __name__ == '__main__':
    main() 