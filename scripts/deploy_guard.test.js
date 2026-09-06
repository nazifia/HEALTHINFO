const assert = require('assert');
const check = require('./deploy_guard');
const built = () => true;

assert.strictEqual(check(['healthinfoweb'], { GCLOUD_PROJECT: 'healthinfoweb' }, built), null);
assert.strictEqual(check(['healthinfoapp2', 'healthinfoapp'], { GCLOUD_PROJECT: 'healthinfoapp' }, built), null);
assert.match(check(['healthinfoweb'], { GCLOUD_PROJECT: 'healthinfoapp2' }, built), /refusing to deploy/);
assert.match(check(['healthinfoweb'], {}, built), /\(none\)/);
assert.match(
  check(['healthinfoapp2', '--require', 'build/web/main.dart.js'], { GCLOUD_PROJECT: 'healthinfoapp2' }, () => false),
  /main\.dart\.js/
);

console.log('deploy_guard: ok');
