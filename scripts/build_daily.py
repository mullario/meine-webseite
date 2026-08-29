#!/usr/bin/env python3
"""Baut index.html mit Wetter- und Nachrichten-Briefing neu. Nur Python-Standardbibliothek."""

import html
import json
import os
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")
LAT, LON = 49.44806, 8.23861  # Gönnheim, Landkreis Bad Dürkheim
UA = "Mozilla/5.0 (compatible; meine-webseite-bot/1.0; +https://github.com/mullario/meine-webseite)"
ITEMS_PER_FEED = 5

WEATHER_CODES = {
    0: ("Klarer Himmel", "☀️"),
    1: ("Überwiegend klar", "🌤️"),
    2: ("Teilweise bewölkt", "⛅"),
    3: ("Bedeckt", "☁️"),
    45: ("Nebel", "🌫️"),
    48: ("Reifnebel", "🌫️"),
    51: ("Leichter Nieselregen", "🌦️"),
    53: ("Nieselregen", "🌦️"),
    55: ("Starker Nieselregen", "🌧️"),
    56: ("Leichter gefrierender Nieselregen", "🌧️"),
    57: ("Starker gefrierender Nieselregen", "🌧️"),
    61: ("Leichter Regen", "🌧️"),
    63: ("Regen", "🌧️"),
    65: ("Starker Regen", "🌧️"),
    66: ("Leichter gefrierender Regen", "🌧️"),
    67: ("Starker gefrierender Regen", "🌧️"),
    71: ("Leichter Schneefall", "🌨️"),
    73: ("Schneefall", "🌨️"),
    75: ("Starker Schneefall", "❄️"),
    77: ("Schneegriesel", "🌨️"),
    80: ("Leichte Regenschauer", "🌦️"),
    81: ("Regenschauer", "🌧️"),
    82: ("Heftige Regenschauer", "⛈️"),
    85: ("Leichte Schneeschauer", "🌨️"),
    86: ("Starke Schneeschauer", "❄️"),
    95: ("Gewitter", "⛈️"),
    96: ("Gewitter mit leichtem Hagel", "⛈️"),
    99: ("Gewitter mit starkem Hagel", "⛈️"),
}

NEWS_SOURCES = [
    ("Deutschland", "https://www.tagesschau.de/xml/rss2/"),
    ("Region Bad Dürkheim", "https://news.google.com/rss/search?q=Bad+D%C3%BCrkheim&hl=de&gl=DE&ceid=DE:de"),
    ("Welt", "https://www.tagesschau.de/ausland/index~rss2.xml"),
    ("Wirtschaft", "https://www.tagesschau.de/wirtschaft/index~rss2.xml"),
    ("BVB", "https://news.google.com/rss/search?q=Borussia+Dortmund&hl=de&gl=DE&ceid=DE:de"),
    ("MotoGP", "https://news.google.com/rss/search?q=MotoGP&hl=de&gl=DE&ceid=DE:de"),
    ("Künstliche Intelligenz", "https://rss.golem.de/rss.php?feed=RSS2.0&ms=ki"),
]


def fetch(url: str, _redirects: int = 0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code in (301, 302, 303, 307, 308) and _redirects < 5:
            location = exc.headers.get("Location")
            if location:
                if location.startswith("/"):
                    location = re.match(r"https?://[^/]+", url).group(0) + location
                return fetch(location, _redirects + 1)
        raise


def get_weather():
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={LAT}&longitude={LON}"
        "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,wind_speed_10m_max"
        "&timezone=Europe%2FBerlin&forecast_days=1"
    )
    data = json.loads(fetch(url))
    daily = data["daily"]
    code = daily["weather_code"][0]
    desc, emoji = WEATHER_CODES.get(code, ("Unbekannt", "🌡️"))
    return {
        "desc": desc,
        "emoji": emoji,
        "tmax": round(daily["temperature_2m_max"][0]),
        "tmin": round(daily["temperature_2m_min"][0]),
        "precip": daily["precipitation_probability_max"][0],
        "wind": round(daily["wind_speed_10m_max"][0]),
    }


def strip_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def get_headlines(url: str, limit: int = ITEMS_PER_FEED):
    try:
        raw = fetch(url)
        root = ET.fromstring(raw)
    except Exception as exc:  # Feed-Ausfall soll den Build nicht stoppen
        return [{"title": f"(Quelle nicht erreichbar: {exc})", "link": "#", "source": ""}]

    items = []
    for item in root.findall("./channel/item")[:limit]:
        title = strip_tags(item.findtext("title") or "")
        link = (item.findtext("link") or "#").strip()
        source_el = item.find("source")
        source = source_el.text.strip() if source_el is not None and source_el.text else ""
        if source and title.endswith(f" - {source}"):
            title = title[: -len(f" - {source}")]
        elif not source and "news.google.com" in link and " - " in title:
            title, _, source = title.rpartition(" - ")
        items.append({"title": html.escape(title), "link": html.escape(link), "source": html.escape(source)})
    return items


def render_news_card(name: str, headlines) -> str:
    rows = "\n".join(
        f'          <li><a href="{h["link"]}" target="_blank" rel="noopener">{h["title"]}</a>'
        + (f' <span class="src">{h["source"]}</span>' if h["source"] else "")
        + "</li>"
        for h in headlines
    )
    return f"""      <div class="card news-card">
        <h2>{html.escape(name)}</h2>
        <ul>
{rows}
        </ul>
      </div>"""


def render_page(weather, news_cards_html: str, now: datetime) -> str:
    weekday = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"][now.weekday()]
    date_str = f"{weekday}, {now.strftime('%d.%m.%Y')}"
    time_str = now.strftime("%H:%M")
    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Morgen-Briefing</title>
<style>
  :root {{
    color-scheme: light dark;
    --bg: #f7f7f8;
    --fg: #1a1a1a;
    --muted: #6b6b70;
    --accent: #4f46e5;
    --card-bg: #ffffff;
    --border: #e5e5e7;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #0f0f10;
      --fg: #f2f2f3;
      --muted: #9a9a9e;
      --accent: #818cf8;
      --card-bg: #1a1a1c;
      --border: #2a2a2d;
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    background: var(--bg);
    color: var(--fg);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    padding: 24px;
  }}
  .wrap {{ max-width: 1000px; margin: 0 auto; }}
  header {{
    display: flex;
    align-items: center;
    gap: 16px;
    margin-bottom: 24px;
  }}
  header img {{
    width: 56px;
    height: 56px;
    object-fit: cover;
    border-radius: 50%;
    border: 2px solid var(--border);
  }}
  header h1 {{ margin: 0; font-size: 1.6rem; }}
  header p {{ margin: 2px 0 0; color: var(--muted); font-size: 0.9rem; }}
  .grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: 16px;
  }}
  .card {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 20px 24px;
  }}
  .card h2 {{
    margin: 0 0 12px;
    font-size: 1.05rem;
    color: var(--accent);
  }}
  .weather-card {{ grid-column: 1 / -1; display: flex; align-items: center; gap: 24px; flex-wrap: wrap; }}
  .weather-emoji {{ font-size: 3rem; line-height: 1; }}
  .weather-main {{ font-size: 1.4rem; font-weight: 600; }}
  .weather-details {{ color: var(--muted); font-size: 0.95rem; }}
  ul {{ margin: 0; padding: 0; list-style: none; }}
  li {{ margin-bottom: 10px; line-height: 1.4; font-size: 0.92rem; }}
  li a {{ color: var(--fg); text-decoration: none; }}
  li a:hover {{ text-decoration: underline; }}
  .src {{ color: var(--muted); font-size: 0.8rem; }}
  footer {{
    margin-top: 32px;
    text-align: center;
    color: var(--muted);
    font-size: 0.8rem;
  }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <img src="hund.jpeg" alt="">
    <div>
      <h1>Morgen-Briefing</h1>
      <p>{date_str} · aktualisiert {time_str} Uhr</p>
    </div>
  </header>
  <div class="grid">
    <div class="card weather-card">
      <div class="weather-emoji">{weather['emoji']}</div>
      <div>
        <div class="weather-main">{weather['desc']}, {weather['tmin']}° – {weather['tmax']}° in Gönnheim</div>
        <div class="weather-details">Regenwahrscheinlichkeit {weather['precip']}% · Wind bis {weather['wind']} km/h</div>
      </div>
    </div>
{news_cards_html}
  </div>
  <footer>Automatisch generiert jeden Morgen um 6 Uhr &middot; <a href="https://github.com/mullario/meine-webseite">Quellcode</a></footer>
</div>
</body>
</html>
"""


def main():
    now = datetime.now(BERLIN)
    force = os.environ.get("FORCE_RUN", "").lower() == "true"
    if not force and now.hour != 6:
        print(f"Übersprungen: {now.isoformat()} ist nicht 6 Uhr Berliner Zeit.")
        sys.exit(0)
    weather = get_weather()
    cards = []
    for name, url in NEWS_SOURCES:
        headlines = get_headlines(url)
        cards.append(render_news_card(name, headlines))
    page = render_page(weather, "\n".join(cards), now)
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(page)
    print(f"index.html geschrieben ({now.isoformat()})")


if __name__ == "__main__":
    main()
