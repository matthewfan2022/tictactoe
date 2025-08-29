#!/usr/bin/env uv run
# /// script
# dependencies = []
# ///
"""
Tig Submodule Setup - Enable git-native branching with clean PR history
"""
import os
import sys
import subprocess
import tempfile
import shutil
import json
from pathlib import Path

class TigSubmoduleManager:
    """Manages .tig as a git submodule for clean PR history and branch following"""
    
    def __init__(self, project_dir: str = None):
        self.project_dir = project_dir or os.getcwd()
        self.tig_dir = os.path.join(self.project_dir, '.tig')
        self.tig_remote_dir = os.path.join(self.project_dir, '.tig-remote.git')
    
    def setup_tig_submodule(self):
        """
        Set up .tig as a git submodule with local bare repository as remote
        This enables branch following and clean PR history
        """
        print("🔧 Setting up Tig submodule for git-native branching...")
        
        # Check if we're in a git repository
        if not self._is_git_repo():
            print("❌ Not in a git repository. Initialize git first: git init")
            return False
        
        # Case 1: No .tig exists - create submodule from scratch (clean path)
        if not os.path.exists(self.tig_dir):
            return self._create_submodule_from_scratch()
        
        # Case 2: .tig exists and is already a submodule - do nothing
        if self._is_submodule_setup():
            print("✅ Tig submodule already configured")
            return True
        
        # Case 3: .tig exists as something else - user needs to clean up
        print("❌ .tig directory already exists but is not a Tig submodule")
        print("   Please remove .tig directory first: rm -rf .tig")
        print("   Then run setup again")
        return False
    
    def _create_submodule_from_scratch(self):
        """Create submodule when no .tig exists (clean path - no backup needed)"""
        print("📦 Creating fresh Tig submodule...")
        
        try:
            # Step 1: Create bare repository
            self._create_bare_remote()
            
            # Step 2: Create empty initial commit in bare repo
            self._create_initial_commit()
            
            # Step 3: Add as submodule (no existing directory to conflict)
            subprocess.run(['git', 'submodule', 'add', self.tig_remote_dir, '.tig'], 
                          cwd=self.project_dir, check=True)
            
            # Step 4: Initialize basic Tig structure in submodule
            self._initialize_tig_structure()
            
            # Step 5: Configure branch following
            self._configure_branch_following()
            
            # Step 6: Update .gitignore
            self._update_gitignore()
            
            print("✅ Fresh Tig submodule created successfully!")
            return True
            
        except Exception as e:
            print(f"❌ Fresh submodule creation failed: {e}")
            self._cleanup_failed_setup()
            return False
    
    # Migration methods removed - only supporting fresh submodule creation
    
    def _is_git_repo(self) -> bool:
        """Check if current directory is a git repository"""
        try:
            subprocess.run(['git', 'rev-parse', '--git-dir'], 
                         cwd=self.project_dir, capture_output=True, check=True)
            return True
        except subprocess.CalledProcessError:
            return False
    
    def _is_submodule_setup(self) -> bool:
        """Check if .tig is already configured as a submodule"""
        gitmodules_path = os.path.join(self.project_dir, '.gitmodules')
        if os.path.exists(gitmodules_path):
            with open(gitmodules_path, 'r') as f:
                content = f.read()
                return 'path = .tig' in content
        return False
    
    def _create_bare_remote(self):
        """Create bare repository to serve as submodule remote"""
        print("📦 Creating bare repository for submodule remote...")
        
        # Remove existing bare remote if it exists
        if os.path.exists(self.tig_remote_dir):
            shutil.rmtree(self.tig_remote_dir)
        
        # Create bare repository
        subprocess.run(['git', 'init', '--bare', self.tig_remote_dir], check=True)
        print(f"✅ Bare repository created: {self.tig_remote_dir}")
    
    def _create_initial_commit(self):
        """Create initial empty commit in bare repository"""
        print("📝 Creating initial commit in bare repository...")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Clone bare repo to temp directory
            subprocess.run(['git', 'clone', self.tig_remote_dir, temp_dir], check=True)
            
            # Create minimal initial structure
            with open(os.path.join(temp_dir, 'config.json'), 'w') as f:
                json.dump({'version': '1.0', 'type': 'tig-context'}, f, indent=2)
            
            # Create initial commit
            subprocess.run(['git', 'add', '.'], cwd=temp_dir, check=True)
            subprocess.run(['git', 'commit', '-m', 'tig: Initialize context repository'], 
                         cwd=temp_dir, check=True)
            subprocess.run(['git', 'push', 'origin', 'main'], cwd=temp_dir, check=True)
            
            print("✅ Initial commit created in bare repository")
    
    def _initialize_tig_structure(self):
        """Initialize basic Tig structure in the new submodule"""
        print("📁 Initializing Tig structure in submodule...")
        
        # Create basic structure
        os.makedirs(os.path.join(self.tig_dir, 'cache'), exist_ok=True)
        os.makedirs(os.path.join(self.tig_dir, 'shadow'), exist_ok=True)
        
        # Create .gitignore to exclude session_state.json
        gitignore_path = os.path.join(self.tig_dir, '.gitignore')
        with open(gitignore_path, 'w') as f:
            f.write('session_state.json\n')
        
        # Create micro_index.json
        micro_index = {
            'conversations': {},
            'snapshots': {},
            'last_conversation_id': 0,
            'last_snapshot_id': 0,
            'file_index': {}
        }
        
        micro_index_path = os.path.join(self.tig_dir, 'micro_index.json')
        with open(micro_index_path, 'w') as f:
            json.dump(micro_index, f, indent=2)
        
        print("✅ Tig structure initialized")
    
    def _populate_bare_remote(self):
        """Initialize bare remote with existing .tig content"""
        print("📁 Populating bare remote with existing .tig content...")
        
        # Create temporary directory for initial commit
        with tempfile.TemporaryDirectory() as temp_dir:
            # Clone the bare repo to temp directory
            subprocess.run(['git', 'clone', self.tig_remote_dir, temp_dir], check=True)
            
            # Copy existing .tig content (excluding .git directory)
            if os.path.exists(self.tig_dir):
                for item in os.listdir(self.tig_dir):
                    if item == '.git':
                        continue  # Skip existing .git directory
                    
                    src = os.path.join(self.tig_dir, item)
                    dst = os.path.join(temp_dir, item)
                    
                    if os.path.isdir(src):
                        shutil.copytree(src, dst)
                    else:
                        shutil.copy2(src, dst)
            
            # Create initial commit in temp repo
            subprocess.run(['git', 'add', '.'], cwd=temp_dir, check=True)
            
            # Check if there's anything to commit
            result = subprocess.run(['git', 'diff', '--cached', '--quiet'], 
                                  cwd=temp_dir, capture_output=True)
            
            if result.returncode != 0:  # There are changes to commit
                subprocess.run(['git', 'commit', '-m', 'tig: Initial context import'], 
                             cwd=temp_dir, check=True)
                subprocess.run(['git', 'push', 'origin', 'main'], 
                             cwd=temp_dir, check=True)
                print("✅ Initial content committed to bare remote")
            else:
                print("ℹ️  No existing content to import")
    
    # Old _add_submodule method removed - destructive backup logic eliminated
    # Only supporting fresh submodule creation via _create_submodule_from_scratch
    
    def _configure_branch_following(self):
        """Configure submodule to follow main repository branches"""
        print("🌿 Configuring branch following...")
        
        # Set submodule to follow the current branch
        subprocess.run(['git', 'config', '-f', '.gitmodules', 
                       'submodule..tig.branch', '.'], 
                      cwd=self.project_dir, check=True)
        
        # Update submodule configuration
        subprocess.run(['git', 'submodule', 'sync'], cwd=self.project_dir, check=True)
        
        print("✅ Branch following configured")
    
    def _update_gitignore(self):
        """Update .gitignore to exclude bare repository and backup files"""
        gitignore_path = os.path.join(self.project_dir, '.gitignore')
        
        entries_to_add = [
            ".tig-remote.git/",
            ".tig.backup/"
        ]
        
        existing_entries = set()
        if os.path.exists(gitignore_path):
            with open(gitignore_path, 'r') as f:
                existing_entries = set(line.strip() for line in f if line.strip())
        
        new_entries = [entry for entry in entries_to_add if entry not in existing_entries]
        
        if new_entries:
            with open(gitignore_path, 'a') as f:
                if existing_entries:  # Add newline if file exists
                    f.write('\n')
                f.write('# Tig submodule files\n')
                for entry in new_entries:
                    f.write(f'{entry}\n')
            print("✅ Updated .gitignore for submodule files")
    
    def _cleanup_failed_setup(self):
        """Clean up if submodule setup fails"""
        print("🧹 Cleaning up failed setup...")
        
        # Remove bare remote
        if os.path.exists(self.tig_remote_dir):
            shutil.rmtree(self.tig_remote_dir)
        
        # Remove .gitmodules entry if it exists
        gitmodules_path = os.path.join(self.project_dir, '.gitmodules')
        if os.path.exists(gitmodules_path):
            try:
                subprocess.run(['git', 'rm', '--cached', '.tig'], 
                             cwd=self.project_dir, capture_output=True)
                os.remove(gitmodules_path)
            except:
                pass
        
        # Restore backup if it exists
        backup_dir = f"{self.tig_dir}.backup"
        if os.path.exists(backup_dir):
            if os.path.exists(self.tig_dir):
                shutil.rmtree(self.tig_dir)
            shutil.move(backup_dir, self.tig_dir)
    
    def update_submodule_after_conversation(self, ai_files: list):
        """
        Update submodule after AI conversation
        This creates the clean commit structure described in the design doc
        """
        print("📝 Updating submodule after conversation...")
        
        try:
            # Step 1: Commit AI-modified files to main repository
            for file_path in ai_files:
                subprocess.run(['git', 'add', file_path], cwd=self.project_dir, check=True)
            
            # Step 2: Commit submodule changes
            subprocess.run(['git', 'add', '.'], cwd=self.tig_dir, check=True)
            
            # Check if there are changes to commit in submodule
            result = subprocess.run(['git', 'diff', '--cached', '--quiet'], 
                                  cwd=self.tig_dir, capture_output=True)
            
            if result.returncode != 0:  # There are changes
                subprocess.run(['git', 'commit', '-m', 'tig: Update conversation context'], 
                             cwd=self.tig_dir, check=True)
                
                # Step 3: Combined commit: AI files + submodule reference
                subprocess.run(['git', 'add', '.tig'], cwd=self.project_dir, check=True)
                
                commit_msg = f'feat: AI-assisted changes ({len(ai_files)} files + context)'
                subprocess.run(['git', 'commit', '-m', commit_msg], 
                             cwd=self.project_dir, check=True)
                
                print(f"✅ Created clean commit: {len(ai_files)} files + context")
            else:
                print("ℹ️  No context changes to commit")
                
        except Exception as e:
            print(f"❌ Failed to update submodule: {e}")
            return False
        
        return True

def main():
    """Command line interface for submodule setup"""
    if len(sys.argv) > 1 and sys.argv[1] == '--help':
        print("""
Tig Submodule Setup

Usage:
  tig_submodule_setup.py         # Set up .tig as submodule
  tig_submodule_setup.py --help  # Show this help

This enables:
- Git-native branching (context follows branches)
- Clean PR history (submodule updates appear as single line)
- Single hosting (everything in GitHub)
""")
        return
    
    manager = TigSubmoduleManager()
    success = manager.setup_tig_submodule()
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main() 