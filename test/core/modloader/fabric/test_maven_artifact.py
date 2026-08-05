from pathlib import Path

from src.core.modloader.fabric.maven_artifact import MavenArtifact


def test_builds_standard_maven_artifact_path():
    artifact = MavenArtifact.from_coordinate("net.fabricmc:fabric-loader:0.19.3", "https://maven.fabricmc.net")

    assert artifact.path == Path("net/fabricmc/fabric-loader/0.19.3/fabric-loader-0.19.3.jar")
    assert artifact.url == "https://maven.fabricmc.net/net/fabricmc/fabric-loader/0.19.3/fabric-loader-0.19.3.jar"


def test_supports_classifier_and_extension():
    artifact = MavenArtifact.from_coordinate("example.group:demo:1.0:client@zip", "https://repo.example/")

    assert artifact.path == Path("example/group/demo/1.0/demo-1.0-client.zip")
    assert artifact.url.endswith("/example/group/demo/1.0/demo-1.0-client.zip")
