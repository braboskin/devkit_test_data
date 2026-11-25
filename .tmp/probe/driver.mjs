import { probeParseProfileFile } from './probe.mjs';
import fs from 'node:fs';
const root = String.raw`X:\devkit_projects\projects\atlas`;
for (const f of [String.raw`X:\devkit_projects\projects\atlas\.tmp\profile-min.json`, String.raw`X:\devkit_projects\projects\atlas\.tmp\profile-atlas.yaml`]) {
  try {
    const p = probeParseProfileFile(f, root);
    console.log('OK', f, JSON.stringify(p).slice(0, 80));
  } catch (e) {
    console.log('FAIL', f, e.code, e.message, JSON.stringify(e.details));
  }
}
const t = fs.readFileSync(String.raw`X:\devkit_projects\projects\atlas\.tmp\profile-min.json`, 'utf8');
console.log('first char code:', t.charCodeAt(0), 'stripped:', JSON.stringify(t.replace(/^\uFEFF/, '').slice(0, 2)));
