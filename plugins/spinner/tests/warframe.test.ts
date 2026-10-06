import { expect, test } from 'claude-code/testing'

import { CLAWD_PET, petArtOf } from '../hooks/pets'
import { THEME_NAMES, isThemeName, pickRandom } from '../hooks/themes'
import { WARFRAME } from '../hooks/warframe'

test('random draws Warframe themes only, and reaches every one', async () => {
  const drawn = new Set(Array.from({ length: 400 }, (_, i) => pickRandom(i)))
  expect([...drawn].sort()).toEqual([...WARFRAME].sort())
})

test('every Warframe theme is a theme, with a pet of its own', async () => {
  for (const name of WARFRAME) {
    expect(isThemeName(name)).toBe(true)
    expect(THEME_NAMES).toContain(name)
    expect(petArtOf(name, '#000000').body).not.toEqual(CLAWD_PET.body)
  }
})
