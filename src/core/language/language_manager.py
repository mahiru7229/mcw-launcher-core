from __future__ import annotations

import json
import re
import string
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True, slots=True)
class LanguageInfo:
    locale: str
    name: str
    path: Path


class LanguageManager:
    DEFAULT_LOCALE = "en-US"

    def __init__(self, language_dir: Path | None = None) -> None:
        self._language_dirs = [language_dir] if language_dir is not None else self._default_language_dirs()
        self._locale = self.DEFAULT_LOCALE
        self._translations: dict[str, str] = {}
        self._default_translations: dict[str, str] = {}
        self._aliases: dict[str, str] = {}
        self._rendered_value_keys: dict[str, str] = {}
        self._rendered_templates: list[tuple[re.Pattern[str], str, tuple[str, ...]]] = []
        self._rendered_match_cache: dict[str, tuple[str, dict[str, str]] | None] = {}
        self._languages: dict[str, LanguageInfo] = {}
        self._listeners: list[Callable[[str], None]] = []
        self.reload()
        self.set_language(self.DEFAULT_LOCALE, notify=False)

    @property
    def current_locale(self) -> str:
        return self._locale

    @property
    def language_dir(self) -> Path:
        return self._language_dirs[-1]

    @property
    def language_dirs(self) -> tuple[Path, ...]:
        return tuple(self._language_dirs)

    def reload(self) -> list[LanguageInfo]:
        languages: dict[str, LanguageInfo] = {}
        for directory in self._language_dirs:
            if not directory.exists():
                continue
            for path in sorted(directory.glob("*.json")):
                try:
                    data = self._read_pack(path)
                    meta = data["meta"]
                    locale = str(meta.get("locale") or path.stem).strip()
                    name = str(meta.get("name") or locale).strip()
                    if locale and name:
                        languages[locale] = LanguageInfo(locale=locale, name=name, path=path)
                except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
                    continue

        self._languages = languages
        self._load_default_pack()
        self._build_rendered_text_index()
        return self.available_languages()

    def available_languages(self) -> list[LanguageInfo]:
        return sorted(self._languages.values(), key=lambda item: (item.name.casefold(), item.locale.casefold()))

    def set_language(self, locale: str, notify: bool = True) -> bool:
        requested = str(locale or self.DEFAULT_LOCALE).strip()
        info = self._languages.get(requested) or self._languages.get(self.DEFAULT_LOCALE)
        if info is None:
            self._locale = self.DEFAULT_LOCALE
            self._translations = {}
            return False

        try:
            data = self._read_pack(info.path)
            translations = self._normalize_string_map(data.get("translations", {}), "translations")
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return False

        changed = self._locale != info.locale or self._translations != translations
        self._locale = info.locale
        self._translations = translations
        if notify and changed:
            for listener in tuple(self._listeners):
                listener(self._locale)
        return True

    def resolve_key(self, key: str) -> str:
        source = str(key)
        return self._aliases.get(source, self._rendered_value_keys.get(source, source))

    def translate(self, key: str, default: str | None = None, **values: object) -> str:
        source = str(key)
        resolved = self.resolve_key(source)
        matched_values: dict[str, str] = {}
        text = self._translations.get(resolved)
        if text is None:
            text = self._default_translations.get(resolved)
        if text is None:
            rendered_match = self._resolve_rendered_template(source)
            if rendered_match is not None:
                resolved, matched_values = rendered_match
                text = self._translations.get(resolved) or self._default_translations.get(resolved)
        if text is None:
            text = default if default is not None else source
        format_values = {**matched_values, **values}
        try:
            return text.format(**format_values)
        except (KeyError, ValueError, IndexError):
            return text

    def has_key(self, key: str) -> bool:
        resolved = self.resolve_key(key)
        return resolved in self._default_translations or resolved in self._translations

    def missing_keys(self, locale: str | None = None) -> list[str]:
        translations = self._translations
        if locale is not None and locale != self._locale:
            info = self._languages.get(locale)
            if info is None:
                return sorted(self._default_translations)
            try:
                data = self._read_pack(info.path)
                translations = self._normalize_string_map(data.get("translations", {}), "translations")
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                return sorted(self._default_translations)
        return sorted(set(self._default_translations) - set(translations))

    def placeholder_mismatches(self, locale: str | None = None) -> dict[str, tuple[set[str], set[str]]]:
        translations = self._translations
        if locale is not None and locale != self._locale:
            info = self._languages.get(locale)
            if info is None:
                return {}
            try:
                data = self._read_pack(info.path)
                translations = self._normalize_string_map(data.get("translations", {}), "translations")
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                return {}

        mismatches: dict[str, tuple[set[str], set[str]]] = {}
        for key, default_text in self._default_translations.items():
            translated_text = translations.get(key)
            if translated_text is None:
                continue
            default_fields = self._format_fields(default_text)
            translated_fields = self._format_fields(translated_text)
            if default_fields != translated_fields:
                mismatches[key] = (default_fields, translated_fields)
        return mismatches


    def _build_rendered_text_index(self) -> None:
        """Index rendered language strings so live language changes can recover their keys.

        Widgets are sometimes constructed with ``tr("semantic.key")`` and only
        retain the rendered text.  Exact and placeholder-aware reverse indexes let
        the runtime translate that existing text again without requiring every GUI
        class to retain a separate key property.  Ambiguous values are excluded.
        """
        value_candidates: dict[str, set[str]] = {}
        template_candidates: dict[tuple[str, str], tuple[re.Pattern[str], str, tuple[str, ...]]] = {}
        for info in self._languages.values():
            try:
                data = self._read_pack(info.path)
                translations = self._normalize_string_map(data.get("translations", {}), "translations")
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                continue
            for key, rendered in translations.items():
                if not rendered:
                    continue
                value_candidates.setdefault(rendered, set()).add(key)
                compiled = self._compile_rendered_template(rendered)
                if compiled is not None:
                    pattern, fields = compiled
                    template_candidates[(pattern.pattern, key)] = (pattern, key, fields)

        self._rendered_value_keys = {value: next(iter(keys)) for value, keys in value_candidates.items() if len(keys) == 1}
        self._rendered_templates = sorted(template_candidates.values(), key=lambda item: len(item[0].pattern), reverse=True)
        self._rendered_match_cache.clear()

    def _resolve_rendered_template(self, source: str) -> tuple[str, dict[str, str]] | None:
        if source in self._rendered_match_cache:
            return self._rendered_match_cache[source]
        matches: list[tuple[str, dict[str, str]]] = []
        for pattern, key, fields in self._rendered_templates:
            match = pattern.fullmatch(source)
            if match is None:
                continue
            values = {field: str(match.group(f"field_{index}")) for index, field in enumerate(fields)}
            matches.append((key, values))
            if len(matches) > 1 and matches[-1][0] != matches[0][0]:
                self._rendered_match_cache[source] = None
                return None
        result = matches[0] if matches else None
        self._rendered_match_cache[source] = result
        return result

    @classmethod
    def _compile_rendered_template(cls, text: str) -> tuple[re.Pattern[str], tuple[str, ...]] | None:
        parsed = list(string.Formatter().parse(text))
        field_names = [field_name for _literal, field_name, _format_spec, _conversion in parsed if field_name]
        if not field_names:
            return None
        fields: list[str] = []
        pieces = ["^"]
        seen: dict[str, int] = {}
        for literal, field_name, _format_spec, _conversion in parsed:
            pieces.append(re.escape(literal))
            if not field_name:
                continue
            normalized = field_name.split(".", 1)[0].split("[", 1)[0]
            if normalized in seen:
                pieces.append(f"(?P=field_{seen[normalized]})")
                continue
            index = len(fields)
            seen[normalized] = index
            fields.append(normalized)
            pieces.append(f"(?P<field_{index}>.+?)")
        pieces.append("$")
        try:
            return re.compile("".join(pieces), re.DOTALL), tuple(fields)
        except re.error:
            return None

    def subscribe(self, listener: Callable[[str], None]) -> None:
        if listener not in self._listeners:
            self._listeners.append(listener)

    def unsubscribe(self, listener: Callable[[str], None]) -> None:
        if listener in self._listeners:
            self._listeners.remove(listener)

    def _load_default_pack(self) -> None:
        info = self._languages.get(self.DEFAULT_LOCALE)
        if info is None:
            self._default_translations = {}
            self._aliases = {}
            return

        try:
            data = self._read_pack(info.path)
            self._default_translations = self._normalize_string_map(data.get("translations", {}), "translations")
            self._aliases = self._normalize_string_map(data.get("aliases", {}), "aliases")
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            self._default_translations = {}
            self._aliases = {}

    @classmethod
    def _default_language_dirs(cls) -> list[Path]:
        if getattr(sys, "frozen", False):
            bundled_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
            external_root = Path(sys.executable).resolve().parent
            return [bundled_root / "lang", external_root / "lang"]
        return [Path(__file__).resolve().parents[3] / "lang"]

    @staticmethod
    def _normalize_string_map(value: object, field_name: str) -> dict[str, str]:
        if not isinstance(value, dict):
            raise ValueError(f"{field_name} must be an object")
        return {str(key): str(text) for key, text in value.items() if isinstance(text, str)}

    @staticmethod
    def _format_fields(text: str) -> set[str]:
        fields: set[str] = set()
        for _, field_name, _, _ in string.Formatter().parse(text):
            if field_name:
                fields.add(field_name.split(".", 1)[0].split("[", 1)[0])
        return fields

    @staticmethod
    def _read_pack(path: Path) -> dict:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("meta"), dict):
            raise ValueError("Invalid language pack")
        return data


language_manager = LanguageManager()


def tr(key: str, default: str | None = None, **values: object) -> str:
    return language_manager.translate(key, default, **values)
