const fs = require('fs');

const logPath = 'C:\\Users\\nferr\\.gemini\\antigravity\\brain\\eee4402c-9228-44d1-ba6b-366d51379fa5\\.system_generated\\logs\\transcript.jsonl';
const lines = fs.readFileSync(logPath, 'utf8').split('\n');

const fixes = [];
for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (!line.trim()) continue;
    try {
        const obj = JSON.parse(line);
        if (obj.created_at >= '2026-07-06T22:13:00Z' && obj.created_at <= '2026-07-06T22:48:00Z') {
            if (obj.tool_calls) {
                for (const call of obj.tool_calls) {
                    if (call.name === 'replace_file_content' || call.name === 'multi_replace_file_content') {
                        if (call.args.TargetFile.includes('antigravity_phone_chat\\\\')) {
                            const cleanFile = call.args.TargetFile.replace(/\\\\/g, '\\').replace(/^"/, '').replace(/"$/, '');
                            
                            // Check if contents are escaped strings
                            let target = call.args.TargetContent;
                            let repl = call.args.ReplacementContent;
                            
                            if (target && target.startsWith('"') && target.endsWith('"')) {
                                target = JSON.parse(target);
                            }
                            if (repl && repl.startsWith('"') && repl.endsWith('"')) {
                                repl = JSON.parse(repl);
                            }

                            if (target && repl) {
                                fixes.push({
                                    file: cleanFile,
                                    target: target,
                                    replacement: repl
                                });
                            } else if (call.args.ReplacementChunks) {
                                let chunkStr = call.args.ReplacementChunks;
                                if (chunkStr.startsWith('"') && chunkStr.endsWith('"')) {
                                    chunkStr = JSON.parse(chunkStr);
                                }
                                const chunks = typeof chunkStr === 'string' ? JSON.parse(chunkStr) : chunkStr;
                                for (const chunk of chunks) {
                                    fixes.push({
                                        file: cleanFile,
                                        target: chunk.TargetContent,
                                        replacement: chunk.ReplacementContent
                                    });
                                }
                            }
                        }
                    }
                }
            }
        }
    } catch(e) {}
}

let successCount = 0;
for (const fix of fixes) {
    if (!fs.existsSync(fix.file)) {
        console.log('File not found:', fix.file);
        continue;
    }
    let content = fs.readFileSync(fix.file, 'utf8');
    if (content.includes(fix.target)) {
        content = content.replace(fix.target, fix.replacement);
        fs.writeFileSync(fix.file, content);
        console.log('Successfully patched:', fix.file);
        successCount++;
    } else {
        console.log('Target not found in:', fix.file);
    }
}
console.log(`Applied ${successCount} out of ${fixes.length} fixes.`);
