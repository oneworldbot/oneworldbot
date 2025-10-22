from deep_translator import GoogleTranslator
import os

# Basic wrapper: English is primary; other languages via GoogleTranslator (can be replaced by local catalogs later)

SUPPORTED = ['en', 'ar', 'es', 'fr', 'ru', 'zh']


def translate(text: str, target_lang: str) -> str:
    if not target_lang:
        return text
    lang = target_lang[:2]
    if lang == 'en' or lang not in SUPPORTED:
        return text
    try:
        return GoogleTranslator(source='auto', target=lang).translate(text)
    except Exception:
        return text
