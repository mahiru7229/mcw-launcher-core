from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import parse_qs, urljoin, urlparse
import re

from src.models.optifine.optifine_models import OptiFineVersion


_MINECRAFT_RE = re.compile(r"Minecraft\s+([0-9][0-9A-Za-z._-]*)", re.IGNORECASE)
_FILENAME_RE = re.compile(r"OptiFine_([^\s\"'<>]+?)\.jar", re.IGNORECASE)
_VERSION_TEXT_RE = re.compile(r"OptiFine\s+(HD_[A-Z0-9]+)\s+([A-Z0-9][A-Z0-9._-]*)", re.IGNORECASE)
_DATE_RE = re.compile(r"\b((?:20\d{2}-\d{2}-\d{2})|(?:\d{2}\.\d{2}\.20\d{2}))\b")
_FORGE_RE = re.compile(r"(?:Forge|F)\s*[: ]?\s*#?\s*([0-9][0-9A-Za-z.+_-]*|N/A)", re.IGNORECASE)


class _DownloadsHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.current_minecraft = ""
        self.preview_context = False
        self._heading_tag = ""
        self._heading_text: list[str] = []
        self._row_depth = 0
        self._row_text: list[str] = []
        self._row_links: list[tuple[str, str]] = []
        self._anchor_href = ""
        self._anchor_text: list[str] = []
        self.rows: list[tuple[str, bool, str, tuple[tuple[str, str], ...]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.casefold()
        attrs_dict = {str(key).casefold(): str(value or "") for key, value in attrs}
        if lowered in {"h1", "h2", "h3", "h4", "strong"}:
            self._heading_tag = lowered
            self._heading_text = []
        if lowered in {"td", "th", "br"} and self._row_depth:
            self._row_text.append(" ")
        if lowered == "tr":
            self._row_depth += 1
            if self._row_depth == 1:
                self._row_text = []
                self._row_links = []
        if lowered == "a":
            self._anchor_href = attrs_dict.get("href", "")
            self._anchor_text = []

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.casefold()
        if lowered == self._heading_tag:
            text = " ".join("".join(self._heading_text).split())
            match = _MINECRAFT_RE.search(text)
            if match:
                self.current_minecraft = match.group(1)
                self.preview_context = "preview" in text.casefold()
            elif "preview" in text.casefold():
                self.preview_context = True
            elif text:
                self.preview_context = False
            self._heading_tag = ""
            self._heading_text = []
        if lowered == "a" and self._anchor_href:
            text = " ".join("".join(self._anchor_text).split())
            if self._row_depth:
                self._row_links.append((self._anchor_href, text))
            self._anchor_href = ""
            self._anchor_text = []
        if lowered in {"td", "th"} and self._row_depth:
            self._row_text.append(" ")
        if lowered == "tr" and self._row_depth:
            self._row_depth -= 1
            if self._row_depth == 0:
                text = " ".join("".join(self._row_text).split())
                if text or self._row_links:
                    self.rows.append((self.current_minecraft, self.preview_context, text, tuple(self._row_links)))
                self._row_text = []
                self._row_links = []

    def handle_data(self, data: str) -> None:
        if self._heading_tag:
            self._heading_text.append(data)
        if self._row_depth:
            self._row_text.append(data)
        if self._anchor_href:
            self._anchor_text.append(data)


class OptiFineMetadataParser:
    BASE_URL = "https://optifine.net/"

    @classmethod
    def parse(cls, html: str) -> list[OptiFineVersion]:
        parser = _DownloadsHTMLParser()
        parser.feed(str(html or ""))
        output: list[OptiFineVersion] = []
        seen: set[tuple[str, str]] = set()
        for minecraft_version, preview_context, text, links in parser.rows:
            filename = cls._filename(links, text)
            version_match = _VERSION_TEXT_RE.search(text.replace("OptiFine_", "OptiFine ").replace("_", "_"))
            if not filename and version_match is None:
                continue
            parsed = cls._filename_parts(filename) if filename else None
            if parsed is not None:
                file_minecraft, edition, build = parsed
                minecraft = minecraft_version or file_minecraft
            elif version_match is not None:
                minecraft = minecraft_version
                edition, build = version_match.group(1), version_match.group(2)
                filename = f"OptiFine_{minecraft}_{edition}_{build}.jar" if minecraft else f"OptiFine_{edition}_{build}.jar"
            else:
                continue
            if not minecraft:
                minecraft = cls._minecraft_from_text(text)
            if not minecraft:
                continue
            key = (minecraft.casefold(), filename.casefold())
            if key in seen:
                continue
            seen.add(key)
            hrefs = [(urljoin(cls.BASE_URL, href), label) for href, label in links]
            mirror = next((href for href, label in hrefs if "mirror" in label.casefold() or "adloadx" in href.casefold()), "")
            changelog = next((href for href, label in hrefs if "change" in label.casefold() or href.casefold().endswith(".txt")), "")
            download_page = next((href for href, label in hrefs if "download" in label.casefold() or "adload" in href.casefold()), cls.BASE_URL + "downloads")
            forge_match = _FORGE_RE.search(text)
            date_match = _DATE_RE.search(text)
            output.append(
                OptiFineVersion(
                    minecraft_version=minecraft,
                    edition=edition.upper(),
                    build=build,
                    filename=filename,
                    preview=bool("preview" in text.casefold() or re.search(r"(?:^|[_\s])pre\d+", build, re.IGNORECASE)),
                    forge_version=forge_match.group(1) if forge_match else "",
                    release_date=date_match.group(1) if date_match else "",
                    download_page_url=download_page,
                    mirror_url=mirror,
                    changelog_url=changelog,
                )
            )
        output.sort(key=lambda item: (cls._version_key(item.minecraft_version), item.preview, item.release_date, item.version_id), reverse=True)
        return output

    @staticmethod
    def _filename(links: tuple[tuple[str, str], ...], text: str) -> str:
        for href, _label in links:
            query = parse_qs(urlparse(href).query)
            candidate = str((query.get("f") or [""])[0])
            match = _FILENAME_RE.search(candidate)
            if match:
                return match.group(0)
            match = _FILENAME_RE.search(href)
            if match:
                return match.group(0)
        match = _FILENAME_RE.search(text)
        return match.group(0) if match else ""

    @staticmethod
    def _filename_parts(filename: str) -> tuple[str, str, str] | None:
        normalized = str(filename or "")
        if not normalized.casefold().startswith("optifine_") or not normalized.casefold().endswith(".jar"):
            return None
        body = normalized[len("OptiFine_") : -4]
        match = re.match(r"(?P<mc>[0-9][0-9A-Za-z.-]*)_(?P<edition>HD_[A-Z0-9]+)_(?P<build>.+)$", body, re.IGNORECASE)
        if not match:
            return None
        return match.group("mc"), match.group("edition"), match.group("build")

    @staticmethod
    def _minecraft_from_text(text: str) -> str:
        match = _MINECRAFT_RE.search(text)
        return match.group(1) if match else ""

    @staticmethod
    def _version_key(value: str) -> tuple:
        parts = re.split(r"([0-9]+)", str(value))
        return tuple(int(part) if part.isdigit() else part.casefold() for part in parts if part)
