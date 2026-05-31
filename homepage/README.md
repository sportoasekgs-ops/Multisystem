# Slotra – Marketing-Homepage

Statische Verkaufsseite für Einrichtungen mit buchbaren Kursen, Beratungen und Terminen (ohne technische Details).

## Anzeigen

Datei im Browser öffnen:

```
homepage/index.html
```

Oder lokal mit einem einfachen Server (optional):

```bash
cd homepage
python -m http.server 8080
```

Dann: `http://127.0.0.1:8080`

## Screenshots

Echte Produktbilder liegen in `homepage/images/`:

| Datei | Verwendung |
|-------|------------|
| `dashboard-wochenplan.png` | Hero + Galerie (Ausschnitte per CSS) |

Weitere PNGs einfach ablegen und in `index.html` in der Sektion `#produkt` verlinken.

## Anpassen

- **Kontakt-E-Mail:** in `index.html` im Bereich `#kontakt` (`mailto:`-Link)
- **Farben:** in `css/style.css` unter `:root` (`--brand`, …)

Die Seite ist bewusst unabhängig von der Flask-App und kann z. B. auf einer eigenen Domain oder als Unterordner gehostet werden.
