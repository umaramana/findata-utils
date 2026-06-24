# Shell Merge — Single App Architecture Correction

**Context**
S1.2 was deployed as a standalone Apps Script web app (its own `index.html` + `Code.gs`, its own URL) with no navigation shell. This diverges from the wireframes' unified-app structure (`insight_wireframes_v6.html`): one deployed app, a tab-switcher at the top, every card from here on adding a tab to that same shell rather than spinning up a new deployment. This card retrofits S1.2 into that shell before F02-S02 adds the full assessment form as a second tab.

**No new wireframe** — reuses the tab-switcher pattern already built in `insight_wireframes_v6.html` (content blocks + a JS function toggling visibility).

**Build**
1. Restructure `index.html` to introduce the tab-switcher shell: a top-level nav with one entry per card-tab, content blocks per tab, JS visibility toggle — matching the `insight_wireframes_v6.html` pattern.
2. Move S1.2's existing check-in form markup and client-side JS into a "Check-In" tab content block. No behavior changes to the check-in form itself.
3. Introduce a shared client-side state object (selected client, selected date) that all tabs read/write, so switching tabs doesn't lose the trainer's current selection.
4. Re-verify the existing check-in flow (add-client, pre-fill, upsert/delete submit) is unchanged inside the new shell — this is a structural move, not a rewrite.
5. Redeploy as a single Apps Script web app. Retire the standalone S1.2 deployment URL once the merged shell is confirmed working; give Arun the new combined URL.

**Technical requirements**
1. No new unit tests — this is a structural move of existing, already-tested logic. Re-run S1.2's existing tests/acceptance checks against the new shell.
2. Health check / regression — n/a (no Python changes)
3. Error handling — unchanged, reuse what S1.2 already has
4. Auth — unchanged, reuse `sheets_auth.py` / GAS auth pattern
5. PWA — unchanged

**Acceptance criteria**
1. Single deployed Apps Script URL serves both the tab-switcher shell and the Check-In tab
2. Check-in form behaves identically to S1.2's standalone version — all 14 of S1.2's original acceptance criteria still pass inside the shell
3. Switching away from and back to the Check-In tab preserves the selected client and date
4. Old standalone S1.2 URL is retired; Arun is given the one merged URL
5. Shell has no other tabs populated yet — Check-In is the only active tab until F02-S02 adds the full assessment form tab

**Dependencies**
S1.2 complete (existing code being migrated, not rewritten). Must complete before F02-S02 starts, since F02-S02 adds its form as a tab inside this shell rather than a separate deployment.
