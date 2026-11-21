import { DatabaseSync } from 'node:sqlite';
const db = new DatabaseSync(process.env.USERPROFILE + '/.devkit/devkit.db');
console.log('projects', db.prepare('select id, slug from projects').all());
console.log('tasks', db.prepare("select id, project_id, status from tasks").all());
console.log('views', db.prepare("select name, type from sqlite_master where name in ('tasks','task_index')").all());
console.log('index rows', db.prepare("select task_id, project_id from task_index").all());
