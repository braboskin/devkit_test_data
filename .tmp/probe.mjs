import { readFileSync } from 'node:fs';
const src = readFileSync('X:/dev/packages/core/src/task-service.ts','utf8');
const idx = src.indexOf("status === 'done'");
console.log('done idx', idx);
const need = src.match(/requiredChecksOk|checks.*required|gatesOk|canDone|doneBlocked/g);
console.log('markers', need);
