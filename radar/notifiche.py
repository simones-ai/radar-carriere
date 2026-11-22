"""Email con le nuove posizioni (Gmail o qualsiasi server SMTP)."""

import html
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

from classifica import CATEGORIE

PROTETTE = re.compile(r"categori[ae] protett|L\.?\s*68/99|art\.?\s*1/18", re.I)
COLORI = {"summer": "#b07800", "offcycle": "#c2185b", "stage": "#0277bd", "graduate": "#7b1fa2",
          "junior": "#2e7d32", "insight": "#3949ab", "possibile": "#666666"}


def oggetto(offerte):
    if len(offerte) == 1:
        o = offerte[0]
        return f"🎯 {o['azienda']}: {o['titolo']}"[:150]
    aziende = list(dict.fromkeys(o["azienda"] for o in offerte))
    elenco = ", ".join(aziende[:3]) + (f" e altre {len(aziende) - 3}" if len(aziende) > 3 else "")
    return f"🎯 {len(offerte)} nuove posizioni: {elenco}"[:150]


def testo(offerte):
    righe = ["Nuove posizioni appena uscite:\n"]
    for o in offerte:
        tipi = ", ".join(CATEGORIE.get(c, c) for c in o["categorie"])
        righe.append(f"• {o['azienda']} — {o['titolo']}\n  {tipi} · {o['luogo']}\n  Candidati: {o['url']}\n")
    righe.append("— Radar Carriere")
    return "\n".join(righe)


def pagina(offerte):
    e = html.escape
    blocchi = []
    for o in offerte:
        etichette = "".join(
            f'<span style="display:inline-block;border:1px solid {COLORI.get(c, "#666")};color:{COLORI.get(c, "#666")};'
            f'font-size:11px;padding:0 6px;margin-right:4px;border-radius:3px">{e(CATEGORIE.get(c, c))}</span>'
            for c in o["categorie"])
        blocchi.append(
            f'<tr><td style="padding:14px 0;border-bottom:1px solid #eee">'
            f'<div style="color:#b07800;font-weight:bold;font-size:13px">{e(o["azienda"])}</div>'
            f'<div style="font-size:16px;font-weight:bold;margin:2px 0 6px;color:#111">{e(o["titolo"])}</div>'
            f'<div style="margin-bottom:6px">{etichette}</div>'
            f'<div style="color:#555;font-size:13px;margin-bottom:10px">📍 {e(o["luogo"] or "luogo non indicato")}</div>'
            f'<a href="{e(o["url"], quote=True)}" style="background:#ffb000;color:#000;text-decoration:none;'
            f'font-weight:bold;padding:7px 14px;border-radius:3px;font-size:13px">CANDIDATI ↗</a></td></tr>')
    return (f'<div style="font-family:Arial,Helvetica,sans-serif;max-width:620px">'
            f'<div style="background:#000;color:#ffb000;padding:10px 14px;font-weight:bold;letter-spacing:2px">'
            f'RADAR CARRIERE</div><table style="width:100%;border-collapse:collapse">{"".join(blocchi)}</table>'
            f'<p style="color:#999;font-size:11px">Ricevi questa email perché hai attivato Radar Carriere.</p></div>')


def invia_email(cfg, offerte):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = oggetto(offerte)
    msg["From"] = formataddr(("Radar Carriere", cfg["utente"]))
    msg["To"] = cfg.get("destinatario") or cfg["utente"]
    msg.attach(MIMEText(testo(offerte), "plain", "utf-8"))
    msg.attach(MIMEText(pagina(offerte), "html", "utf-8"))
    porta = int(cfg.get("porta") or 465)
    if porta == 465:
        server = smtplib.SMTP_SSL(cfg.get("smtp") or "smtp.gmail.com", porta, timeout=30)
    else:
        server = smtplib.SMTP(cfg.get("smtp") or "smtp.gmail.com", porta, timeout=30)
        server.starttls()
    with server:
        server.login(cfg["utente"], cfg["password"])
        server.send_message(msg)
