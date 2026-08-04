from pathlib import Path

from src.core.fs.paths import Paths
from src.core.network.httpx_downloader import HttpDownloader
from src.core.progress.progress_reporter import ProgressReporter
from src.core.repair.verification_cache import VerificationCache
from src.models.minecraft.assets_index import DownloadAssetIndex
from src.models.minecraft.version import Version
from src.models.progress.progress_stage import ProgressStage


class AssetIndexManager:

    @staticmethod
    def load(
        version: Version,
        reporter: ProgressReporter | None = None,
        verification_cache: VerificationCache | None = None,
        fast_verify: bool = False,
    ) -> Path:
        asset_index = AssetIndexManager._parse_assets_index(
            version
        )

        asset_index_path = Paths.asset_index(version)

        if asset_index_path.exists():
            if verification_cache is not None:
                verification = verification_cache.verify(
                    "asset-index:" + str(asset_index_path),
                    asset_index_path,
                    asset_index.size,
                    asset_index.sha1,
                    "sha1",
                    force_hash=not fast_verify,
                )
                if verification.valid:
                    return asset_index_path
            elif HttpDownloader.verify_sha1(asset_index_path, asset_index.sha1):
                return asset_index_path

        if asset_index_path.exists():
            HttpDownloader.delete_file(
                asset_index_path
            )

        downloaded = HttpDownloader.download(
            download_info=asset_index,
            path=asset_index_path,
            max_retry=2,
            timeout=20.0,
            reporter=reporter,
            progress_stage=(
                ProgressStage.DOWNLOADING_ASSET_INDEX
            ),
            progress_message=(
                f"Downloading asset index "
                f"{version.assets}.json..."
            ),
        )
        if verification_cache is not None:
            verification_cache.verify(
                "asset-index:" + str(asset_index_path),
                downloaded,
                asset_index.size,
                asset_index.sha1,
                "sha1",
                force_hash=True,
            )
        return downloaded

    @staticmethod
    def _parse_assets_index(
        version: Version,
    ) -> DownloadAssetIndex:
        try:
            asset_index = version.asset_index

            return DownloadAssetIndex(
                url=asset_index["url"],
                sha1=asset_index["sha1"],
                size=int(asset_index["size"]),
                id=asset_index["id"],
            )

        except (
            KeyError,
            TypeError,
            ValueError,
        ) as error:
            raise RuntimeError(
                f"Invalid asset index data for "
                f"Minecraft {version.id}"
            ) from error