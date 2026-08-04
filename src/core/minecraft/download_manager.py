from pathlib import Path
import json

from src.core.fs.paths import Paths
from src.core.network.httpx_downloader import HttpDownloader
from src.core.progress.progress_reporter import ProgressReporter
from src.core.repair.verification_cache import VerificationCache
from src.models.minecraft.download import DownloadClient
from src.models.minecraft.version import Version
from src.models.progress.progress_stage import ProgressStage


class DownloadClientManager:

    @staticmethod
    def load(
        version: Version,
        reporter: ProgressReporter | None = None,
        verification_cache: VerificationCache | None = None,
        fast_verify: bool = False,
    ) -> Path:
        client_data = DownloadClientManager._load_download(
            version.path
        )

        client_obj = DownloadClientManager._load_download_object(
            client_data
        )

        client_dir = Paths.version_dir(version)
        client_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        client_path = Paths.client(version)

        if client_path.exists():
            if verification_cache is not None:
                verification = verification_cache.verify(
                    "client:" + str(client_path),
                    client_path,
                    client_obj.size,
                    client_obj.sha1,
                    "sha1",
                    force_hash=not fast_verify,
                )
                if verification.valid:
                    return client_path
            elif HttpDownloader.verify_sha1(client_path, client_obj.sha1):
                return client_path

        if client_path.exists():
            HttpDownloader.delete_file(client_path)

        downloaded = HttpDownloader.download(
            download_info=client_obj,
            path=client_path,
            reporter=reporter,
            progress_stage=ProgressStage.DOWNLOADING_CLIENT,
            progress_message=(
                f"Downloading Minecraft "
                f"{version.id} client..."
            ),
        )
        if verification_cache is not None:
            verification_cache.verify(
                "client:" + str(client_path),
                downloaded,
                client_obj.size,
                client_obj.sha1,
                "sha1",
                force_hash=True,
            )
        return downloaded

    @staticmethod
    def _load_download(path: Path) -> dict:
        try:
            return json.loads(
                path.read_text(encoding="utf-8")
            )

        except (
            FileNotFoundError,
            json.JSONDecodeError,
        ):
            return {}

    @staticmethod
    def _load_download_object(
        download_dict: dict,
    ) -> DownloadClient:
        try:
            client_data = download_dict["downloads"]["client"]

            return DownloadClient(
                url=client_data["url"],
                sha1=client_data["sha1"],
                size=int(client_data["size"]),
            )

        except (
            KeyError,
            TypeError,
            ValueError,
        ) as error:
            raise RuntimeError(
                "Invalid Minecraft client download data"
            ) from error