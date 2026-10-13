from __future__ import annotations

import re
from urllib.parse import quote_plus, urlparse, urlunparse

_ALLOWED_HOSTS = {"curseforge.com", "www.curseforge.com", "legacy.curseforge.com"}
_PROJECT_CATEGORIES = {"mc-mods", "modpacks", "texture-packs", "shaders", "worlds", "data-packs"}
_PROJECT_SLUG_CACHE: dict[int, str] = {}


def normalize_project_page(url: object) -> str:
    raw = str(url or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlparse(raw)
    except ValueError:
        return ""
    host = str(parsed.hostname or "").casefold()
    if parsed.scheme.casefold() != "https" or host not in _ALLOWED_HOSTS or parsed.username or parsed.password:
        return ""
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 3 or parts[0].casefold() != "minecraft" or parts[1].casefold() not in _PROJECT_CATEGORIES:
        return ""
    project_parts = parts[:3]
    if not project_parts[2]:
        return ""
    return urlunparse(("https", "www.curseforge.com", "/" + "/".join(project_parts), "", "", ""))


def is_numeric_project_placeholder(url: object, project_id: int | str) -> bool:
    normalized = normalize_project_page(url)
    if not normalized:
        return False
    last = normalized.rstrip("/").rsplit("/", 1)[-1]
    return last == str(project_id).strip() or last.isdigit()


def _resolve_from_client(project_id: int) -> str:
    try:
        from mcw_core.api.curseforge.curseforge_client import CurseForgeClient
        proj = CurseForgeClient.get_project(project_id)
        candidate = normalize_project_page(getattr(proj, "project_url", ""))
        if candidate and not is_numeric_project_placeholder(candidate, project_id):
            return candidate
    except Exception:
        pass
    return ""


def _resolve_from_cflookup(project_id: int) -> str:
    try:
        from src.core.network.httpx_downloader import HttpDownloader
        client = HttpDownloader.get_client()
        resp = client.get(f"https://cflookup.com/{project_id}", timeout=5.0, follow_redirects=True)
        if resp.status_code == 200:
            match = re.search(
                r'<meta\s+property=["\']og:url["\']\s+content=["\'](https://(?:www\.)?curseforge\.com/minecraft/[^"\']+)["\']',
                resp.text,
                re.IGNORECASE,
            )
            candidate = match.group(1) if match else ""
            if not candidate:
                pattern = re.compile(
                    r'https://(?:www\.)?curseforge\.com/minecraft/(?:' + "|".join(_PROJECT_CATEGORIES) + r')/[a-zA-Z0-9_\-]+',
                    re.IGNORECASE,
                )
                match2 = pattern.search(resp.text)
                if match2:
                    candidate = match2.group(0)
            if candidate:
                norm = normalize_project_page(candidate)
                if norm and not is_numeric_project_placeholder(norm, project_id):
                    return norm
    except Exception:
        pass
    return ""


def resolve_curseforge_project_slug(project_id: int | str) -> str:
    pid = int(project_id or 0) if str(project_id).strip().isdigit() else 0
    if pid <= 0:
        return ""
    if pid in _PROJECT_SLUG_CACHE:
        return _PROJECT_SLUG_CACHE[pid]

    resolved = _resolve_from_client(pid)
    if not resolved:
        resolved = _resolve_from_cflookup(pid)

    if resolved:
        _PROJECT_SLUG_CACHE[pid] = resolved
    return resolved


def project_search_url(project_id: int | str) -> str:
    identifier = str(project_id).strip()
    return f"https://www.curseforge.com/minecraft/search?search={quote_plus(identifier)}" if identifier else "https://www.curseforge.com/minecraft"


def file_page_url(project_url: object, file_id: int | str) -> str:
    project_page = normalize_project_page(project_url)
    identifier = str(file_id).strip()
    if project_page and identifier:
        return f"{project_page}/files/{identifier}"
    return str(project_url or "").strip()


def file_download_url(project_url: object, file_id: int | str) -> str:
    project_page = normalize_project_page(project_url)
    identifier = str(file_id or "").strip()
    if project_page and identifier.isdigit() and int(identifier) > 0:
        return f"{project_page}/download/{identifier}"
    return str(project_url or "").strip()


def best_manual_download_url(requirement: object) -> str:
    provider = str(getattr(requirement, "provider", "") or "").strip().casefold()
    direct_url = str(getattr(requirement, "direct_url", "") or "").strip()
    version_url = str(getattr(requirement, "version_url", "") or "").strip()
    project_url = str(getattr(requirement, "project_url", "") or "").strip()
    project_id_val = getattr(requirement, "project_id", getattr(requirement, "projectID", 0))
    project_id = int(project_id_val or 0) if str(project_id_val).strip().isdigit() else 0
    file_id = getattr(requirement, "file_id", getattr(requirement, "version_id", getattr(requirement, "fileID", None)))
    file_id_str = str(file_id).strip() if file_id is not None else ""
    if file_id_str == "0":
        file_id_str = ""

    if provider == "curseforge":
        # Prefer the CurseForge download countdown page so the user doesn't have
        # to search for the download button.
        candidate_project = normalize_project_page(project_url) or normalize_project_page(version_url)

        # Check if candidate_project is a numeric placeholder (e.g. /mc-mods/348025) which returns 404
        if (not candidate_project or (project_id > 0 and is_numeric_project_placeholder(candidate_project, project_id))) and project_id > 0:
            resolved_proj = resolve_curseforge_project_slug(project_id)
            if resolved_proj:
                candidate_project = resolved_proj

        if not file_id_str:
            for source_url in (version_url, direct_url):
                if source_url:
                    match = re.search(r"/(?:files|download)/(\d+)", source_url)
                    if match and int(match.group(1)) > 0:
                        file_id_str = match.group(1)
                        break

        file_name = str(getattr(requirement, "file_name", "") or "").strip()
        if not file_id_str and project_id > 0 and file_name:
            try:
                from mcw_core.api.curseforge.curseforge_client import CurseForgeClient
                flist = CurseForgeClient.list_files_result(project_id)
                for cf_file in flist.files:
                    if cf_file.file_name.casefold() == file_name.casefold() and cf_file.file_id > 0:
                        file_id_str = str(cf_file.file_id)
                        break
            except Exception:
                pass

        is_numeric = (project_id > 0 and is_numeric_project_placeholder(candidate_project, project_id)) or (candidate_project.rstrip("/").rsplit("/", 1)[-1].isdigit() if candidate_project else False)
        if candidate_project and not is_numeric and file_id_str and file_id_str.isdigit() and int(file_id_str) > 0:
            return file_download_url(candidate_project, file_id_str)

        if candidate_project and not is_numeric:
            return f"{candidate_project}/files"

        if version_url and not (project_id > 0 and is_numeric_project_placeholder(version_url, project_id)):
            if file_id_str and file_id_str.isdigit() and int(file_id_str) > 0:
                return re.sub(r"/files/(\d+)", r"/download/\1", version_url)
            if "/search?search=" not in version_url:
                return version_url

        if project_id > 0:
            return project_search_url(project_id)

        return project_url or direct_url

    return direct_url or version_url or project_url
