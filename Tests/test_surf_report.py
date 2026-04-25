import datetime as dt

from System import surf_report


def test_resolve_jaco_alias():
    spot = surf_report.resolve_spot("Jaco, Costa Rica")
    assert spot.name == "Jaco, Costa Rica"
    assert spot.latitude > 9
    assert spot.longitude < -84


def test_resolve_next_weekday():
    now = dt.datetime(2026, 4, 25, 10, 0, tzinfo=surf_report._TZ)
    assert surf_report.resolve_date("thursday", now=now).isoformat() == "2026-04-30"


def test_format_report_mentions_not_surfline():
    text = surf_report.format_report(
        {
            "spot": "Jaco, Costa Rica",
            "date": "2026-04-30",
            "source": "test",
            "wave_height_ft": 4.2,
            "swell_height_ft": 3.5,
            "swell_period_s": 12.0,
            "swell_direction_deg": 210.0,
            "wave_period_s": 11.0,
            "wave_direction_deg": 205.0,
            "wind_mph_avg": 6.0,
            "wind_gust_mph_avg": 11.0,
            "wind_direction_label": "SW",
            "weather": "partly cloudy",
            "temperature_f_high": 88.0,
            "apparent_temperature_f_high": 95.0,
            "precipitation_probability_pct_max": 40.0,
            "water_temp_c": 28.0,
            "tide_note": "Check Surfline Premium or a local tide chart.",
            "spot_note": "Beachbreak.",
            "read": "Surfable but not great.",
            "nearby_comparison": {
                "spot": "Playa Hermosa, Costa Rica",
                "wave_height_ft": 5.0,
                "swell_height_ft": 4.0,
                "swell_period_s": 12.0,
            },
        }
    )
    assert "Jaco" in text
    assert "4.2 ft" in text
    assert "My read" in text
    assert "Tide" in text
    assert "Playa Hermosa" in text
    assert "not a Surfline Premium report" in text


def test_surf_read_gives_practical_recommendation():
    report = {
        "spot": "Jaco, Costa Rica",
        "wave_height_ft": 2.2,
        "swell_height_ft": 2.0,
        "swell_period_s": 9.0,
        "wind_mph_avg": 4.0,
        "wind_gust_mph_avg": 8.0,
        "wind_direction_label": "SW",
    }
    read = surf_report._surf_read(report)
    assert "longboard" in read.lower() or "foamie" in read.lower()
    assert "Wind looks light" in read
