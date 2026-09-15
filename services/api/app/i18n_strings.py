"""Backend-side i18n for email/notification strings (en + hi).

Mirrors the API i18n key namespaces in docs/api-contract.md; kept minimal and
data-only. The frontend owns the full dictionary (apps/web/lib/i18n/locales).
"""
from __future__ import annotations

STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "alerts.irrigation_needed": "Irrigation needed in {field}",
        "alerts.irrigation_review": "Review irrigation for {field} tomorrow",
        "alerts.rain_incoming": "Rain expected (~{mm} mm). Check planned irrigation in {field}",
        "alerts.extreme_heat": "Extreme heat forecast for {field}. Watch your crop.",
        "alerts.sensor_offline": "Soil sensor for {field} has stopped reporting",
        "alerts.low_confidence": "Recommendation confidence is low for {field} (data missing/stale)",
        "alerts.weather_unavailable": "Weather data unavailable for {field}",
        "email.body_note": "Open AgriFlow for the full explanation. "
                           "This is decision support, not guaranteed agricultural advice.",
    },
    "hi": {
        "alerts.irrigation_needed": "{field} में सिंचाई की जरूरत है",
        "alerts.irrigation_review": "कल {field} की सिंचाई जांचें",
        "alerts.rain_incoming": "बारिश की संभावना (~{mm} मिमी)। {field} की सिंचाई की योजना देखें",
        "alerts.extreme_heat": "{field} के लिए अत्यधिक गर्मी का पूर्वानुमान। फसल पर नजर रखें।",
        "alerts.sensor_offline": "{field} का मृदा सेंसर बंद हो गया है",
        "alerts.low_confidence": "{field} के लिए सिफारिश का भरोसा कम है (डेटा गायब/पुराना)",
        "alerts.weather_unavailable": "{field} के लिए मौसम डेटा उपलब्ध नहीं",
        "email.body_note": "पूरा कारण AgriFlow में देखें। यह सहायता है, कृषि सलाह की गारंटी नहीं।",
    },
}


def translate(key: str, language: str = "en") -> str:
    lang = language if language in STRINGS else "en"
    return STRINGS[lang].get(key) or STRINGS["en"].get(key) or key
