#!/usr/bin/env node
/**
 * Tig Local Query Engine (Node)
 * Mirrors tig_local_query.py behavior: given a commit hash and file path,
 * reads .tig/micro_index.json and shadow files to return conversation context.
 */

const fs = require('fs');
const path = require('path');

function findTigDir(startDir = process.cwd()) {
  let current = startDir;
  while (true) {
    const maybe = path.join(current, '.tig');
    if (fs.existsSync(maybe)) return maybe;
    const parent = path.dirname(current);
    if (parent === current) break;
    current = parent;
  }
  return null;
}

function loadJson(filePath, fallback) {
  try {
    const raw = fs.readFileSync(filePath, 'utf8');
    return JSON.parse(raw);
  } catch (_) {
    return fallback;
  }
}

class TigLocalQuery {
  constructor(tigDir) {
    this.tigDir = tigDir || findTigDir();
    if (!this.tigDir) throw new Error('No .tig directory found');
    this.microIndexPath = path.join(this.tigDir, 'micro_index.json');
    this.shadowDir = path.join(this.tigDir, 'shadow');
    this.microIndex = loadJson(this.microIndexPath, {
      conversations: {},
      snapshots: {},
      last_conversation_id: 0,
      last_snapshot_id: 0,
      file_index: {},
    });
  }

  getShadowContext(filePath, conversationId) {
    const filename = path.basename(filePath);
    const shadowFile = path.join(this.shadowDir, `${filename}.tig`);
    if (!fs.existsSync(shadowFile)) return {};
    try {
      const data = JSON.parse(fs.readFileSync(shadowFile, 'utf8'));
      const history = Array.isArray(data.history) ? data.history : [];
      for (const entry of history) {
        if (entry && entry.conversation_id === conversationId) {
          return {
            ai_response: entry.ai_response || '',
            tool_operations: entry.tool_operations || [],
            user_prompt: entry.user_prompt || '',
            timestamp: entry.timestamp || '',
          };
        }
      }
    } catch (e) {
      // Swallow and return empty context to match Python script tolerance
    }
    return {};
  }

  getBlameInfo(commitHash, filePath) {
    // Find snapshot by commit hash (full or prefix match)
    let snapshot = null;
    for (const [snapId, snapData] of Object.entries(this.microIndex.snapshots || {})) {
      const stored = (snapData && snapData.commit) || '';
      if (stored === commitHash || stored.startsWith(commitHash)) {
        snapshot = snapData;
        break;
      }
    }

    if (!snapshot) {
      return {
        conversation_id: null,
        user_prompt: null,
        prompt: null,
        ai_response: null,
        timestamp: null,
        tool_operations: [],
      };
    }

    const convId = snapshot.conversation_id;
    const conversation = (this.microIndex.conversations || {})[convId] || {};
    const shadowContext = this.getShadowContext(filePath, convId) || {};
    const responses = Array.isArray(conversation.responses) ? conversation.responses : [];

    return {
      conversation_id: convId,
      user_prompt: conversation.prompt || '',
      prompt: conversation.prompt || '',
      ai_response: shadowContext.ai_response || (responses.length ? responses[0] : ''),
      timestamp: snapshot.timestamp || conversation.start_time || '',
      tool_operations: shadowContext.tool_operations || [],
      commit_hash: commitHash,
      file_path: filePath,
    };
  }
}

function printHuman(blameInfo) {
  if (blameInfo && blameInfo.conversation_id) {
    console.log(`Conversation: ${blameInfo.conversation_id}`);
    console.log(`Timestamp: ${blameInfo.timestamp || ''}`);
    console.log(`User Prompt: ${blameInfo.user_prompt || ''}`);
    const ai = blameInfo.ai_response || '';
    console.log(`AI Response: ${ai.substring(0, 200)}...`);
  } else {
    console.log('No conversation context found for this commit');
  }
}

function main(argv) {
  // Simple arg parsing: node script.js <commit_hash> <file_path> [--json]
  const args = argv.slice(2);
  if (args.length < 2) {
    console.error('Usage: tig_local_query.js <commit_hash> <file_path> [--json]');
    process.exit(1);
  }
  const commitHash = args[0];
  const filePath = args[1];
  const asJson = args.includes('--json');

  try {
    const engine = new TigLocalQuery();
    const info = engine.getBlameInfo(commitHash, filePath);
    if (asJson) {
      process.stdout.write(JSON.stringify(info, null, 2));
    } else {
      printHuman(info);
    }
  } catch (e) {
    if (asJson) {
      process.stdout.write(JSON.stringify({ error: String(e && e.message ? e.message : e) }));
    } else {
      console.error(`❌ Error: ${e && e.message ? e.message : e}`);
    }
    process.exit(1);
  }
}

if (require.main === module) {
  main(process.argv);
}

