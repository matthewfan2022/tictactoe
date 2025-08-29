#!/usr/bin/env uv run
# /// script
# dependencies = []
# ///
"""
Stop Hook - Process completed conversations for Tig
"""
import json
import sys
import os
import subprocess
from datetime import datetime

class TigConversationProcessor:
    def __init__(self, tig_dir):
        self.tig_dir = tig_dir
        self.git_dir = os.path.join(tig_dir, '.git')
        self.micro_index_path = os.path.join(tig_dir, 'micro_index.json')
        self.shadow_dir = os.path.join(tig_dir, 'shadow')
        
    def load_micro_index(self):
        """Load existing micro_index.json or create new one"""
        if os.path.exists(self.micro_index_path):
            with open(self.micro_index_path, 'r') as f:
                return json.load(f)
        return {
            'conversations': {},
            'snapshots': {},
            'last_conversation_id': 0,
            'last_snapshot_id': 0,
            'file_index': {}
        }
    
    def parse_transcript(self, transcript_path, conversation_start_time):
        """Parse JSONL transcript to extract AI responses for current conversation only"""
        conversation_data = {
            'ai_responses': [],
            'tool_operations': []
        }
        
        if not transcript_path or not os.path.exists(transcript_path):
            return conversation_data
            
        try:
            all_responses = []
            
            with open(transcript_path, 'r') as f:
                for line in f:
                    if line.strip():
                        entry = json.loads(line)
                        
                        if entry.get('type') == 'assistant':
                            content = entry.get('message', {}).get('content', [])
                            
                            # Extract text responses
                            text_content = []
                            for item in content:
                                if isinstance(item, dict) and item.get('type') == 'text':
                                    text_content.append(item.get('text', ''))
                                elif isinstance(item, dict) and item.get('type') == 'tool_use':
                                    conversation_data['tool_operations'].append({
                                        'tool_name': item.get('name'),
                                        'tool_input': item.get('input', {}),
                                        'timestamp': entry.get('timestamp')
                                    })
                            
                            if text_content:
                                response_text = ' '.join(text_content)
                                all_responses.append(response_text)
            
            # Simple approach: Take the last 3-5 responses from the transcript
            # This works because Claude Code conversations are typically recent responses
            if all_responses:
                # Take last 4 responses maximum, minimum 1
                conversation_data['ai_responses'] = all_responses[-4:] if len(all_responses) > 4 else all_responses[-len(all_responses):]
                
        except Exception as e:
            # If parsing fails completely, return empty but don't crash
            pass
            
        return conversation_data
    
    def create_git_commit(self, file_path, conversation_data, change_data, change_index):
        """Create Git commit for file change with descriptive message"""
        try:
            # Stage the file
            subprocess.run(['git', 'add', file_path], cwd=self.tig_dir, check=True)
            
            # Create descriptive commit message
            user_prompt = conversation_data.get('user_prompt', 'No prompt available')
            tool_name = change_data.get('tool_name', 'Unknown')
            
            # Truncate prompt if too long
            if len(user_prompt) > 60:
                user_prompt = user_prompt[:57] + "..."
            
            # Get file name for commit message
            file_name = os.path.basename(file_path)
            
            # Create multi-line commit message with context
            commit_msg = f"""tig: {tool_name} {file_name} - {user_prompt}

Conversation: {conversation_data['id']}
User Prompt: {conversation_data.get('user_prompt', 'No prompt available')}
Tool: {tool_name}
File: {file_path}
Timestamp: {change_data.get('timestamp', 'Unknown')}
Change #{change_index + 1} in conversation"""
            
            result = subprocess.run(
                ['git', 'commit', '-m', commit_msg], 
                cwd=self.tig_dir, 
                capture_output=True, 
                text=True
            )
            
            if result.returncode == 0:
                # Get commit hash
                hash_result = subprocess.run(
                    ['git', 'rev-parse', 'HEAD'], 
                    cwd=self.tig_dir, 
                    capture_output=True, 
                    text=True
                )
                return hash_result.stdout.strip()
        except:
            pass
        
        return None
    
    def update_tig_file(self, file_path, conversation_data):
        """Update .tig file with conversation history"""
        tig_file_path = os.path.join(self.shadow_dir, f"{file_path}.tig")
        os.makedirs(os.path.dirname(tig_file_path), exist_ok=True)
        
        # Load existing or create new .tig file
        if os.path.exists(tig_file_path):
            with open(tig_file_path, 'r') as f:
                tig_data = json.load(f)
        else:
            tig_data = {
                'file_path': file_path,
                'history': []
            }
        
        # Add new history entry
        entry = {
            'entry_id': f"entry_{len(tig_data['history']) + 1:03d}",
            'conversation_id': conversation_data['id'],
            'snapshot_ids': conversation_data.get('snapshot_ids', []),
            'timestamp': conversation_data['timestamp'],
            'user_prompt': conversation_data.get('user_prompt', ''),
            'tool_operations': conversation_data.get('tool_operations', []),
            'ai_response': conversation_data.get('ai_response', ''),
            'conversation_commit': conversation_data.get('commit_hash', '')
        }
        
        tig_data['history'].append(entry)
        
        # Save updated .tig file
        with open(tig_file_path, 'w') as f:
            json.dump(tig_data, f, indent=2)
    
    def process_conversation(self, session_state, transcript_path=None):
        """Process current conversation and update local storage"""
        conv_data = session_state.get('current_conversation')
        if not conv_data:
            return
        
        # Parse transcript for AI responses
        transcript_data = {}
        if transcript_path:
            transcript_data = self.parse_transcript(transcript_path, conv_data['start_time'])
        
        micro_index = self.load_micro_index()
        conv_id = conv_data['id']
        
        # Process file changes and create snapshots
        snapshot_ids = []
        for file_path, changes in conv_data.get('file_changes', {}).items():
            for i, change in enumerate(changes):
                # Create Git commit
                commit_hash = self.create_git_commit(
                    file_path, 
                    conv_data, # Pass conversation_data
                    change, # Pass change_data
                    i # Pass change_index
                )
                
                if commit_hash:
                    # Create snapshot entry
                    snapshot_id = f"snap_{micro_index['last_snapshot_id'] + 1:03d}"
                    micro_index['last_snapshot_id'] += 1
                    snapshot_ids.append(snapshot_id)
                    
                    micro_index['snapshots'][snapshot_id] = {
                        'id': snapshot_id,
                        'conversation_id': conv_id,
                        'tool_operation': f"{change['tool_name']}: {change.get('content', '')[:100]}...",
                        'file_path': os.path.join(os.getcwd(), file_path),
                        'commit': commit_hash,
                        'timestamp': change['timestamp'],
                        'sequence_number': len(snapshot_ids)
                    }
                    
                    # Update file index
                    if file_path not in micro_index['file_index']:
                        micro_index['file_index'][file_path] = []
                    micro_index['file_index'][file_path].append(conv_id)
        
        # Create conversation entry
        micro_index['last_conversation_id'] += 1
        
        # Get the best AI response using the same logic as shadow files
        ai_responses = transcript_data.get('ai_responses', [])
        best_ai_response = ''
        if ai_responses:
            # Take the last response that's not empty and not a generic greeting
            for response in reversed(ai_responses):
                if response and not response.strip().startswith("I see you've started"):
                    best_ai_response = response
                    break
            # If no relevant response found, take the last response
            if not best_ai_response and ai_responses:
                best_ai_response = ai_responses[-1]
        
        micro_index['conversations'][conv_id] = {
            'id': conv_id,
            'prompt': conv_data.get('user_prompt', ''),
            'start_time': conv_data['start_time'],
            'end_time': datetime.now().isoformat(),
            'snapshot_ids': snapshot_ids,
            'responses': [best_ai_response] if best_ai_response else [],  # Single best response instead of all responses
            'status': 'complete',
            'last_activity': datetime.now().isoformat(),
            'conversation_commit': snapshot_ids[-1] if snapshot_ids else None,
            'user_id': conv_data.get('user_id', 'unknown_user'),
            'user_email': conv_data.get('user_email', 'unknown@example.com')
        }
        
        # Update .tig files for each modified file
        for file_path in conv_data.get('file_changes', {}).keys():
            # Get the most relevant AI response (last non-empty response)
            ai_responses = transcript_data.get('ai_responses', [])
            relevant_ai_response = ''
            
            if ai_responses:
                # Take the last response that's not empty and not a generic greeting
                for response in reversed(ai_responses):
                    if response and not response.strip().startswith("I see you've started"):
                        relevant_ai_response = response
                        break
                # If no relevant response found, take the last response
                if not relevant_ai_response and ai_responses:
                    relevant_ai_response = ai_responses[-1]
            else:
                # Fallback: create a descriptive response based on the user prompt and tool operations
                user_prompt = conv_data.get('user_prompt', '')
                if user_prompt and len(user_prompt.strip()) > 1:
                    # Generate a basic response based on the user prompt
                    relevant_ai_response = f"Processed request: {user_prompt}"
                else:
                    relevant_ai_response = "File modified by Claude"
            
            # Get only the tool operations that affected THIS specific file
            file_specific_operations = []
            if file_path in conv_data.get('file_changes', {}):
                for change in conv_data['file_changes'][file_path]:
                    file_specific_operations.append(f"{change['tool_name']}: {str(change['tool_input'])}")
            
            # Get only the snapshots that affected THIS specific file
            file_specific_snapshot_ids = []
            file_specific_commit = None
            for snapshot_id in snapshot_ids:
                if snapshot_id in micro_index['snapshots']:
                    snapshot = micro_index['snapshots'][snapshot_id]
                    # Check if this snapshot's file_path matches our current file
                    snapshot_file_path = os.path.relpath(snapshot['file_path'], os.getcwd())
                    if snapshot_file_path == file_path:
                        file_specific_snapshot_ids.append(snapshot_id)
                        # The last snapshot for this file becomes the conversation commit
                        file_specific_commit = snapshot_id
            
            self.update_tig_file(file_path, {
                'id': conv_id,
                'snapshot_ids': file_specific_snapshot_ids,  # Only snapshots for this file
                'timestamp': conv_data['start_time'],
                'user_prompt': conv_data.get('user_prompt', ''),
                'tool_operations': file_specific_operations,  # Only operations for this file
                'ai_response': relevant_ai_response,
                'commit_hash': file_specific_commit,  # Last snapshot for this specific file
                'user_id': conv_data.get('user_id', 'unknown_user'),
                'user_email': conv_data.get('user_email', 'unknown@example.com')
            })
        
        # Save updated micro_index
        with open(self.micro_index_path, 'w') as f:
            json.dump(micro_index, f, indent=2)
    
    # Old auto-commit implementation removed - now using standalone tig_auto_commit.py
    
    def get_ai_modified_files_from_session(self, session_state):
        """Extract list of files modified by AI during this conversation"""
        ai_files = []
        
        # Try to get files from current_conversation.file_changes first
        current_conv = session_state.get('current_conversation')
        if current_conv and isinstance(current_conv, dict):
            file_changes = current_conv.get('file_changes', {})
        else:
            # Fallback to top-level file_changes
            file_changes = session_state.get('file_changes', {})
        
        for file_path in file_changes.keys():
            # Convert absolute paths to relative paths
            if file_path.startswith('/'):
                # Make relative to project directory
                project_dir = os.path.dirname(self.tig_dir)
                if file_path.startswith(project_dir):
                    rel_path = os.path.relpath(file_path, project_dir)
                    ai_files.append(rel_path)
            else:
                ai_files.append(file_path)
        
        return ai_files

def main():
    try:
        input_data = json.load(sys.stdin)
        transcript_path = input_data.get('transcript_path')
        
        tig_dir = os.path.join(os.getcwd(), '.tig')
        session_state_path = os.path.join(tig_dir, 'session_state.json')
        
        # Skip if no session state
        if not os.path.exists(session_state_path):
            sys.exit(0)
        
        # Load session state
        with open(session_state_path, 'r') as f:
            session_state = json.load(f)
        
        # Process the conversation (existing functionality)
        processor = TigConversationProcessor(tig_dir)
        try:
            processor.process_conversation(session_state, transcript_path)
        except Exception as e:
            print(f"⚠️  Conversation processing failed: {e}")
        
        # Extract AI-modified files BEFORE resetting current_conversation
        ai_modified_files = []
        current_conv = session_state.get('current_conversation')
        if current_conv and isinstance(current_conv, dict):
            file_changes = current_conv.get('file_changes', {})
            ai_modified_files = list(file_changes.keys())
        
        # Reset current conversation
        session_state['current_conversation'] = None
        
        # Auto-commit context and stage AI files 
        try:
            # Use standalone auto-commit utility for reliability
            project_dir = os.path.dirname(tig_dir)
            sys.path.append(project_dir)
            from tig_auto_commit import TigAutoCommit
            
            auto_commit = TigAutoCommit(project_dir)
            auto_commit.auto_commit_after_conversation(ai_modified_files)
        except Exception as e:
            print(f"⚠️  Auto-commit failed: {e}")
        with open(session_state_path, 'w') as f:
            json.dump(session_state, f, indent=2)
            
    except Exception as e:
        print(f"❌ Stop Hook error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()