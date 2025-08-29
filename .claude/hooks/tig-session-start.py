#!/usr/bin/env uv run
# /// script
# dependencies = [
#   "python-dotenv>=1.0.0"
# ]
# ///
"""
SessionStart Hook - Initialize Tig session and auto-sync contextbase
"""
import json
import sys
import os
import subprocess
import shutil
from datetime import datetime
from pathlib import Path

# Load environment variables from .env files
def load_tig_env():
    """Load environment variables from .env file in Tig project root"""
    try:
        from dotenv import load_dotenv
        
        # Find .env in current directory or parent directories
        current_dir = Path(os.getcwd())
        for parent in [current_dir] + list(current_dir.parents):
            env_file = parent / '.env'
            if env_file.exists():
                # Check if this looks like a tig project root (has tig_push.py)
                if (parent / 'tig_push.py').exists():
                    load_dotenv(env_file)
                    return True
        return False
    except ImportError:
        return False

# Try to load environment variables
load_tig_env()

class TigSessionManager:
    def __init__(self, project_dir):
        self.project_dir = project_dir
        self.tig_dir = os.path.join(project_dir, '.tig')
        self.config_path = os.path.join(self.tig_dir, 'config.json')
        self.session_state_path = os.path.join(self.tig_dir, 'session_state.json')
        
    # GCS sync functionality removed as part of database-to-git migration
        
    def ensure_tig_structure(self):
        """Create .tig directory structure if it doesn't exist (skips if submodule)"""
        # Skip if .tig is a submodule - it manages its own structure
        gitmodules_path = os.path.join(self.project_dir, '.gitmodules')
        if os.path.exists(gitmodules_path):
            with open(gitmodules_path, 'r') as f:
                if 'path = .tig' in f.read():
                    print("ℹ️  Skipping .tig structure creation (submodule manages its own structure)")
                    return
        
        # Only create regular .tig structure if no submodule exists
        os.makedirs(self.tig_dir, exist_ok=True)
        os.makedirs(os.path.join(self.tig_dir, 'cache'), exist_ok=True)
        os.makedirs(os.path.join(self.tig_dir, 'shadow'), exist_ok=True)
        
        # Create .gitignore to exclude session_state.json
        gitignore_path = os.path.join(self.tig_dir, '.gitignore')
        if not os.path.exists(gitignore_path):
            with open(gitignore_path, 'w') as f:
                f.write('session_state.json\n')
        
        # Initialize git repository if it doesn't exist
        git_dir = os.path.join(self.tig_dir, '.git')
        if not os.path.exists(git_dir):
            if not os.path.exists(git_dir):
                print("🔧 Initializing new git repository...")
            subprocess.run(['git', 'init'], cwd=self.tig_dir, check=True)
            
    def load_config(self):
        """Load or create Tig configuration"""
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r') as f:
                return json.load(f)
        
        # Default configuration
        config = {
            'contextbase_id': None,
            'mcp_server_configured': False,
            'last_sync': None,
            'created_at': datetime.now().isoformat()
        }
        
        with open(self.config_path, 'w') as f:
            json.dump(config, f, indent=2)
            
        return config
    
    def check_mcp_server(self):
        """Check if MCP server is available and configured"""
        try:
            # Try to call MCP server to get project context
            result = subprocess.run([
                'claude', 'mcp', 'list'
            ], capture_output=True, text=True, timeout=5)
            
            return 'tig-history' in result.stdout
        except:
            return False
    
    def detect_user_identity(self):
        """Detect user identity for testing"""
        # Manual override via environment variables (for testing)
        user_id = os.environ.get('TIG_USER_ID', 'test_user')
        user_email = os.environ.get('TIG_USER_EMAIL', 'test@example.com')
        
        return user_id, user_email
    
    def auto_sync_contextbase(self):
        """Automatically sync with contextbase if MCP server is available"""
        if not self.check_mcp_server():
            print("📝 Tig: No contextbase configured - starting in local mode")
            return False
            
        try:
            print("🔄 Tig: Syncing latest contextbase...")
            
            # This will be handled by MCP server calling get_project_context()
            # which provides Claude with the latest contextbase information
            
            config = self.load_config()
            config['last_sync'] = datetime.now().isoformat()
            config['mcp_server_configured'] = True
            
            with open(self.config_path, 'w') as f:
                json.dump(config, f, indent=2)
                
            print("✅ Tig: Contextbase sync complete")
            return True
            
        except Exception as e:
            print(f"⚠️  Tig: Sync failed - {e}")
            return False
    
    def initialize_session_state(self, session_id, user_id, user_email):
        """Initialize session tracking"""
        # Load existing session state to preserve conversation counter
        existing_counter = 1
        
        # First, sync with micro_index.json if it exists (source of truth)
        micro_index_path = os.path.join(self.tig_dir, 'micro_index.json')
        if os.path.exists(micro_index_path):
            try:
                with open(micro_index_path, 'r') as f:
                    micro_index = json.load(f)
                    # Next conversation should be last_conversation_id + 1
                    existing_counter = micro_index.get('last_conversation_id', 0) + 1
            except:
                pass  # Fall back to session state
        
        # If no micro_index, try to preserve existing session state counter
        if existing_counter == 1 and os.path.exists(self.session_state_path):
            try:
                with open(self.session_state_path, 'r') as f:
                    existing_state = json.load(f)
                    existing_counter = existing_state.get('conversation_counter', 1)
            except:
                pass  # Use default if file is corrupted
        
        session_state = {
            'session_id': session_id,
            'user_id': user_id,  # ✅ Store user identity
            'user_email': user_email,  # ✅ Store user email
            'current_conversation': None,
            'conversation_counter': existing_counter,  # ✅ PRESERVE EXISTING COUNTER
            'message_counter': 1,
            'start_time': datetime.now().isoformat(),
            'tracked_files': {},
            'pending_changes': []
        }
        
        with open(self.session_state_path, 'w') as f:
            json.dump(session_state, f, indent=2)

    def start_blame_api(self):
        """
        Start the Tig Blame API server if not already running
        """
        try:
            # Check if API is already running
            import urllib.request
            try:
                urllib.request.urlopen('http://localhost:8000/health', timeout=2)
                return True  # Already running
            except:
                pass  # Not running, continue to start it
            
            # Find the tig project root (where tig_blame_api.py is located)
            current_dir = Path(os.getcwd())
            tig_root = None
            
            for parent in [current_dir] + list(current_dir.parents):
                if (parent / 'tig_blame_api.py').exists():
                    tig_root = parent
                    break
            
            if not tig_root:
                print("ℹ️  Tig Blame API startup skipped (tig_blame_api.py not found)")
                return False
            
            # Start the API in background
            api_script = tig_root / 'tig_blame_api.py'
            subprocess.Popen([
                'uv', 'run', str(api_script)
            ], cwd=str(tig_root), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            print("🚀 Tig Blame API server started in background")
            return True
            
        except Exception as e:
            print(f"⚠️  Could not start Tig Blame API: {e}")
            return False
    
    def setup_submodule_if_needed(self):
        """Set up .tig as submodule if in a git repository and not already configured"""
        try:
            # Check if we're in a git repository
            result = subprocess.run(['git', 'rev-parse', '--git-dir'], 
                                  cwd=self.project_dir, capture_output=True)
            if result.returncode != 0:
                print("ℹ️  Not in git repository, skipping submodule setup")
                return False
            
            # Check if submodule already configured
            gitmodules_path = os.path.join(self.project_dir, '.gitmodules')
            if os.path.exists(gitmodules_path):
                with open(gitmodules_path, 'r') as f:
                    if 'path = .tig' in f.read():
                        print("ℹ️  Tig submodule already configured")
                        return True
            
            # Import and run submodule setup
            sys.path.append(self.project_dir)
            from tig_submodule_setup import TigSubmoduleManager
            
            manager = TigSubmoduleManager(self.project_dir)
            success = manager.setup_tig_submodule()
            
            if success:
                print("🎉 Tig submodule auto-configured for git-native branching!")
            
            return success
            
        except Exception as e:
            print(f"⚠️  Submodule auto-setup failed: {e}")
            return False

def main():
    try:
        input_data = json.load(sys.stdin)
        session_id = input_data['session_id']
        
        # Initialize Tig session
        project_dir = os.getcwd()
        session_manager = TigSessionManager(project_dir)
        
        # Set up submodule FIRST (before creating any .tig structure)
        session_manager.setup_submodule_if_needed()
        
        # Ensure directory structure (only if not submodule)
        session_manager.ensure_tig_structure()
        
        # Load configuration
        session_manager.load_config()
        
        # Auto-sync contextbase
        session_manager.auto_sync_contextbase()
        
        # Detect user identity
        user_id, user_email = session_manager.detect_user_identity()
        
        # Initialize session state
        session_manager.initialize_session_state(session_id, user_id, user_email)
        
        # Start Tig Blame API server
        session_manager.start_blame_api()
        
        # Output for Claude
        output = {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": "🐅 Tig session initialized. Ready to capture development context."
            }
        }
        print(json.dumps(output))
        
    except Exception as e:
        print(f"❌ Tig SessionStart error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()