# Releasing Statutor

Python, the root plugin, and the Antigravity plugin share a version. npm and
Cargo have independent versions. The hardening candidate uses Python/plugin
0.7.5, npm 0.2.0, and Cargo 0.1.3. Read the manifests for later candidates.

1. Add behavioral regressions before fixing a reproduced failure. Run the
   affected tests, then obtain independent review of the final patch.
2. Reconcile TASKS and the bounded HANDOFF. Keep existing task IDs and append
   decisions. Update README/pre-commit pins and all relevant package manifests.
   Use the UTC verification date in HANDOFF so runners in earlier time zones
   do not see a future date.
3. Stage the candidate and run the full gate with Python `build`, `pytest`,
   and optional-test dependency `PyYAML`, Node 24, and Cargo available:

   ```sh
   python scripts/release_gate.py --tag v0.7.5 --dist-dir /tmp/statutor-release-dist
   ```

   The output directory must be empty. The gate tests a clone of the exact
   index, excludes untracked files, audits Python/npm/Cargo payloads, and
   smoke-tests the installed wheel. Trust approval is checked against the
   original repository, whose HEAD and tree must still match the snapshot.
   The dependency-free Python matrix separately exercises PyYAML absence.
4. Run the opt-in current-host probe under its temporary profiles:

   ```sh
   python scripts/global_e2e.py --json
   ```

   Version pins describe completed native probes. Update a pin only after
   executing its matching probe. An unavailable offline catalog is reported
   explicitly; on-disk projections do not prove model-visible discovery.
5. Push the reviewed branch, create a PR, and wait for its checks. Merge the
   verified revision before tagging. Preserve the regression/fix commit order
   when the repository permits merge commits.
6. Push the matching `v<python-version>` tag. The
   [publish workflow](https://github.com/hoohugokim/statutor/blob/main/.github/workflows/publish.yml)
   reruns the gate and publishes Python via PyPI trusted publishing. Check the
   workflow result and the actual registry version. Create GitHub release
   notes from the commits; keep release notes on GitHub Releases.
7. Publish the independent channels only after their package checks pass:

   ```sh
   npm whoami
   npm pack --ignore-scripts --pack-destination /tmp/statutor-native-dist
   npm publish /tmp/statutor-native-dist/statutor-0.2.0.tgz --access public
   cargo publish --locked --manifest-path crates/statutor/Cargo.toml
   ```

   Run npm packing from `adapters/opencode/`. Run Cargo from the reviewed
   checkout. npm authentication can require browser approval or a one-time
   password; Cargo requires a publishing token. Enter credentials through
   the registry's own login flow. Record a blocked channel as pending rather
   than marking the release complete.
8. Query [PyPI](https://pypi.org/pypi/statutor/json),
   [npm](https://registry.npmjs.org/statutor), and
   [crates.io](https://crates.io/api/v1/crates/statutor). Compare published
   package contents with the release source and smoke-test clean installs.
   Confirm the GitHub release points to the reviewed tag.
9. Refresh local CLI/plugin installations through their package commands.
   Begin fresh worker sessions after upgrading from an unscoped registry.
   Global instruction/skill migration is a separate opt-in operation.

Existing untracked notes are collaborator-owned working material. This
tracked runbook is available in clean clones and does not depend on them.
