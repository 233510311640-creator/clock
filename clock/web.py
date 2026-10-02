"""Web access for Clock: search results, weather, and reading a page. No API keys needed."""
import html
import ipaddress
import json
import re
import socket
import urllib.parse
import urllib.request

from . import config as C

_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}

_WEATHER_CODES = {
    0: "clear sky", 1: "mostly clear", 2: "partly cloudy", 3: "overcast", 45: "foggy", 48: "foggy",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle", 61: "light rain", 63: "rain", 65: "heavy rain",
    71: "light snow", 73: "snow", 75: "heavy snow", 80: "rain showers", 81: "rain showers",
    82: "violent rain showers", 95: "a thunderstorm", 96: "a thunderstorm with hail", 99: "a thunderstorm with hail",
}


def _get(url: str, limit: int = 500_000) -> str:
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=C.WEB_TIMEOUT) as r:
        return r.read(limit).decode(r.headers.get_content_charset() or "utf-8", "replace")


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", fragment))).strip()


def search(query: str, n: int = 4) -> str:
    """Top web results as 'title - snippet (url)' lines the model can summarise."""
    page = _get("https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query))
    titles = re.findall(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', page, re.S)
    snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', page, re.S)
    out = []
    for i, (href, title) in enumerate(titles[:n]):
        real = urllib.parse.parse_qs(urllib.parse.urlparse(href).query).get("uddg", [href])[0]
        snip = _text(snippets[i]) if i < len(snippets) else ""
        out.append(f"{_text(title)} - {snip} ({real})")
    return "\n".join(out) or "No results."


def weather(city: str = "") -> str:
    city = city or C.CITY
    geo = json.loads(_get("https://geocoding-api.open-meteo.com/v1/search?count=1&name=" + urllib.parse.quote(city)))
    if not geo.get("results"):
        return f"Couldn't find a place called {city}."
    g = geo["results"][0]
    w = json.loads(_get(
        "https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s&timezone=auto&forecast_days=1"
        "&current=temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,weather_code"
        "&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max" % (g["latitude"], g["longitude"])))
    c, d = w["current"], w["daily"]
    return (f"{g['name']}, {g.get('country', '')}: {c['temperature_2m']:.0f}°C (feels {c['apparent_temperature']:.0f}), "
            f"{_WEATHER_CODES.get(c['weather_code'], 'unsettled')}, humidity {c['relative_humidity_2m']}%, "
            f"wind {c['wind_speed_10m']:.0f} km/h. Today: high {d['temperature_2m_max'][0]:.0f}, "
            f"low {d['temperature_2m_min'][0]:.0f}, rain chance {d['precipitation_probability_max'][0]}%.")


def _public_host(host: str) -> bool:
    """False for anything resolving to a local/private address, so a page can't point Clock at local services."""
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    return all(ipaddress.ip_address(i[4][0]).is_global for i in infos)


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _public_host(urllib.parse.urlparse(newurl).hostname or ""):
            raise urllib.error.URLError("redirect to a non-public address blocked")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def read_page(url: str, max_chars: int = 3000) -> str:
    u = urllib.parse.urlparse(url)
    if u.scheme not in ("http", "https") or not _public_host(u.hostname or ""):
        return "That address isn't allowed."
    opener = urllib.request.build_opener(_SafeRedirect)
    with opener.open(urllib.request.Request(url, headers=_UA), timeout=C.WEB_TIMEOUT) as r:
        raw = r.read(1_000_000).decode(r.headers.get_content_charset() or "utf-8", "replace")
    raw = re.sub(r"(?is)<(script|style|noscript|svg|head)\b.*?</\1>", " ", raw)
    return _text(raw)[:max_chars] or "The page had no readable text."
