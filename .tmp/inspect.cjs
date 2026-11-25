const { parse } = require(process.argv[2]);
const fs = require('fs');
const p = parse(fs.readFileSync(process.argv[3], 'utf8'));
console.log('top keys:', Object.keys(p));
console.log('profile keys:', Object.keys(p.profile));
console.log('app type:', typeof p.profile.app, JSON.stringify(p.profile.app));
console.log('command keys:', Object.keys(p.profile.commands));
