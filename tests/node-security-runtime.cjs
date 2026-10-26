// Isolated loopback checks; does not load service configuration, flows or accounts.
const assert = require('node:assert/strict');
const http = require('node:http');
const zlib = require('node:zlib');
const {PassThrough} = require('node:stream');
const fs = require('node:fs');
const path = require('node:path');
const { createRequire } = require('node:module');
const root = path.resolve(process.argv[2]);
const app = createRequire(path.join(root, 'package.json'));
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

async function checkParsers() {
  const bodyParser = app('body-parser');
  const multer = app('multer');
  const json = bodyParser.json({limit: '16kb'});
  const upload = multer({fileFilter(req, file, cb) {
    setTimeout(() => file.originalname === 'reject' ? cb(new Error('expected rejection')) : cb(null, true), file.originalname === 'reject' ? 5 : 25);
  }}).any();
  const server = http.createServer((req, res) => {
    const parser = req.url === '/upload' ? upload : json;
    parser(req, res, err => {
      res.statusCode = err ? 400 : 200;
      res.end(err ? 'rejected' : JSON.stringify(req.body));
    });
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const port = server.address().port;
  async function request(url, body, headers, trailing) {
    return new Promise((resolve, reject) => {
      const req = http.request({host:'127.0.0.1', port, path:url, method:'POST', headers:{...headers,'Content-Length':body.length + (trailing?.length || 0)}}, res => {
        let out = ''; res.on('data', b => out += b); res.on('end', () => resolve({status:res.statusCode, body:out}));
      });
      req.on('error', reject);
      if (trailing) { req.write(body); setTimeout(() => req.end(trailing), 20); }
      else req.end(body);
    });
  }
  try {
    const payload = Buffer.from('{"ok":true}');
    const headers = {'Content-Type':'application/json','Content-Encoding':'gzip'};
    assert.equal((await request('/json', zlib.gzipSync(payload), headers)).status, 200);
    // Upstream GHSA-27r3-jxmh-p828: a valid frame, NUL and a later decoder write.
    const bad = await request('/json', Buffer.concat([zlib.gzipSync(payload), Buffer.from([0]), Buffer.alloc(100 * 1024, 0x58)]), headers);
    assert.ok([200,400].includes(bad.status));
    await delay(100); // A late decoder error used to escape the middleware.
    assert.equal((await request('/json', payload, {'Content-Type':'application/json'})).status, 200);
    const boundary = 'security-compatibility-check';
    function multipart(names) {
      return Buffer.from(names.map(name => `--${boundary}\r\nContent-Disposition: form-data; name="files"; filename="${name}"\r\nContent-Type: text/plain\r\n\r\nsmall test\r\n`).join('') + `--${boundary}--\r\n`);
    }
    const mh = {'Content-Type':`multipart/form-data; boundary=${boundary}`};
    assert.equal((await request('/upload', multipart(['normal']), mh)).status, 200);
    assert.equal((await request('/upload', multipart(['reject','pending']), mh)).status, 400);
    await delay(100); // The pending filter must not resume a destroyed stream.
    assert.equal((await request('/upload', multipart(['normal']), mh)).status, 200);
  } finally { await new Promise(resolve => server.close(resolve)); }
  console.log('PASS: JSON/gzip controls, trailing compressed bytes, multipart controls and pending-filter teardown');
}

// Upstream GHSA-q7qp-rjg7-q26m: pending callback after synthetic stream teardown.
async function checkMulterTeardown() {
  const req = new PassThrough();
  const expected = new Error('expected rejection');
  const boundary = 'IsolatedTeardown';
  const body = ['first','second'].map(name => `--${boundary}\r\nContent-Disposition: form-data; name="${name}"; filename="${name}.txt"\r\nContent-Type: text/plain\r\n\r\nx`).join('\r\n');
  req.headers = {'content-type':`multipart/form-data; boundary=${boundary}`, 'content-length':Buffer.byteLength(body)};
  let resume, parser, calls = 0;
  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('teardown completion timeout')), 2000);
    const upload = app('multer')({fileHwm:1,
      streamHandler(request, stream) { parser=stream; request.pipe(stream); },
      fileFilter(request, file, cb) {
        if (file.fieldname === 'first') resume=cb;
        else request.once('end', () => setImmediate(() => cb(expected)));
      }
    }).any();
    upload(req, null, error => {
      calls++;
      assert.equal(error, expected);
      setImmediate(() => {
        parser.once('close', () => { clearTimeout(timer); assert.equal(calls,1); assert.deepEqual(req.files,[]); resolve(); });
        resume(null,true);
      });
    });
    req.end(body);
  });
  console.log('PASS: pending multipart filter cannot emit an unhandled error after teardown');
}

async function checkUndici(req, label) {
  const undici = req('undici');
  const server = http.createServer((request, response) => {
    response.setHeader('Content-Encoding', request.url === '/bad' ? Array(50).fill('gzip').join(',') : 'gzip');
    response.end(zlib.gzipSync(Buffer.from('small control')));
  });
  await new Promise(resolve => server.listen(0,'127.0.0.1',resolve));
  const url = `http://127.0.0.1:${server.address().port}`;
  try {
    assert.equal(await (await undici.fetch(url)).text(), 'small control');
    await assert.rejects(async () => (await undici.fetch(url + '/bad')).text());
    await delay(50);
    assert.equal(await (await undici.fetch(url)).text(), 'small control');
  } finally { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); }
  console.log('PASS: ' + label + ' gzip fetch and excessive encodings handled without process failure');
}

(async () => {
  const name = JSON.parse(fs.readFileSync(path.join(root,'package.json'))).name;
  if (name === 'node-red') {
    if (process.argv[3] === '--multer-only') { await checkMulterTeardown(); return; }
    await checkParsers();
    await checkMulterTeardown();
  }
  if (name === 'openclaw') {
    const {z} = app('zod');
    let calls = 0;
    const schema = z.array(z.string().transform(x => { calls++; return x; })).max(2);
    assert.equal(schema.safeParse(Array(100).fill('x')).success, false);
    assert.equal(calls, 0, 'oversized collections must reject before visiting elements');
    assert.deepEqual(schema.parse(['ok']), ['ok']);
    await checkUndici(app, 'application Undici');
    console.log('PASS: Zod rejects oversized collections before element validation and accepts legitimate data');
  }
  const npm = createRequire(path.join(root,'node_modules/npm/package.json'));
  await checkUndici(npm, 'bundled npm Undici');
  const {Address6} = npm('ip-address');
  assert.equal(new Address6('::1').correctForm(),'::1');
  if (name === 'openclaw') {
    assert.deepEqual(npm('brace-expansion').expand('{a,b}'), ['a','b']);
    assert.equal(npm('postcss-selector-parser')().processSync('a > .example'), 'a > .example');
  }
  console.log('PASS: dependency API compatibility');
})().catch(error => { console.error(error); process.exitCode = 1; });
