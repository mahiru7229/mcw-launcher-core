from pathlib import Path
import concurrent.futures
import json

from src.core.fs.paths import Paths
from src.core.minecraft.asset_index_manager import (
    AssetIndexManager,
)
from src.core.network.httpx_downloader import HttpDownloader
from src.core.progress.file_batch_progress import FileBatchProgress
from src.core.progress.progress_reporter import ProgressReporter
from src.core.repair.verification_cache import VerificationCache
from src.models.minecraft.assets import DownloadAsset
from src.models.minecraft.version import Version
from src.models.progress.progress_stage import ProgressStage


MAIN_LINK = "https://resources.download.minecraft.net"
MAX_WORKERS = 20


class AssetManager:

    @staticmethod
    def load(
        version: Version,
        reporter: ProgressReporter | None = None,
        verification_cache: VerificationCache | None = None,
        fast_verify: bool = False,
    ) -> Path:
        if verification_cache is None and not fast_verify:
            asset_index_path = AssetIndexManager.load(version=version, reporter=reporter)
        else:
            asset_index_path = AssetIndexManager.load(
                version=version,
                reporter=reporter,
                verification_cache=verification_cache,
                fast_verify=fast_verify,
            )

        assets_data = AssetManager._load_asset_index(
            asset_index_path
        )

        assets = AssetManager._parse_assets(
            assets_data
        )

        total = len(assets)

        batch_progress = FileBatchProgress(reporter=reporter, stage=ProgressStage.DOWNLOADING_ASSETS, message="Preparing Minecraft assets...", total=total, min_emit_interval_seconds=0.08)
        batch_progress.start()

        if total == 0:
            return Paths.asset_index_dir()

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=MAX_WORKERS
        ) as executor:
            future_to_asset = {}
            for asset in assets:
                token = object()
                child_reporter = batch_progress.reporter_for(token)
                if verification_cache is None and not fast_verify:
                    future = executor.submit(AssetManager._download_single_asset, asset) if child_reporter is None else executor.submit(AssetManager._download_single_asset, asset, child_reporter)
                else:
                    future = executor.submit(
                        AssetManager._download_single_asset,
                        asset,
                        child_reporter,
                        verification_cache,
                        fast_verify,
                    )
                future_to_asset[future] = (asset, token)

            for future in concurrent.futures.as_completed(
                future_to_asset
            ):
                asset, token = future_to_asset[future]

                try:
                    future.result()

                except Exception as error:
                    batch_progress.discard(token)
                    raise RuntimeError(
                        "Failed to download asset: "
                        f"{asset.logical_name}"
                    ) from error

                batch_progress.complete(token)


        return Paths.asset_index_dir()

    @staticmethod
    def _download_single_asset(
        asset: DownloadAsset,
        reporter: ProgressReporter | None = None,
        verification_cache: VerificationCache | None = None,
        fast_verify: bool = False,
    ) -> Path:
        asset_path = Paths.asset_object(asset)

        if asset_path.exists():
            if verification_cache is not None:
                verification = verification_cache.verify(
                    "asset:" + asset.sha1,
                    asset_path,
                    asset.size,
                    asset.sha1,
                    "sha1",
                    force_hash=not fast_verify,
                )
                if verification.valid:
                    return asset_path
            elif HttpDownloader.verify_sha1(asset_path, asset.sha1):
                return asset_path

        HttpDownloader.delete_file(asset_path)

        kwargs = {"download_info": asset, "path": asset_path, "max_retry": 5}
        if reporter is not None:
            kwargs.update({"reporter": reporter, "progress_stage": ProgressStage.DOWNLOADING_ASSETS, "progress_message": f"Downloading asset {asset.logical_name}..."})
        downloaded = HttpDownloader.download(**kwargs)
        if verification_cache is not None:
            verification_cache.verify(
                "asset:" + asset.sha1,
                downloaded,
                asset.size,
                asset.sha1,
                "sha1",
                force_hash=True,
            )
        return downloaded

    @staticmethod
    def _load_asset_index(
        path: Path,
    ) -> dict:
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
    def _parse_assets(
        assets_data: dict,
    ) -> list[DownloadAsset]:
        assets: list[DownloadAsset] = []

        for logical_name, obj in assets_data.get(
            "objects",
            {},
        ).items():
            try:
                asset_hash = obj["hash"]

                assets.append(
                    DownloadAsset(
                        logical_name=logical_name,
                        url=AssetManager._build_download_url(
                            asset_hash
                        ),
                        sha1=asset_hash,
                        size=int(obj["size"]),
                    )
                )

            except (
                KeyError,
                TypeError,
                ValueError,
            ) as error:
                raise RuntimeError(
                    f"Invalid asset data: {logical_name}"
                ) from error

        return assets

    @staticmethod
    def _build_download_url(
        asset_hash: str,
    ) -> str:
        return (
            f"{MAIN_LINK}/"
            f"{asset_hash[:2]}/"
            f"{asset_hash}"
        )