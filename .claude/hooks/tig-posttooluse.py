#!/usr/bin/env uv run
# /// script
# dependencies = []
# ///
"""
PostToolUse Hook - Track file changes for Tig
"""
import json
import sys
import os
import hashlib
from datetime import datetime

def get_file_hash(file_path):
    """Get SHA-256 hash of file content"""
    try:
        with open(file_path, 'rb') as f:
            return hashlib.sha256(f.read()).hexdigest()
    except:
        return None

def get_file_content(file_path):
    """Get file content safely"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except:
        return None

def main():
    try:
        input_data = json.load(sys.stdin)
        tool_name = input_data['tool_name']
        tool_input = input_data['tool_input']
        tool_response = input_data['tool_response']
        
        # Only track file-modifying tools
        if tool_name not in ['Write', 'Edit', 'MultiEdit']:
            sys.exit(0)
        
        tig_dir = os.path.join(os.getcwd(), '.tig')
        session_state_path = os.path.join(tig_dir, 'session_state.json')
        
        # Skip if no session state
        if not os.path.exists(session_state_path):
            sys.exit(0)
        
        # Load session state
        with open(session_state_path, 'r') as f:
            session_state = json.load(f)
        
        if session_state['current_conversation'] is None:
            sys.exit(0)
        
        # Extract file path from tool input
        file_path = tool_input.get('file_path', tool_input.get('path'))
        if not file_path:
            sys.exit(0)
        
        # Make path relative to project root
        rel_path = os.path.relpath(file_path, os.getcwd())
        
        # Get file content for Tig storage
        file_content = get_file_content(file_path)
        file_hash = get_file_hash(file_path)
        
        # Record file change
        change_record = {
            'tool_name': tool_name,
            'file_path': rel_path,
            'file_hash': file_hash,
            'content': file_content,
            'timestamp': datetime.now().isoformat(),
            'tool_input': tool_input,
            'tool_response': tool_response
        }
        
        # Add to current conversation
        conv = session_state['current_conversation']
        if rel_path not in conv['file_changes']:
            conv['file_changes'][rel_path] = []
        conv['file_changes'][rel_path].append(change_record)
        
        # Copy file to .tig directory for Git tracking
        tig_file_path = os.path.join(tig_dir, rel_path)
        os.makedirs(os.path.dirname(tig_file_path), exist_ok=True)
        
        if file_content is not None:
            with open(tig_file_path, 'w', encoding='utf-8') as f:
                f.write(file_content)
        
        # Save updated state
        with open(session_state_path, 'w') as f:
            json.dump(session_state, f, indent=2)
            
    except Exception as e:
        # Fail silently
        pass

if __name__ == '__main__':
    main() 