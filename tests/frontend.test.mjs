import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { selectLanguage, translate, formatCoefficient } from '../pvyieldlens/src/pvyieldlens/static/i18n.js';

test('selects supported preferences and regional variants with English fallback', () => {
  assert.equal(selectLanguage(['es-ES', 'de-AT']), 'de');
  assert.equal(selectLanguage(['fr-CA']), 'fr');
  assert.equal(selectLanguage(['zh-Hans-CN']), 'zh');
  assert.equal(selectLanguage(['pl-PL']), 'pl');
  assert.equal(selectLanguage(['it-IT']), 'it');
  assert.equal(selectLanguage(['es-ES']), 'en');
  assert.equal(selectLanguage([]), 'en');
});

test('falls back per key without showing untranslated keys', () => {
  assert.equal(translate({en:{hello:'Hello {name}'}, de:{}}, 'de','hello',{name:'Ada'}), 'Hello Ada');
});

test('coefficient formatting does not multiply datasheet percent by 100', () => {
  assert.equal(formatCoefficient(-0.35, 'en'), '-0.35 %/°C');
  assert.equal(formatCoefficient(-0.35, 'de'), '-0,35 %/°C');
});

test('all six catalogs provide complete matching placeholders', async () => {
  const catalogs = await Promise.all(['en','zh','fr','de','pl','it'].map(async language => JSON.parse(await readFile(
    new URL(`../pvyieldlens/src/pvyieldlens/static/locales/${language}.json`, import.meta.url), 'utf8'))));
  const keys = Object.keys(catalogs[0]).sort();
  assert.ok(keys.length > 60);
  for (const catalog of catalogs) {
    assert.deepEqual(Object.keys(catalog).sort(), keys);
    for (const key of keys) {
      assert.equal(typeof catalog[key], 'string');
      assert.ok(catalog[key].length);
      assert.deepEqual(catalog[key].match(/\{\w+\}/g), catalogs[0][key].match(/\{\w+\}/g));
    }
  }
});
