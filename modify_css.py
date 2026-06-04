import sys
import os
import re

filepath = r"c:\Users\Mauro\Desktop\MULTI REPLIT SYSTEM\Multisystem\static\admin-themes.css"

with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# Replace Professional section
content = re.sub(r'/\*\s*════[^\n]*\r?\n\s*2\.\s*PROFESSIONELL.*?(?=\r?\n/\*\s*════[^\n]*\r?\n\s*3\.\s*MINIMAL)', '', content, flags=re.DOTALL)

# Replace Elegant section 
content = re.sub(r'/\*\s*════[^\n]*\r?\n\s*4\.\s*ELEGANT.*?(?=\r?\n/\*\s*════[^\n]*\r?\n\s*5\.\s*SLOTRA 2\.0)', '', content, flags=re.DOTALL)

iserv_css = """
/* ═══════════════════════════════════════════════════════════════════════════
   ISERV – Schulportal-Look (vertraut, funktional, IServ-typisch)
   ═══════════════════════════════════════════════════════════════════════════ */
html[data-admin-theme="iserv"] {
    --font-heading: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    --font-body: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    --font-mono: 'Consolas', 'Courier New', monospace;
    --accent: #28a745;
    --accent-warn: #ffc107;
    --text-primary: #212529;
    --text-secondary: #495057;
    --text-tertiary: #6c757d;
    --bg-primary: #f5f6fa;
    --bg-secondary: #ebedf3;
    --bg-tertiary: #dee2e6;
    --bg-card: #ffffff;
    --border: #ced4da;
    --border-light: #dee2e6;
    --login-gradient: #f5f6fa;
    --shadow-sm: 0 1px 2px rgba(0,0,0,0.05);
    --shadow: 0 1px 3px rgba(0,0,0,0.08);
    --shadow-md: 0 3px 8px rgba(0,0,0,0.1);
    --shadow-lg: 0 6px 16px rgba(0,0,0,0.12);
    --radius-sm: 3px;
    --radius: 4px;
    --radius-lg: 6px;
    --radius-xl: 8px;
    --radius-2xl: 10px;
}

html[data-admin-theme="iserv"] body {
    background-color: #f5f6fa;
    background-image: none;
    letter-spacing: 0;
    line-height: 1.5;
}

html[data-admin-theme="iserv"] .bg-glow-orb {
    display: none;
}

html[data-admin-theme="iserv"] .top-nav {
    background: #074B83;
    border-bottom: 3px solid #053a66;
    box-shadow: 0 2px 6px rgba(0,0,0,0.15);
    padding: 0;
}

html[data-admin-theme="iserv"] .top-nav nav a {
    color: rgba(255,255,255,0.85);
    border-radius: 0;
    font-weight: 500;
    font-size: 0.85rem;
    padding: 0.75rem 1rem;
    text-transform: none;
    letter-spacing: 0;
    transition: background 0.15s ease;
}

html[data-admin-theme="iserv"] .top-nav nav a:hover {
    background: rgba(255,255,255,0.15);
    color: #ffffff;
    transform: none;
}

html[data-admin-theme="iserv"] .top-nav nav a.active {
    background: rgba(255,255,255,0.2);
    color: #fff;
    border-bottom: 2px solid #fff;
}

html[data-admin-theme="iserv"] .top-nav .nav-brand {
    color: #fff;
    font-weight: 700;
}

html[data-admin-theme="iserv"] .user-info {
    background: rgba(255,255,255,0.1);
    border: 1px solid rgba(255,255,255,0.2);
    border-radius: 4px;
    color: rgba(255,255,255,0.9);
}

html[data-admin-theme="iserv"] .btn {
    border-radius: 4px;
    border: 1px solid #ced4da;
    box-shadow: none;
    font-weight: 600;
    text-transform: none;
    letter-spacing: 0;
}

html[data-admin-theme="iserv"] .btn-primary {
    background: #074B83;
    border-color: #053a66;
    color: #fff;
}

html[data-admin-theme="iserv"] .btn-primary:hover {
    background: #053a66;
    transform: none;
    box-shadow: 0 2px 6px rgba(7,75,131,0.3);
}

html[data-admin-theme="iserv"] .btn-secondary {
    background: #ffffff;
    border-color: #ced4da;
    color: #212529;
}

html[data-admin-theme="iserv"] .btn-secondary:hover {
    background: #f5f6fa;
    border-color: #074B83;
    color: #074B83;
    transform: none;
}

html[data-admin-theme="iserv"] .dashboard-card,
html[data-admin-theme="iserv"] .week-overview,
html[data-admin-theme="iserv"] .login-box,
html[data-admin-theme="iserv"] .admin-card,
html[data-admin-theme="iserv"] .admin-section-modern,
html[data-admin-theme="iserv"] .date-selector {
    border-radius: 4px;
    border: 1px solid #dee2e6;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    background: #fff;
    transform: none;
}

html[data-admin-theme="iserv"] .dashboard-card:hover,
html[data-admin-theme="iserv"] .admin-card:hover {
    transform: none;
    border-color: #074B83;
    box-shadow: 0 2px 8px rgba(7,75,131,0.15);
}

html[data-admin-theme="iserv"] .dashboard-card .card-icon {
    border-radius: 4px;
    background: #074B83;
}

html[data-admin-theme="iserv"] .week-table {
    border: 1px solid #dee2e6;
    border-radius: 4px;
    overflow: hidden;
}

html[data-admin-theme="iserv"] .week-table th {
    background: #074B83;
    color: #ffffff;
    font-weight: 600;
    font-size: 0.8rem;
    text-transform: none;
    letter-spacing: 0;
    border-bottom: none;
    padding: 0.65rem 0.75rem;
}

html[data-admin-theme="iserv"] .week-table td {
    background: #fff;
    border-color: #dee2e6;
}

html[data-admin-theme="iserv"] .week-table tbody tr:nth-child(even) td {
    background: #f8f9fc;
}

html[data-admin-theme="iserv"] .slot-card {
    border-radius: 3px;
    border: 1px solid #dee2e6;
    box-shadow: none;
    background: #fff;
}

html[data-admin-theme="iserv"] .slot-card:hover {
    transform: none;
    border-color: #074B83;
    box-shadow: inset 0 0 0 1px #074B83;
}

html[data-admin-theme="iserv"] .slot-course-name {
    font-style: normal;
    font-weight: 600;
    text-transform: none;
    color: #212529;
    font-size: 0.8rem;
}

html[data-admin-theme="iserv"] .selected-date-info h3 {
    background: #074B83;
    border-radius: 4px;
    box-shadow: none;
}

html[data-admin-theme="iserv"] .login-box {
    border-radius: 6px;
    border: 1px solid #dee2e6;
}

html[data-admin-theme="iserv"] .dashboard-title,
html[data-admin-theme="iserv"] h2 {
    font-weight: 700;
    letter-spacing: 0;
    color: #212529;
}

html[data-admin-theme="iserv"] .week-dates {
    background: #e8f0f8;
    color: #074B83;
    border-radius: 4px;
    border: 1px solid #b8d4ed;
}

html[data-admin-theme="iserv"] .week-nav-arrow {
    border-radius: 4px;
    border: 1px solid #ced4da;
    background: #fff;
}

html[data-admin-theme="iserv"] .form-group input,
html[data-admin-theme="iserv"] .form-group select {
    border-radius: 4px;
    border-color: #ced4da;
}

html[data-admin-theme="iserv"] .message {
    border-radius: 4px;
    border-left-width: 4px;
}

html[data-admin-theme="iserv"] .stat-card {
    background: #074B83;
    border-radius: 6px;
}

html[data-admin-theme="iserv"] main.container {
    position: relative;
    z-index: 1;
}

/* IServ Dark Mode */
[data-theme="dark"] html[data-admin-theme="iserv"],
html[data-admin-theme="iserv"][data-theme="dark"] {
    --bg-primary: #1a1f2e;
    --bg-secondary: #242938;
    --bg-tertiary: #2e3446;
    --bg-card: #242938;
    --text-primary: #e4e7eb;
    --text-secondary: #9ca3af;
    --text-tertiary: #6b7280;
    --border: #374151;
    --border-light: #2e3446;
}

[data-theme="dark"] html[data-admin-theme="iserv"] .top-nav,
html[data-admin-theme="iserv"][data-theme="dark"] .top-nav {
    background: #052d50;
    border-bottom-color: #074B83;
}

/* IServ Pause Row Overrides */
html[data-admin-theme="iserv"] .week-table tr.week-row-pause td {
    border-radius: var(--radius);
}

html[data-admin-theme="iserv"] .week-table .period-row-label-pause {
    border-radius: var(--radius);
}

html[data-admin-theme="iserv"] .week-table .period-row-label-pause .period-row-label-title {
    margin-bottom: 0 !important;
    line-height: 1.2 !important;
}

html[data-admin-theme="iserv"] .week-table .period-row-label-pause .period-row-time {
    margin-top: 0.1rem !important;
    line-height: 1.2 !important;
}
"""

content += "\n" + iserv_css + "\n"

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)

print("SUCCESS")
