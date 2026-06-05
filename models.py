# Datenbankmodelle für das Buchungssystem mit Flask-SQLAlchemy
# Diese Datei definiert die Struktur der Datenbank-Tabellen für PostgreSQL

import json
from datetime import datetime

from werkzeug.security import check_password_hash, generate_password_hash

from database import db


class User(db.Model):
    """Benutzer-Modell für Lehrkräfte und Admins"""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), index=True)
    password_hash = db.Column(db.String(256), nullable=True)
    role = db.Column(db.String(20), nullable=False)

    bookings = db.relationship("Booking", backref="teacher", lazy=True)

    def set_password(self, password):
        """Setzt das Passwort (gehasht)"""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Überprüft das Passwort"""
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        """Konvertiert User zu Dictionary für Kompatibilität"""
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "password_hash": self.password_hash,
            "role": self.role,
        }


class Booking(db.Model):
    """Buchungs-Modell"""

    __tablename__ = "bookings"

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(10), nullable=False, index=True)
    weekday = db.Column(db.String(3), nullable=False)
    period = db.Column(db.Integer, nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    teacher_name = db.Column(db.String(100))
    teacher_class = db.Column(db.String(50))
    students_json = db.Column(db.Text, nullable=False)
    offer_type = db.Column(db.String(10), nullable=False)
    offer_label = db.Column(db.String(100), nullable=False)
    calendar_event_id = db.Column(db.String(200), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    admin_reply = db.Column(db.Text, nullable=True)
    is_exclusive = db.Column(db.Boolean, default=False, nullable=False)
    is_approved = db.Column(db.Boolean, default=True, nullable=False)
    is_request = db.Column(db.Boolean, default=False, nullable=False)
    status = db.Column(db.String(20), default="booked", nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    room_id = db.Column(db.Integer, db.ForeignKey("rooms.id"), nullable=True)

    notifications = db.relationship(
        "Notification",
        back_populates="booking",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def to_dict(self):
        """Konvertiert Booking zu Dictionary für Kompatibilität"""
        return {
            "id": self.id,
            "date": self.date,
            "weekday": self.weekday,
            "period": self.period,
            "teacher_id": self.teacher_id,
            "teacher_name": self.teacher_name,
            "teacher_class": self.teacher_class,
            "students_json": self.students_json,
            "offer_type": self.offer_type,
            "offer_label": self.offer_label,
            "calendar_event_id": self.calendar_event_id,
            "notes": self.notes,
            "admin_reply": self.admin_reply,
            "is_exclusive": self.is_exclusive,
            "is_approved": self.is_approved,
            "is_request": self.is_request,
            "status": self.status,
            "room_id": self.room_id,
            "created_at": self.created_at.isoformat()
            if isinstance(self.created_at, datetime)
            else self.created_at,
            "teacher_email": self.teacher.email if self.teacher else None,
        }


class SlotName(db.Model):
    """Modell für anpassbare Slot-Namen"""

    __tablename__ = "slot_names"

    id = db.Column(db.Integer, primary_key=True)
    weekday = db.Column(db.String(3), nullable=False)
    period = db.Column(db.Integer, nullable=False)
    label = db.Column(db.String(200), nullable=False)

    __table_args__ = (
        db.UniqueConstraint("weekday", "period", name="unique_weekday_period"),
    )

    def to_dict(self):
        """Konvertiert SlotName zu Dictionary"""
        return {
            "id": self.id,
            "weekday": self.weekday,
            "period": self.period,
            "label": self.label,
        }


class BlockedSlot(db.Model):
    """Modell für von Admins blockierte Slots (z.B. für Beratungsgespräche)"""

    __tablename__ = "blocked_slots"

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(10), nullable=False, index=True)
    weekday = db.Column(db.String(3), nullable=False)
    period = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(200), default="Beratung")
    icon = db.Column(db.String(10), default="🔧")
    blocked_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    room_id = db.Column(db.Integer, db.ForeignKey("rooms.id"), nullable=True)

    __table_args__ = (
        db.UniqueConstraint("date", "period", "room_id", name="unique_date_period_room_block"),
    )

    def to_dict(self):
        """Konvertiert BlockedSlot zu Dictionary"""
        return {
            "id": self.id,
            "date": self.date,
            "weekday": self.weekday,
            "period": self.period,
            "reason": self.reason,
            "icon": self.icon or "🔧",
            "blocked_by": self.blocked_by,
            "room_id": self.room_id,
            "created_at": self.created_at.isoformat()
            if isinstance(self.created_at, datetime)
            else self.created_at,
        }


class SystemConfig(db.Model):
    """System-Konfiguration als Key-Value-Tabelle"""

    __tablename__ = "system_config"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False, index=True)
    value = db.Column(db.Text, nullable=True)
    category = db.Column(db.String(50), nullable=False, default="general")
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def to_dict(self):
        return {
            "id": self.id,
            "key": self.key,
            "value": self.value,
            "category": self.category,
        }


class Period(db.Model):
    """Stundenzeiten – dynamisch aus DB statt hardcoded in config.py"""

    __tablename__ = "periods"

    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.Integer, nullable=False, unique=True)
    name = db.Column(db.String(100), nullable=False)
    start_time = db.Column(db.String(5), nullable=False)
    end_time = db.Column(db.String(5), nullable=False)
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    period_kind = db.Column(db.String(20), nullable=False, default="lesson")
    after_lesson = db.Column(db.Integer, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "number": self.number,
            "name": self.name,
            "start": self.start_time,
            "end": self.end_time,
            "sort_order": self.sort_order,
            "is_active": self.is_active,
            "period_kind": self.period_kind or "lesson",
            "after_lesson": self.after_lesson,
        }


class Course(db.Model):
    """Kurse/Angebote – fest (fester Wochentag+Stunde) oder frei (freie Wahl)"""

    __tablename__ = "courses"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    color = db.Column(db.String(7), default="#E91E63")
    icon = db.Column(db.String(10), nullable=True)
    course_type = db.Column(
        db.String(10), nullable=False, default="free"
    )  # 'fixed' or 'free'
    weekday = db.Column(db.String(3), nullable=True)
    period_number = db.Column(db.Integer, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    sort_order = db.Column(db.Integer, default=0)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "color": self.color,
            "icon": self.icon,
            "course_type": self.course_type,
            "weekday": self.weekday,
            "period_number": self.period_number,
            "is_active": self.is_active,
            "sort_order": self.sort_order,
        }


class SchoolClass(db.Model):
    """Schulklassen – dynamisch aus DB"""

    __tablename__ = "school_classes"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "sort_order": self.sort_order,
            "is_active": self.is_active,
        }


class Room(db.Model):
    """Raum-Modell"""

    __tablename__ = "rooms"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.String(300), nullable=True)
    color = db.Column(db.String(7), default="#6366f1")  # Hex-Farbe
    icon = db.Column(db.String(10), default="🏫")
    max_students = db.Column(db.Integer, nullable=True)  # NULL = globale Einstellung
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "color": self.color,
            "icon": self.icon,
            "max_students": self.max_students,
            "sort_order": self.sort_order,
            "is_active": self.is_active,
        }


class PasswordResetToken(db.Model):
    """Einmal-Token für Passwort-Reset (lokale Admin-Accounts)"""

    __tablename__ = "password_reset_tokens"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token = db.Column(db.String(64), unique=True, nullable=False, index=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship(
        "User", backref=db.backref("reset_tokens", cascade="all, delete-orphan")
    )


class Notification(db.Model):
    """Modell für Benachrichtigungen an Admins"""

    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(
        db.Integer,
        db.ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    recipient_role = db.Column(db.String(20), nullable=False, default="admin")
    recipient_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    notification_type = db.Column(db.String(50), nullable=False, default="new_booking")
    message = db.Column(db.String(500), nullable=False)
    is_read = db.Column(db.Boolean, default=False, nullable=False, index=True)
    read_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, index=True
    )
    metadata_json = db.Column(db.Text, nullable=True)

    booking = db.relationship("Booking", back_populates="notifications")

    def to_dict(self):
        """Konvertiert Notification zu Dictionary"""
        metadata = None
        if self.metadata_json:
            try:
                metadata = json.loads(self.metadata_json)
            except:
                metadata = None

        return {
            "id": self.id,
            "booking_id": self.booking_id,
            "recipient_role": self.recipient_role,
            "recipient_user_id": self.recipient_user_id,
            "notification_type": self.notification_type,
            "message": self.message,
            "is_read": self.is_read,
            "read_at": self.read_at.isoformat()
            if isinstance(self.read_at, datetime)
            else self.read_at,
            "created_at": self.created_at.isoformat()
            if isinstance(self.created_at, datetime)
            else self.created_at,
            "metadata": metadata,
            "booking": self.booking.to_dict() if self.booking else None,
        }


# Hilfsfunktionen für Kompatibilität mit dem alten Code


def create_user(username, password, role, email=None):
    """Erstellt einen neuen Benutzer in der Datenbank"""
    try:
        user = User(username=username, email=email, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        return user.id
    except Exception as e:
        db.session.rollback()
        print(f"Fehler beim Erstellen des Benutzers: {e}")
        return None


def get_user_by_username(username):
    """Sucht einen Benutzer anhand des Benutzernamens"""
    user = User.query.filter_by(username=username).first()
    return user.to_dict() if user else None


def get_user_by_email(email):
    """Sucht einen Benutzer anhand der E-Mail-Adresse"""
    user = User.query.filter_by(email=email).first()
    return user.to_dict() if user else None


def get_or_create_oauth_user(email, username, oauth_provider, oauth_id, role="teacher"):
    """Erstellt oder aktualisiert einen Benutzer basierend auf E-Mail (IServ SSO)"""
    try:
        # Suche nach E-Mail
        user = User.query.filter_by(email=email).first()

        if user:
            # Benutzer existiert, aktualisiere Rolle falls nötig
            user.role = role
            print(
                f"✅ Benutzer gefunden und aktualisiert: {email} (ID: {user.id}, Rolle: {role})"
            )
        else:
            # Neuen Benutzer ohne lokales Passwort anlegen.
            # OAuth-Benutzer sollen sich nicht mit einem bekannten Fallback-Passwort lokal anmelden können.
            user = User(
                username=email,
                email=email,
                role=role,
                password_hash=None,
            )
            db.session.add(user)
            print(f"✅ Neuer Benutzer erstellt: {email} (Rolle: {role})")

        db.session.commit()
        return user.to_dict()
    except Exception as e:
        db.session.rollback()
        print(f"❌ FEHLER beim Erstellen/Aktualisieren des Benutzers: {e}")
        print(f"   E-Mail: {email}")
        import traceback

        traceback.print_exc()
        return None


def get_user_by_id(user_id):
    """Sucht einen Benutzer anhand der ID"""
    if user_id == -1:
        return {"id": -1, "username": "demo_teacher", "email": "demo.teacher@example.com", "role": "teacher"}
    elif user_id == -2:
        return {"id": -2, "username": "demo_admin", "email": "demo.admin@example.com", "role": "admin"}
    user = User.query.get(user_id)
    return user.to_dict() if user else None


def verify_password(user_dict, password):
    """Überprüft, ob das eingegebene Passwort korrekt ist"""
    user = User.query.get(user_dict["id"])
    return user.check_password(password) if user else False


def change_user_password(user_id, old_password, new_password):
    """Ändert das Passwort eines Benutzers"""
    try:
        user = User.query.get(user_id)
        if not user:
            return {"success": False, "error": "Benutzer nicht gefunden"}

        if not user.check_password(old_password):
            return {"success": False, "error": "Altes Passwort ist falsch"}

        user.set_password(new_password)
        db.session.commit()
        return {"success": True, "message": "Passwort erfolgreich geändert"}
    except Exception as e:
        db.session.rollback()
        print(f"Fehler beim Ändern des Passworts: {e}")
        return {"success": False, "error": "Fehler beim Ändern des Passworts"}


def get_all_users():
    """Gibt alle Benutzer zurück (für Admin-Ansicht)"""
    users = User.query.order_by(User.role, User.username).all()
    return [u.to_dict() for u in users]


def create_booking(
    date,
    weekday,
    period,
    teacher_id,
    students,
    offer_type,
    offer_label,
    teacher_name=None,
    teacher_class=None,
    calendar_event_id=None,
    notes=None,
    admin_reply=None,
    is_exclusive=False,
    is_approved=None,
    room_id=None,
    status="booked",
    is_request=False,
):
    """Erstellt eine neue Buchung in der Datenbank"""
    try:
        students_json = json.dumps(students, ensure_ascii=False)
        if is_approved is None:
            is_approved = not is_exclusive
        booking = Booking(
            date=date,
            weekday=weekday,
            period=period,
            teacher_id=teacher_id,
            teacher_name=teacher_name,
            teacher_class=teacher_class,
            students_json=students_json,
            offer_type=offer_type,
            offer_label=offer_label,
            calendar_event_id=calendar_event_id,
            notes=notes,
            admin_reply=admin_reply,
            is_exclusive=is_exclusive,
            is_approved=is_approved,
            is_request=is_request,
            room_id=room_id,
            status=status,
            created_at=datetime.now(),
        )
        db.session.add(booking)
        db.session.commit()
        return booking.id
    except Exception as e:
        db.session.rollback()
        print(f"Fehler beim Erstellen der Buchung: {e}")
        return None


def get_bookings_for_date_period(date, period, room_id=None):
    """Gibt alle approved Buchungen für ein bestimmtes Datum und Stunde zurück"""
    query = Booking.query.filter_by(date=date, period=period, is_approved=True).filter(Booking.status != 'no_show')
    if room_id is not None:
        query = query.filter_by(room_id=room_id)
    bookings = query.order_by(Booking.created_at).all()
    return [b.to_dict() for b in bookings]


def count_students_for_period(date, period, room_id=None):
    """Zählt die Gesamtzahl der Schüler für eine bestimmte Stunde"""
    bookings = get_bookings_for_date_period(date, period, room_id=room_id)
    total = 0
    for booking in bookings:
        students = json.loads(booking["students_json"])
        total += len(students)
    return total


def check_student_double_booking(
    student_name, student_class, date, period, exclude_booking_id=None
):
    """
    Prüft, ob ein Schüler bereits für dieses Datum und diese Stunde gebucht ist.

    Args:
        student_name: Name des Schülers
        student_class: Klasse des Schülers
        date: Datum (YYYY-MM-DD)
        period: Stunde (1-6)
        exclude_booking_id: Optional - Buchungs-ID die ausgeschlossen werden soll (für Updates)

    Returns:
        Dict mit 'is_booked' (bool) und 'booking_info' (str) oder None
    """
    bookings = get_bookings_for_date_period(date, period)

    for booking in bookings:
        # Überspringe die Buchung, die ausgeschlossen werden soll
        if exclude_booking_id and booking["id"] == exclude_booking_id:
            continue

        students = json.loads(booking["students_json"])

        # Prüfe ob der Schüler in dieser Buchung ist
        for student in students:
            if (
                student.get("name", "").strip().lower() == student_name.strip().lower()
                and student.get("klasse", "").strip().lower()
                == student_class.strip().lower()
            ):
                return {
                    "is_booked": True,
                    "booking_info": f"{student_name} ({student_class}) ist bereits in '{booking['offer_label']}' bei {booking['teacher_name']} gebucht.",
                }

    return {"is_booked": False, "booking_info": None}


def get_all_bookings():
    """Gibt alle Buchungen zurück (für Admin-Ansicht)"""
    bookings = Booking.query.filter(Booking.is_request == False).order_by(Booking.date.desc(), Booking.period).all()
    return [b.to_dict() for b in bookings]


def get_bookings_by_date(date):
    """Gibt alle Buchungen für ein bestimmtes Datum zurück"""
    bookings = Booking.query.filter_by(date=date).filter(Booking.status != 'no_show', Booking.is_request == False).order_by(Booking.period).all()
    return [b.to_dict() for b in bookings]


def get_bookings_for_week(start_date, end_date, room_id=None):
    """Gibt alle Buchungen für eine Woche zurück"""
    query = Booking.query.filter(Booking.date >= start_date, Booking.date <= end_date).filter(Booking.status != 'no_show', Booking.is_request == False)
    if room_id is not None:
        query = query.filter_by(room_id=room_id)
    bookings = query.order_by(Booking.date, Booking.period).all()
    return [b.to_dict() for b in bookings]


def get_booking_by_id(booking_id):
    """Gibt eine einzelne Buchung anhand der ID zurück"""
    booking = Booking.query.get(booking_id)
    return booking.to_dict() if booking else None


def get_exclusive_booking_for_date_period(date, period, room_id=None):
    """Prüft ob eine genehmigte exklusive Buchung für diesen Slot existiert"""
    query = Booking.query.filter_by(
        date=date, period=period, is_exclusive=True, is_approved=True
    ).filter(Booking.status != 'no_show')
    if room_id is not None:
        query = query.filter_by(room_id=room_id)
    booking = query.first()
    return booking.to_dict() if booking else None


def get_pending_exclusive_bookings():
    """Gibt alle exklusiven Buchungen und Anfragen zurück, die noch auf Freigabe warten"""
    bookings = (
        Booking.query.filter_by(is_approved=False)
        .filter(Booking.status != 'no_show')
        .filter(Booking.status != 'rejected')
        .order_by(Booking.date, Booking.period)
        .all()
    )
    return [b.to_dict() for b in bookings]


def approve_exclusive_booking(booking_id):
    """Genehmigt eine exklusive Buchung"""
    try:
        booking = Booking.query.get(booking_id)
        if not booking:
            return False

        booking.is_approved = True
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        print(f"Fehler beim Genehmigen der Buchung: {e}")
        return False


def reject_exclusive_booking(booking_id):
    """Lehnt eine exklusive Buchung ab (löscht sie)"""
    return delete_booking(booking_id)


def update_booking(
    booking_id,
    date,
    weekday,
    period,
    teacher_id,
    students,
    offer_type,
    offer_label,
    teacher_name=None,
    teacher_class=None,
    notes=None,
    room_id=None,
):
    """Aktualisiert eine bestehende Buchung in der Datenbank"""
    try:
        booking = Booking.query.get(booking_id)
        if not booking:
            return False

        booking.date = date
        booking.weekday = weekday
        booking.period = period
        booking.teacher_id = teacher_id
        booking.teacher_name = teacher_name
        booking.teacher_class = teacher_class
        booking.students_json = json.dumps(students, ensure_ascii=False)
        booking.offer_type = offer_type
        booking.offer_label = offer_label
        booking.notes = notes
        if room_id is not None:
            booking.room_id = room_id

        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        print(f"Fehler beim Aktualisieren der Buchung: {e}")
        return False


def delete_booking(booking_id, delete_calendar_event_callback=None):
    """Löscht eine Buchung aus der Datenbank und optional den Google Calendar Eintrag"""
    try:
        booking = Booking.query.get(booking_id)
        if not booking:
            return False

        # Wenn Callback für Calendar-Löschung übergeben wurde, nutze ihn
        if delete_calendar_event_callback and booking.calendar_event_id:
            try:
                delete_calendar_event_callback(booking.calendar_event_id)
            except Exception as e:
                print(f"Warnung: Calendar Eintrag konnte nicht gelöscht werden: {e}")

        db.session.delete(booking)
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        print(f"Fehler beim Löschen der Buchung: {e}")
        return False


def get_custom_slot_name(weekday, period):
    """Gibt den angepassten Slot-Namen aus der Datenbank zurück"""
    slot = SlotName.query.filter_by(weekday=weekday, period=period).first()
    return slot.label if slot else None


def update_slot_name(weekday, period, label):
    """Aktualisiert oder erstellt einen angepassten Slot-Namen"""
    try:
        slot = SlotName.query.filter_by(weekday=weekday, period=period).first()
        if slot:
            slot.label = label
        else:
            slot = SlotName(weekday=weekday, period=period, label=label)
            db.session.add(slot)

        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        print(f"Fehler beim Aktualisieren des Slot-Namens: {e}")
        return False


def get_all_custom_slot_names():
    """Gibt alle angepassten Slot-Namen zurück"""
    slots = SlotName.query.all()
    return [s.to_dict() for s in slots]


def is_holiday_blocked_reason(reason):
    """True wenn der Sperrgrund Schulferien ist (nicht z. B. Beratung/Fortbildung)."""
    if not reason:
        return False
    return "ferien" in str(reason).strip().lower()


def is_slot_blocked(date, period, room_id=None):
    """Prüft, ob ein Slot für ein bestimmtes Datum und Stunde blockiert ist"""
    query = BlockedSlot.query.filter_by(date=date, period=period)
    if room_id is not None:
        query = query.filter_by(room_id=room_id)
    blocked = query.first()
    return blocked is not None


def get_blocked_slot(date, period, room_id=None):
    """Gibt den blockierten Slot zurück, falls vorhanden"""
    query = BlockedSlot.query.filter_by(date=date, period=period)
    if room_id is not None:
        query = query.filter_by(room_id=room_id)
    blocked = query.first()
    return blocked.to_dict() if blocked else None


def block_slot(date, weekday, period, admin_id, reason="Beratung", icon="🔧", room_id=None):
    """Blockiert einen Slot für Beratungsgespräche (nur Admin)"""
    try:
        if is_slot_blocked(date, period, room_id=room_id):
            return False

        blocked = BlockedSlot(
            date=date,
            weekday=weekday,
            period=period,
            reason=reason,
            icon=icon,
            blocked_by=admin_id,
            room_id=room_id,
            created_at=datetime.now(),
        )
        db.session.add(blocked)
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        print(f"Fehler beim Blockieren des Slots: {e}")
        return False


def unblock_slot(date, period, room_id=None):
    """Gibt einen blockierten Slot wieder frei"""
    try:
        query = BlockedSlot.query.filter_by(date=date, period=period)
        if room_id is not None:
            query = query.filter_by(room_id=room_id)
        blocked = query.first()
        if not blocked:
            return False

        db.session.delete(blocked)
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        print(f"Fehler beim Freigeben des Slots: {e}")
        return False


def get_blocked_slots_for_date(date, room_id=None):
    """Gibt alle blockierten Slots für ein bestimmtes Datum zurück"""
    query = BlockedSlot.query.filter_by(date=date)
    if room_id is not None:
        query = query.filter_by(room_id=room_id)
    blocked_slots = query.all()
    return [b.to_dict() for b in blocked_slots]


def get_blocked_slots_for_week(start_date, end_date, room_id=None):
    """Gibt alle blockierten Slots für eine Woche zurück"""
    query = BlockedSlot.query.filter(
        BlockedSlot.date >= start_date, BlockedSlot.date <= end_date
    )
    if room_id is not None:
        query = query.filter_by(room_id=room_id)
    blocked_slots = query.all()
    return [b.to_dict() for b in blocked_slots]


def get_all_blocked_slots():
    """Gibt alle blockierten Slots zurück (für Admin-Ansicht)"""
    blocked_slots = BlockedSlot.query.order_by(
        BlockedSlot.date.desc(), BlockedSlot.period
    ).all()
    return [b.to_dict() for b in blocked_slots]


def bulk_block_slots(
    start_date, end_date, admin_id, reason="Ferien", periods=None, icon=None, room_id=None
):
    """
    Blockiert alle Slots in einem Zeitraum (z.B. für Ferien).

    Args:
        start_date: Startdatum (YYYY-MM-DD String)
        end_date: Enddatum (YYYY-MM-DD String)
        admin_id: ID des Admins der die Sperrung durchführt
        reason: Grund für die Sperrung
        periods: Liste der Stunden (1-6), None = alle Stunden
        icon: Emoji-Icon für die Blockierung (optional)
        room_id: Optionaler Raum

    Returns:
        Dict mit 'success', 'blocked_count', 'skipped_count'
    """
    from datetime import datetime, timedelta

    # Icon aus reason extrahieren, falls nicht explizit angegeben
    if icon is None and reason:
        first_char = reason[0] if reason else ""
        if ord(first_char) > 127:
            icon = first_char
        else:
            icon = "🔧"

    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")

        if periods is None:
            periods = [1, 2, 3, 4, 5, 6]

        weekday_map = {
            0: "Mon",
            1: "Tue",
            2: "Wed",
            3: "Thu",
            4: "Fri",
            5: "Sat",
            6: "Sun",
        }
        blocked_count = 0
        skipped_count = 0

        if room_id is not None:
            rooms_to_block = [room_id]
        else:
            try:
                rooms_to_block = [r.id for r in Room.query.all()] or [None]
            except:
                rooms_to_block = [None]

        current = start
        while current <= end:
            # Nur Wochentage (Montag-Freitag)
            if current.weekday() < 5:
                date_str = current.strftime("%Y-%m-%d")
                weekday = weekday_map[current.weekday()]

                for period in periods:
                    for r_id in rooms_to_block:
                        # Prüfe ob bereits blockiert
                        if not is_slot_blocked(date_str, period, room_id=r_id):
                            blocked = BlockedSlot(
                                date=date_str,
                                weekday=weekday,
                                period=period,
                                reason=reason,
                                icon=icon,
                                blocked_by=admin_id,
                                room_id=r_id,
                                created_at=datetime.now(),
                            )
                            db.session.add(blocked)
                            blocked_count += 1
                        else:
                            skipped_count += 1

            current += timedelta(days=1)

        db.session.commit()
        return {
            "success": True,
            "blocked_count": blocked_count,
            "skipped_count": skipped_count,
        }
    except Exception as e:
        db.session.rollback()
        print(f"Fehler beim Bulk-Blockieren: {e}")
        return {
            "success": False,
            "error": str(e),
            "blocked_count": 0,
            "skipped_count": 0,
        }


def bulk_unblock_slots(start_date, end_date, periods=None, room_id=None):
    """
    Gibt alle blockierten Slots in einem Zeitraum wieder frei.

    Args:
        start_date: Startdatum (YYYY-MM-DD String)
        end_date: Enddatum (YYYY-MM-DD String)
        periods: Liste der Stunden (1-6), None = alle Stunden
        room_id: Optionaler Raum

    Returns:
        Dict mit 'success', 'unblocked_count'
    """
    try:
        query = BlockedSlot.query.filter(
            BlockedSlot.date >= start_date, BlockedSlot.date <= end_date
        )

        if periods:
            query = query.filter(BlockedSlot.period.in_(periods))

        if room_id is not None:
            query = query.filter_by(room_id=room_id)

        blocked_slots = query.all()
        unblocked_count = len(blocked_slots)

        for slot in blocked_slots:
            db.session.delete(slot)

        db.session.commit()
        return {"success": True, "unblocked_count": unblocked_count}
    except Exception as e:
        db.session.rollback()
        print(f"Fehler beim Bulk-Freigeben: {e}")
        return {"success": False, "error": str(e), "unblocked_count": 0}


def create_notification(
    booking_id,
    message,
    notification_type="new_booking",
    recipient_role="admin",
    recipient_user_id=None,
    metadata=None,
):
    """Erstellt eine neue Benachrichtigung"""
    try:
        metadata_json = json.dumps(metadata, ensure_ascii=False) if metadata else None
        notification = Notification(
            booking_id=booking_id,
            recipient_role=recipient_role,
            recipient_user_id=recipient_user_id,
            notification_type=notification_type,
            message=message,
            metadata_json=metadata_json,
            is_read=False,
            created_at=datetime.now(),
        )
        db.session.add(notification)
        db.session.commit()
        return notification.id
    except Exception as e:
        db.session.rollback()
        print(f"Fehler beim Erstellen der Benachrichtigung: {e}")
        return None


def get_unread_notifications(recipient_role="admin", recipient_user_id=None):
    """Gibt alle ungelesenen Benachrichtigungen zurück"""
    if recipient_user_id is not None:
        notifications = Notification.query.filter_by(recipient_user_id=recipient_user_id, is_read=False)
    else:
        notifications = Notification.query.filter_by(recipient_role=recipient_role, is_read=False)
    
    notifications = notifications.order_by(Notification.created_at.desc()).all()
    return [n.to_dict() for n in notifications]


def get_recent_notifications(recipient_role="admin", recipient_user_id=None, limit=10):
    """Gibt die neuesten Benachrichtigungen zurück (gelesen und ungelesen)"""
    if recipient_user_id is not None:
        notifications = Notification.query.filter_by(recipient_user_id=recipient_user_id)
    else:
        notifications = Notification.query.filter_by(recipient_role=recipient_role)
    
    notifications = notifications.order_by(Notification.created_at.desc()).limit(limit).all()
    return [n.to_dict() for n in notifications]


def mark_notification_as_read(notification_id):
    """Markiert eine Benachrichtigung als gelesen"""
    try:
        notification = Notification.query.get(notification_id)
        if not notification:
            return False
        notification.is_read = True
        notification.read_at = datetime.now()
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        print(f"Fehler beim Markieren der Benachrichtigung: {e}")
        return False


def mark_all_notifications_as_read(recipient_role="admin", recipient_user_id=None):
    """Markiert alle Benachrichtigungen als gelesen"""
    try:
        if recipient_user_id is not None:
            notifications = Notification.query.filter_by(
                recipient_user_id=recipient_user_id, is_read=False
            ).all()
        else:
            notifications = Notification.query.filter_by(
                recipient_role=recipient_role, is_read=False
            ).all()
        for notification in notifications:
            notification.is_read = True
            notification.read_at = datetime.now()
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        print(f"Fehler beim Markieren aller Benachrichtigungen: {e}")
        return False


class PeriodTemplate(db.Model):
    """Gespeicherte Stunden-Vorlagen"""

    __tablename__ = "period_templates"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.String(500), nullable=True)
    periods_json = db.Column(db.Text, nullable=False)  # JSON-Array der Perioden
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def get_periods(self):
        return json.loads(self.periods_json)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "periods": self.get_periods(),
            "created_at": self.created_at.strftime("%d.%m.%Y %H:%M")
            if self.created_at
            else "",
        }


def get_unread_notification_count(recipient_role="admin", recipient_user_id=None):
    """Gibt die Anzahl der ungelesenen Benachrichtigungen zurück"""
    if recipient_user_id is not None:
        return Notification.query.filter_by(
            recipient_user_id=recipient_user_id, is_read=False
        ).count()
    return Notification.query.filter_by(
        recipient_role=recipient_role, is_read=False
    ).count()


def delete_notification(notification_id):
    """Löscht eine Benachrichtigung"""
    try:
        notification = Notification.query.get(notification_id)
        if not notification:
            return False
        db.session.delete(notification)
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        print(f"Fehler beim Löschen der Benachrichtigung: {e}")
        return False


def get_all_rooms(active_only=True):
    """Gibt alle Räume zurück"""
    query = Room.query
    if active_only:
        query = query.filter_by(is_active=True)
    return query.order_by(Room.sort_order, Room.name).all()


def get_room_by_id(room_id):
    """Sucht einen Raum nach ID"""
    return Room.query.get(room_id)


def get_default_room():
    """Gibt den Standardraum zurück (erster Raum)"""
    room = Room.query.order_by(Room.id).first()
    if not room:
        return None
    return room


def create_room(name, description=None, color="#6366f1", icon="🏫", max_students=None, sort_order=0):
    """Erstellt einen neuen Raum"""
    try:
        room = Room(
            name=name,
            description=description,
            color=color,
            icon=icon,
            max_students=max_students,
            sort_order=sort_order
        )
        db.session.add(room)
        db.session.commit()
        return room.id
    except Exception as e:
        db.session.rollback()
        print(f"Fehler beim Erstellen des Raums: {e}")
        return None


def update_room(room_id, **kwargs):
    """Aktualisiert Raumdaten"""
    try:
        room = Room.query.get(room_id)
        if not room:
            return False
        for key, value in kwargs.items():
            if hasattr(room, key):
                setattr(room, key, value)
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        print(f"Fehler beim Aktualisieren des Raums: {e}")
        return False


def delete_room(room_id):
    """Löscht einen Raum"""
    try:
        room = Room.query.get(room_id)
        if not room:
            return False
        # Prüfen ob Buchungen vorhanden sind
        bookings_count = Booking.query.filter_by(room_id=room_id).count()
        if bookings_count > 0:
            return False
        db.session.delete(room)
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        print(f"Fehler beim Löschen des Raums: {e}")
        return False
