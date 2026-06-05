---
name: LearnGrid Branding & Homepage
description: Constraints for brand renames and the marketing homepage in this Flask school-booking app
---

# Brand rename constraint: theme keys are NOT brand text
The admin theme slugs `slotra2` and `slotra-reloaded` look like old-brand leftovers but are **functional identifiers**, not display text.
**Why:** they are persisted in the DB (`admin_theme` config value), validated against `ADMIN_THEME_IDS` in app.py, and matched by CSS selectors `html[data-admin-theme="..."]` in static/admin-themes.css. Renaming them silently breaks theme application for any school that already saved one.
**How to apply:** during any brand rename, change only visible labels (template option text, homepage cards). Leave the slug values, the frozenset, and the CSS selectors untouched. Same for `localStorage 'slotra_widget_height'`.

# Marketing homepage must be in the setup bypass
The public homepage (`/homepage`, endpoints `serve_homepage` / `redirect_homepage`) is served via send_from_directory but is gated by the global `check_setup()` before_request, which redirects everything to the setup wizard until setup is complete.
**How to apply:** those two endpoints must stay in `_SETUP_BYPASS` so the public landing page is reachable on a fresh/un-setup instance.

# The one existing screenshot is the setup wizard, not the Wochenplan
`homepage/images/dashboard-wochenplan.png` is mis-named: it actually shows the Einrichtungs-Assistent (setup wizard), NOT the weekly plan/dashboard.
**How to apply:** keep marketing copy honest — the homepage frames it as the setup assistant. A real Wochenplan screenshot tour is still deferred/pending.
