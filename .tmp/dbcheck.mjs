import { DatabaseSync } from 'node:sqlite';
const db = new DatabaseSync(process.env.USERPROFILE + '/.devkit/devkit.db');
const rows = db.prepare("select id, status, epic_id, project_id from tasks order by created_at").all();
console.log(rows);
const epics = db.prepare("select id, status from epics").all();
console.log('epics', epics);
