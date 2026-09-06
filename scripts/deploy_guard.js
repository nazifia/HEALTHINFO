#!/usr/bin/env node
// Firebase predeploy guard: one directory, one project, one frontend.
//
// `web/` serves the static SPA (project healthinfoweb) and `mobile/` serves the
// Flutter web build (project healthinfoapp2). Running `firebase deploy -P <other>`
// from the wrong directory once pushed the Flutter build over the static site, so
// both URLs served the same frontend. This hook fails that deploy before it uploads.
//
// Usage: node ../scripts/deploy_guard.js <project-id>... [--require <path>]

const fs = require('fs');

function check(args, env, exists) {
  const allowed = [];
  const required = [];
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--require') required.push(args[++i]);
    else allowed.push(args[i]);
  }
  const project = env.GCLOUD_PROJECT || env.FIREBASE_PROJECT || '';
  if (!allowed.includes(project)) {
    return `refusing to deploy: this directory deploys only to ${allowed.join(' or ')}, got "${project || '(none)'}"`;
  }
  for (const file of required) {
    if (!exists(file)) return `refusing to deploy: ${file} is missing — build this frontend first`;
  }
  return null;
}

module.exports = check;

if (require.main === module) {
  const problem = check(process.argv.slice(2), process.env, (f) => fs.existsSync(f));
  if (problem) {
    console.error(problem);
    process.exit(1);
  }
}
