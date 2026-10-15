Check the change against this repository's own written rules, and check its tests.

- Read the instruction files first: AGENTS.md, CLAUDE.md, GEMINI.md and CONTRIBUTING.md at the
  root and next to the changed files, plus any linter, formatter or analyzer config (for
  example .golangci.yml, pyproject.toml, .eslintrc, checkstyle.xml, sonar-project.properties).
  Breaking a written rule is a finding. A personal preference is not.
- Tests: changed behaviour with no test, tests that cannot fail (no assertion, or asserting on
  the mock), tests that depend on time, ordering, the network or shared state, and tests that
  were deleted or skipped.
- Code health an analyzer would flag: logic duplicated from a helper that already exists (name
  it), dead code, functions the change made hard to follow.
- Files that must change together: version bumps, changelogs, READMEs, schemas or generated
  files that the repository's rules tie to this kind of change.

Quote the rule or the existing helper you rely on, with its file path.
