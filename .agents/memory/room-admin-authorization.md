---
name: Room-admin (Raum-Admin) authorization pattern
description: How room-scoped management routes must authorize, vs global-admin-only routes
---

# Room-admin authorization pattern

Raum-Admins manage only their own room(s); global admins manage everything plus
the global scope (room_id 0/None). The shared gate is `_room_manage_allowed(room_id)`
in `admin_dynamic.py` (global admin OR `is_room_admin(user_id, room_id)` with room_id>0).

**Why:** A teacher set as room admin previously got "Zugriff verweigert" on the
Kurse/Stundenplan quick-links because those routes used `_admin_required()` (global only).

**How to apply when adding room-scoped routes:**
- For edit/delete of a specific entity, derive `room_id` from the *persisted* entity
  (e.g. `course.room_id`), NOT from attacker-controlled form input — then authorize.
- For bulk-save endpoints that accept entity IDs from the form (e.g. course assignments),
  validate each ID belongs to the room (or is global) before persisting — IDs are forgeable.
- Keep genuinely global operations (classes, rooms, global periods/templates,
  booking-settings, database-settings, bulk holiday-block) as `_admin_required()` and
  hide their links/tabs from room admins in templates via an `is_global_admin` flag.
