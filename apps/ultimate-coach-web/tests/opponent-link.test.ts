import { test } from 'node:test';
import assert from 'node:assert/strict';
import { opponentFromSearch } from '../src/components/opponent-link.ts';

test('scouting links select only opponents in the current fixture', () => {
  const opponents = [{ id: 'first' }, { id: 'other & player' }];
  assert.equal(opponentFromSearch('?opponent=other%20%26%20player', opponents), 'other & player');
  assert.equal(opponentFromSearch('?opponent=someone-else', opponents), null);
  assert.equal(opponentFromSearch('', opponents), null);
  assert.equal(opponentFromSearch('?opponent=first', []), null);
});
