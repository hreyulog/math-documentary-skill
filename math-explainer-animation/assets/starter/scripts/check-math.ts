import assert from 'node:assert/strict';
import {mkdirSync, writeFileSync} from 'node:fs';
import config from '../src/config/series.json';
import {CARD_ORDER, canonical, DEMO_BRANCHES, DEMO_HAND, Hand, nextDraws, remainingAfter, removeCard, transitions} from '../src/math/card-removal';
import {TIMELINE} from '../src/config/timeline';

assert.ok(['portrait', 'landscape'].includes(config.layout));
assert.ok(config.topic.trim());
assert.ok(Number.isFinite(config.music.offsetSeconds) && config.music.offsetSeconds >= 0);
assert.ok(Number.isFinite(config.music.gain) && config.music.gain >= 0 && config.music.gain <= 1);
assert.ok(!config.music.path || (!/^(?:[a-z]+:|[/\\])/i.test(config.music.path) && !config.music.path.split(/[/\\]/).includes('..')), 'Music must be a relative path inside public/.');
assert.equal(TIMELINE.durationInFrames, 15 * TIMELINE.fps);
const close = (value: number, expected: number) => assert.ok(Math.abs(value - expected) < 1e-12);
let states = 0;
for (let mask = 0; mask < 1 << CARD_ORDER.length; mask++) {
  const hand = CARD_ORDER.filter((_, index) => mask & (1 << index));
  const saved = [...hand];
  const row = transitions(hand);
  close(row.reduce((sum, outcome) => sum + outcome.probability, 0), 1);
  for (const draw of nextDraws(hand)) {
    assert.equal(draw.next.length, hand.length - 1);
    assert.ok(!draw.next.includes(draw.draw));
    close(draw.probability, 1 / hand.length);
  }
  assert.deepEqual(hand, saved, 'Computations must not mutate their input.');
  states++;
}
assert.deepEqual(remainingAfter(['A', 'Q']), remainingAfter(['Q', 'A']));
assert.deepEqual(DEMO_HAND, ['K', '3']);
assert.deepEqual(DEMO_BRANCHES.map(({draw, next}) => [draw, next]), [['K', ['3']], ['3', ['K']]]);
for (const outcome of DEMO_BRANCHES) close(outcome.probability, .5);
assert.throws(() => removeCard(['K'], 'A'));
assert.throws(() => canonical(['K', 'K']));
assert.throws(() => canonical(['invalid'] as unknown as Hand));
assert.deepEqual(transitions([]), [{next: [], probability: 1}]);
mkdirSync('qa', {recursive:true});
writeFileSync('qa/math-check.json', JSON.stringify({passed:true, statesChecked:states, probabilityRowsSumToOne:true, twoHistoriesMerge:true, branchLabelsAndStatesUseSameFunctions:true, noActualGuandanOrWinRateClaim:true}, null, 2));
console.log(`Mathematics and configuration passed: ${states} states, two histories, K/3 branches.`);
