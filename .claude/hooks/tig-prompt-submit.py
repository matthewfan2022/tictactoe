#!/usr/bin/env uv run
# /// script
# dependencies = []
# ///
"""
UserPromptSubmit Hook - Capture user prompts for Tig
"""
import json
import sys
import os
from datetime import datetime

def main():
    try:
        input_data = json.load(sys.stdin)
        prompt = input_data['prompt']
        session_id = input_data['session_id']
        
        # Load session state first to get user_id
        tig_dir = os.path.join(os.getcwd(), '.tig')
        session_state_path = os.path.join(tig_dir, 'session_state.json')
        
        # Skip if no session state (Tig not initialized)
        if not os.path.exists(session_state_path):
            sys.exit(0)
        
        # Load session state
        with open(session_state_path, 'r') as f:
            session_state = json.load(f)
        
        # Get user identity from session state
        user_id = session_state.get('user_id', 'unknown_user')
        user_email = session_state.get('user_email', 'unknown@example.com')
        
        # Start new conversation if needed
        if session_state['current_conversation'] is None:
            conv_id = f"conv_{session_state['conversation_counter']:03d}"
            session_state['current_conversation'] = {
                'id': conv_id,
                'start_time': datetime.now().isoformat(),
                'messages': [],
                'file_changes': {},
                'user_prompt': prompt,  # Store the initial prompt
                'user_id': user_id,
                'user_email': user_email
            }
            session_state['conversation_counter'] += 1
        
        # Record the prompt
        message_id = f"msg_{session_state['message_counter']:03d}"
        session_state['current_conversation']['messages'].append({
            'id': message_id,
            'type': 'user',
            'content': prompt,
            'timestamp': datetime.now().isoformat()
        })
        session_state['message_counter'] += 1
        
        # Save updated state
        with open(session_state_path, 'w') as f:
            json.dump(session_state, f, indent=2)
            
    except Exception as e:
        # Fail silently to not interrupt user experience
        pass

if __name__ == '__main__':
    main()