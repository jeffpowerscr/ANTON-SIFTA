"""Small surf forecast helper for Alice.

Uses public marine/weather forecast endpoints. It deliberately does not scrape
Surfline or use private account credentials.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Iterable
from zoneinfo import ZoneInfo


_TZ = ZoneInfo("America/Costa_Rica")


@dataclass(frozen=True)
class SurfSpot:
    name: str
    latitude: float
    longitude: float
    note: str = ""


SPOTS: dict[str, SurfSpot] = {
    "jaco": SurfSpot("Jaco, Costa Rica", 9.614, -84.629, "Beachbreak; local tide/banks matter."),
    "playa jaco": SurfSpot("Jaco, Costa Rica", 9.614, -84.629, "Beachbreak; local tide/banks matter."),
    "hermosa": SurfSpot("Playa Hermosa, Costa Rica", 9.575, -84.607, "More exposed and powerful than Jaco."),
    "playa hermosa": SurfSpot("Playa Hermosa, Costa Rica", 9.575, -84.607, "More exposed and powerful than Jaco."),
}


def resolve_spot(name: str) -> SurfSpot:
    key = " ".join((name or "").lower().replace(",", " ").split())
    if key in SPOTS:
        return SPOTS[key]
    if "jaco" in key:
        return SPOTS["jaco"]
    if "hermosa" in key:
        return SPOTS["hermosa"]
    raise ValueError(f"unknown surf spot {name!r}; known spots: {', '.join(sorted(SPOTS))}")


def resolve_date(day: str | None = None, date: str | None = None, *, now: dt.datetime | None = None) -> dt.date:
    if date:
        return dt.date.fromisoformat(date)

    base = (now or dt.datetime.now(_TZ)).date()
    if not day or day.lower() in {"today", "now"}:
        return base
    normalized = day.strip().lower()
    if normalized == "tomorrow":
        return base + dt.timedelta(days=1)

    weekdays = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6,
    }
    if normalized not in weekdays:
        raise ValueError(f"unknown day {day!r}; use today, tomorrow, weekday, or YYYY-MM-DD")
    delta = (weekdays[normalized] - base.weekday()) % 7
    if delta == 0:
        delta = 7
    return base + dt.timedelta(days=delta)


def _fetch_json(url: str, *, timeout_s: float = 20.0) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": "SIFTA-Alice/1.0"})
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _url(base: str, params: dict[str, Any]) -> str:
    return base + "?" + urllib.parse.urlencode(params, doseq=True)


def _closest_indices(times: Iterable[str], target: dt.date) -> list[int]:
    out: list[int] = []
    for i, raw in enumerate(times):
        if str(raw).startswith(target.isoformat()):
            out.append(i)
    return out


def _safe(values: list[Any], i: int) -> float | None:
    try:
        value = values[i]
    except Exception:
        return None
    if value is None:
        return None
    try:
        f = float(value)
    except Exception:
        return None
    if math.isnan(f):
        return None
    return f


def _max_at(values: list[Any], indices: list[int]) -> tuple[float | None, int | None]:
    best: tuple[float | None, int | None] = (None, None)
    for i in indices:
        v = _safe(values, i)
        if v is not None and (best[0] is None or v > best[0]):
            best = (v, i)
    return best


def _avg(values: list[Any], indices: list[int]) -> float | None:
    vals = [_safe(values, i) for i in indices]
    clean = [v for v in vals if v is not None]
    if not clean:
        return None
    return sum(clean) / len(clean)


def _mode(values: list[Any], indices: list[int]) -> float | None:
    counts: dict[int, int] = {}
    for i in indices:
        value = _safe(values, i)
        if value is None:
            continue
        key = int(round(value))
        counts[key] = counts.get(key, 0) + 1
    if not counts:
        return None
    return float(max(counts.items(), key=lambda item: (item[1], -item[0]))[0])


def _fmt_ft(meters: float | None) -> str:
    if meters is None:
        return "unknown"
    return f"{meters * 3.28084:.1f} ft"


def _fmt_num(value: float | None, suffix: str = "") -> str:
    if value is None:
        return "unknown"
    return f"{value:.1f}{suffix}"


def _wind_direction_label(deg: float | None) -> str:
    if deg is None:
        return "unknown"
    dirs = ("N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW")
    return dirs[int((deg + 11.25) // 22.5) % 16]


def _weather_label(code: float | None) -> str:
    labels = {
        0: "clear",
        1: "mainly clear",
        2: "partly cloudy",
        3: "overcast",
        45: "fog",
        48: "rime fog",
        51: "light drizzle",
        53: "drizzle",
        55: "heavy drizzle",
        61: "light rain",
        63: "rain",
        65: "heavy rain",
        80: "light showers",
        81: "showers",
        82: "heavy showers",
        95: "thunderstorms",
    }
    if code is None:
        return "unknown"
    return labels.get(int(code), f"weather code {int(code)}")


def _surf_rating(report: dict[str, Any]) -> str:
    wave = report.get("wave_height_ft")
    swell = report.get("swell_height_ft")
    period = report.get("swell_period_s") or report.get("wave_period_s")
    wind = report.get("wind_mph_avg")
    gust = report.get("wind_gust_mph_avg")

    score = 0
    if wave is not None:
        if 2.0 <= wave <= 5.0:
            score += 2
        elif 1.0 <= wave < 2.0 or 5.0 < wave <= 7.0:
            score += 1
    if swell is not None and swell >= 2.0:
        score += 1
    if period is not None:
        if period >= 12:
            score += 2
        elif period >= 9:
            score += 1
    if wind is not None:
        if wind <= 6:
            score += 2
        elif wind <= 12:
            score += 1
    if gust is not None and gust >= 18:
        score -= 1

    if period is not None and period < 12 and score >= 6:
        return "surfable but not great; the period is not especially powerful"
    if score >= 6:
        return "good window if local tide and banks cooperate"
    if score >= 4:
        return "surfable, but not guaranteed clean"
    if score >= 2:
        return "small/marginal; better for a longboard or just getting wet"
    return "probably weak or messy unless a local bank is working"


def _surf_read(report: dict[str, Any]) -> str:
    rating = _surf_rating(report)
    spot = str(report.get("spot") or "")
    wave = report.get("wave_height_ft")
    period = report.get("swell_period_s") or report.get("wave_period_s")
    wind = report.get("wind_mph_avg")
    wind_dir = report.get("wind_direction_label") or "unknown"

    board = "longboard/funboard"
    if wave is not None and wave >= 4:
        board = "shortboard or step-up if the banks are right"
    elif wave is not None and wave < 2.5:
        board = "longboard, foamie, or grovel board"

    timing = "Early morning is usually the cleaner bet before local wind gets on it."
    if wind is not None and wind <= 5:
        timing = "Wind looks light, so the better window may last longer than usual."
    if "Jaco" in spot and wind_dir in {"SW", "WSW", "W"}:
        timing += " For Jaco, SW/WSW/W wind is onshore-ish, so keep an eye on texture."

    return (
        f"{spot} looks {rating}. Bring a {board}. "
        f"The swell period is {_fmt_num(period, 's')} and wind is about "
        f"{_fmt_num(wind, ' mph')} from {wind_dir}. {timing}"
    )


def fetch_surf_report(spot: SurfSpot, target: dt.date) -> dict[str, Any]:
    common = {
        "latitude": spot.latitude,
        "longitude": spot.longitude,
        "timezone": "America/Costa_Rica",
        "forecast_days": 16,
    }
    marine_url = _url(
        "https://marine-api.open-meteo.com/v1/marine",
        {
            **common,
            "hourly": ",".join(
                [
                    "wave_height",
                    "wave_period",
                    "wave_direction",
                    "swell_wave_height",
                    "swell_wave_period",
                    "swell_wave_direction",
                    "wind_wave_height",
                    "wind_wave_period",
                    "sea_surface_temperature",
                ]
            ),
        },
    )
    weather_url = _url(
        "https://api.open-meteo.com/v1/forecast",
        {
            **common,
            "hourly": ",".join(
                [
                    "temperature_2m",
                    "apparent_temperature",
                    "precipitation_probability",
                    "weather_code",
                    "cloud_cover",
                    "wind_speed_10m",
                    "wind_direction_10m",
                    "wind_gusts_10m",
                ]
            ),
            "wind_speed_unit": "mph",
            "temperature_unit": "fahrenheit",
        },
    )
    marine = _fetch_json(marine_url)
    weather = _fetch_json(weather_url)
    mh = marine.get("hourly") or {}
    wh = weather.get("hourly") or {}
    indices = _closest_indices(mh.get("time") or [], target)
    wind_indices = _closest_indices(wh.get("time") or [], target)
    if not indices:
        raise RuntimeError(f"no marine forecast returned for {target.isoformat()}")

    wave_height, wave_i = _max_at(mh.get("wave_height") or [], indices)
    swell_height, swell_i = _max_at(mh.get("swell_wave_height") or [], indices)
    wind_speed = _avg(wh.get("wind_speed_10m") or [], wind_indices)
    gust = _avg(wh.get("wind_gusts_10m") or [], wind_indices)
    wind_dir = _avg(wh.get("wind_direction_10m") or [], wind_indices)
    temp_f = _max_at(wh.get("temperature_2m") or [], wind_indices)[0]
    apparent_f = _max_at(wh.get("apparent_temperature") or [], wind_indices)[0]
    rain_prob = _max_at(wh.get("precipitation_probability") or [], wind_indices)[0]
    cloud_cover = _avg(wh.get("cloud_cover") or [], wind_indices)
    weather_code = _mode(wh.get("weather_code") or [], wind_indices)
    sample_i = swell_i if swell_i is not None else wave_i if wave_i is not None else indices[0]

    report = {
        "spot": spot.name,
        "date": target.isoformat(),
        "source": "Open-Meteo Marine + Weather APIs",
        "wave_height_ft": None if wave_height is None else wave_height * 3.28084,
        "wave_period_s": _safe(mh.get("wave_period") or [], sample_i),
        "wave_direction_deg": _safe(mh.get("wave_direction") or [], sample_i),
        "swell_height_ft": None if swell_height is None else swell_height * 3.28084,
        "swell_period_s": _safe(mh.get("swell_wave_period") or [], sample_i),
        "swell_direction_deg": _safe(mh.get("swell_wave_direction") or [], sample_i),
        "wind_mph_avg": wind_speed,
        "wind_gust_mph_avg": gust,
        "wind_direction_deg_avg": wind_dir,
        "wind_direction_label": _wind_direction_label(wind_dir),
        "weather": _weather_label(weather_code),
        "temperature_f_high": temp_f,
        "apparent_temperature_f_high": apparent_f,
        "precipitation_probability_pct_max": rain_prob,
        "cloud_cover_pct_avg": cloud_cover,
        "water_temp_c": _avg(mh.get("sea_surface_temperature") or [], indices),
        "spot_note": spot.note,
        "tide_note": (
            "Tide timing is not included in this public Open-Meteo feed. "
            "Check Surfline Premium or a local tide chart for the exact tide window."
        ),
    }
    report["read"] = _surf_read(report)
    return report


def fetch_nearby_comparison(spot: SurfSpot, target: dt.date) -> dict[str, Any] | None:
    if "Jaco" not in spot.name:
        return None
    try:
        hermosa = fetch_surf_report(SPOTS["hermosa"], target)
    except Exception:
        return None
    return {
        "spot": hermosa["spot"],
        "wave_height_ft": hermosa.get("wave_height_ft"),
        "swell_height_ft": hermosa.get("swell_height_ft"),
        "swell_period_s": hermosa.get("swell_period_s"),
        "wind_mph_avg": hermosa.get("wind_mph_avg"),
        "read": hermosa.get("read"),
    }


def format_report(report: dict[str, Any]) -> str:
    comparison = report.get("nearby_comparison") or {}
    comparison_text = ""
    if comparison:
        comparison_text = (
            "\nNearby check:\n"
            f"- {comparison.get('spot')}: wave {_fmt_num(comparison.get('wave_height_ft'), ' ft')}, "
            f"swell {_fmt_num(comparison.get('swell_height_ft'), ' ft')} at "
            f"{_fmt_num(comparison.get('swell_period_s'), 's')}. "
            "Hermosa is usually more exposed than Jaco, so treat it as the bigger/heavier option.\n"
        )

    return (
        f"Surf report for {report['spot']} on {report['date']} "
        f"({report['source']}):\n"
        f"- Wave height: {_fmt_num(report.get('wave_height_ft'), ' ft')}\n"
        f"- Swell: {_fmt_num(report.get('swell_height_ft'), ' ft')} at "
        f"{_fmt_num(report.get('swell_period_s'), 's')}, from "
        f"{_fmt_num(report.get('swell_direction_deg'), ' deg')}\n"
        f"- Mean wave period/direction: {_fmt_num(report.get('wave_period_s'), 's')} / "
        f"{_fmt_num(report.get('wave_direction_deg'), ' deg')}\n"
        f"- Wind: {_fmt_num(report.get('wind_mph_avg'), ' mph')} avg, "
        f"gusts {_fmt_num(report.get('wind_gust_mph_avg'), ' mph')}, "
        f"from {report.get('wind_direction_label') or 'unknown'}\n"
        f"- Weather: {report.get('weather', 'unknown')}; "
        f"high {_fmt_num(report.get('temperature_f_high'), ' F')}, "
        f"feels like {_fmt_num(report.get('apparent_temperature_f_high'), ' F')}; "
        f"rain chance up to {_fmt_num(report.get('precipitation_probability_pct_max'), '%')}\n"
        f"- Water temp: {_fmt_num(report.get('water_temp_c'), ' C')}\n"
        f"- Tide: {report.get('tide_note')}\n"
        f"- Local note: {report.get('spot_note') or 'Check tide, banks, and local wind.'}\n"
        f"- My read: {report.get('read') or _surf_rating(report)}\n"
        f"{comparison_text}"
        "This is model guidance, not a Surfline Premium report."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch a public surf forecast for Alice.")
    parser.add_argument("--spot", default="jaco", help="Surf spot name, e.g. jaco or hermosa.")
    parser.add_argument("--day", default="today", help="today, tomorrow, weekday, or omit with --date.")
    parser.add_argument("--date", default="", help="Exact date YYYY-MM-DD.")
    parser.add_argument("--json", action="store_true", help="Print raw JSON summary.")
    args = parser.parse_args(argv)

    spot = resolve_spot(args.spot)
    target = resolve_date(args.day, args.date or None)
    report = fetch_surf_report(spot, target)
    comparison = fetch_nearby_comparison(spot, target)
    if comparison:
        report["nearby_comparison"] = comparison
    print(json.dumps(report, indent=2) if args.json else format_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
