import { DatabaseSync } from 'node:sqlite';
import { attachTz } from 'file:///X:/dev/packages/core/src/doc-service.ts';
const db = new DatabaseSync(process.env.USERPROFILE + '/.devkit/devkit.db');
const out = attachTz(db, process.env.USERPROFILE + '/.devkit', 'testproject', 'E-46E212B4', { docId: 'TZ-52EEACD7' }, 'agent:T-78E09960/analyst', null);
console.log(JSON.stringify({ id: out.id, tz: out.tz && out.tz.id, tzPath: out.tz && out.tz.path }, null, 2));
