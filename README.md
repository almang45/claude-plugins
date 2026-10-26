# alm-plugins

Claude Code plugins: session state you can hear and see from another tab, animated and
themed transcripts, live views of subagents and a session recap, and delegation and code
review through Google Antigravity sub-agents. chime and tabcolor are the owner's own; the
rest are forks or vendored copies of other authors' mods, each with its changes listed in
its README.

| Plugin | Version | Kind | What it does | Upstream |
|---|---|---|---|---|
| [chime](plugins/chime) | 0.4.0 | command hook | Plays a sound when a session finishes a turn or needs you | — |
| [tabcolor](plugins/tabcolor) | 0.10.0 | command hook | Tints the iTerm2 tab by session state (tmux `-CC`) | — |
| [spinner](plugins/spinner) | 0.6.0-warframe.1 | mod | Pixel scenes, a mascot and a companion pet, with six Warframe themes | [hoobnn](https://github.com/hoobnn/hoobnn-agent-mods/tree/main/claude-code/spinner) |
| [swarm](plugins/swarm) | 0.1.0 | mod | `/swarm`: a live map of subagents and agent teams | [OneWave AI](https://github.com/OneWave-AI/claude-code-mods/tree/main/swarm) |
| [session-wrapped](plugins/session-wrapped) | 0.1.0-alm.1 | mod | `/wrapped`: an animated session recap and a PNG card | [OneWave AI](https://github.com/OneWave-AI/claude-code-mods/tree/main/session-wrapped) |
| [skins](plugins/skins) | 0.1.1-alm.3 | mod | Themed tool rows, cards and spinner that keep your `spinnerVerbs` | [hellosverre](https://github.com/hellosverre/claude-skins) |
| [antigravity-agents](plugins/antigravity-agents) | 0.1.0-alm.4 | skills | Delegates audits and research to `agy` sub-agents; `/antigravity-agents:review` runs a parallel Gemini code review beside Claude Opus, verifies both and compares them | [markfulton](https://github.com/markfulton/claude-antigravity-agents) |

## Install

```bash
claude plugin marketplace add almang45/claude-plugins
claude plugin install <plugin>@alm-plugins
```

Updates arrive when a plugin's version changes:

```bash
claude plugin marketplace update alm-plugins
claude plugin update <plugin>@alm-plugins     # then restart the session
```

chime and tabcolor are macOS-only. swarm, session-wrapped and skins need Claude Code
2.1.287 or later. antigravity-agents needs a signed-in `agy`, and its review skill
also needs `python3` 3.9 or later.

## Develop

Run from the repo root:

```bash
claude --plugin-dir ./plugins/<plugin>       # load the working copy for one session
claude plugin validate .                     # marketplace manifest
claude plugin validate plugins/<plugin>
claude plugin test plugins/<plugin>          # spinner, swarm, session-wrapped, skins
./plugins/chime/test.sh
./plugins/tabcolor/test.sh
python3 -I plugins/session-wrapped/tests/test_usage.py
python3 -I plugins/antigravity-agents/tests/test_agy_review.py
```

Installed copies are cached by `version` in `plugins/<plugin>/.claude-plugin/plugin.json`,
so bump it with any change to hooks, skills or manifests. [AGENTS.md](AGENTS.md) has the
conventions.

## License

spinner, swarm, session-wrapped, skins and antigravity-agents are MIT, under their
authors' copyright, with the license in each folder. antigravity-agents' review skill
and opus-reviewer agent were added in this repo. chime and tabcolor carry no license file.
