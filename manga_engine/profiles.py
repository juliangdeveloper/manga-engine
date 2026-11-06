PROFILES = {
    "x4": {
        "name": "Xteink X4 Pro",
        "size": (480, 800),
        "max": (2048, 1536),
        "quality": 85,
    },
    "kindle": {
        "name": "Kindle Paperwhite (11.ª gen.)",
        "size": (1236, 1648),
        "max": (1236, 1648),
        "quality": 90,
    },
    "kobo": {
        "name": "Kobo Clara BW / Clara 2E",
        "size": (1072, 1448),
        "max": (1072, 1448),
        "quality": 90,
    },
}

DEFAULT_PROFILE = "x4"


def fits(size, limit):
    w, h = size
    a, b = limit
    return (w <= a and h <= b) or (w <= b and h <= a)
