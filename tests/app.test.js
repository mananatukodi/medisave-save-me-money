import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const html = readFileSync('index.html', 'utf8');
const js = readFileSync('src/app.js', 'utf8');
test('renders patient-first emergency and privacy entry points', () => {
  assert.match(html, /Get emergency help/);
  assert.match(html, /YOUR DATA, YOUR CONTROL/);
  assert.match(js, /Availability needs confirmation from the hospital/);
});
test('includes safety guardrails in functional dialog content', () => {
  assert.match(js, /not a doctor/);
  assert.match(js, /call your local emergency number/);
  assert.match(js, /not guarantees/);
});
