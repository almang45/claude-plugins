# spinner (Warframe fork)

Claude Code mod. A fork of [hoobnn's spinner](https://github.com/hoobnn/hoobnn-agent-mods/tree/main/claude-code/spinner)
(MIT) with six Warframe themes added. It pairs with the Warframe `spinnerVerbs` in
`settings.json`: the mod never touches the verbs and draws next to the engine's
spinner line, so "Bullet-Jumping…" keeps rolling.

| Theme | Stage (above the prompt) | Mascot | Pet |
|-------|--------------------------|--------|-----|
| `fissure` | Excalibur's Exalted Blade waves cut down Corrupted. Each kill sends Reactant to a `◈ n/10` count; at ten the relic goes Radiant | `⟨◈⟩` relic | Radiant relic |
| `titania` | Razorwing over a fae meadow, with Razorflies circling, Dex Pixia bolts, and Spellbound Grineer lifted away in petals | `ƸӜƷ` | Razorwing |
| `khora` | The whip lashing out, Venari prowling, Strangledome closing over foes, and Pilfering loot | `ᓚᘏᗢ ∿` | Venari |
| `dante` | Noctua's Pageflight, Dark ◐ and Light ◑ verses stacking, then a Final Verse: Tragedy or Elegy | `✎ ◐◑` | Noctua |
| `gyre` | The Arcsphere in orbit, Coil Horizon's vortex, and lightning on every foe it holds | `◎ϟ` | Arcsphere |
| `qorvex` | The Chyrinka Pillar rising and irradiating, Containment Wall crushing foes, and Crucible Blast while it writes | `▐▓▌` | Qorvex helm |

The scenes follow the turn: thicker waves of foes while a tool runs, slower ones
while it waits on you, and a `?` over the frame when it asks.

## Install

```bash
claude plugin install spinner@alm-plugins
```

Don't also install `spinner@hoobnn-agent-mods`: both register `/spinner` and the same state.

```
/spinner fissure          # or titania, khora, dante, gyre, qorvex
/spinner random           # a Warframe theme each session (the default)
/spinner preview khora    # eight seconds, no turn needed
/spinner companion off    # moves the mascot from the pet row to beside the spinner verb
/spinner stage off        # hides the scene band above the prompt (stage on restores it)
/spinner pet              # pats the companion
/spinner off              # all animations off (/spinner on restores them)
```

Every upstream theme (`clawd`, `thunder`, `audio`, …) still works by name. Only
`random` is limited to the Warframe ones. `audio` needs macOS 14.2+, `swiftc`
(Xcode Command Line Tools) and System Audio Recording allowed for your terminal.

## Changes from upstream

- `hooks/warframe.ts`: the six themes, their scenes and their pets. All new code lives here.
- `hooks/themes.ts`: Warframe names come first in `THEME_NAMES`, and `pickRandom` draws from them.
- `hooks/pets.ts`: adds the Warframe pets.
- `hooks/scenes.ts`: exports `glyphStars`, `ridge`, `ground` and `clouds` for reuse.
- `tests/warframe.test.ts`: covers the random pool and the pets. Upstream's width test
  already covers every scene, finale and pet row.

To sync with upstream, copy its `claude-code/spinner` over this folder, keep
this README and `.claude-plugin/plugin.json` (the fork's name, version and
Warframe `theme` options), and re-apply the four small edits above. `warframe.ts` relies only on the `Theme` and
`PetArt` shapes and the cell and scene helpers.

## Check

```bash
claude plugin validate plugins/spinner
claude plugin test plugins/spinner
```
