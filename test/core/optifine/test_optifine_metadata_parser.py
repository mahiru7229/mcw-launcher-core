from src.core.optifine.optifine_metadata_parser import OptiFineMetadataParser


def test_parser_reads_stable_and_preview_rows() -> None:
    html = """
    <h2>Minecraft 1.20.1</h2>
    <table><tr><td>OptiFine HD U I6</td><td>Forge: 47.2.18</td><td>2024-01-01</td>
    <td><a href='adloadx?f=OptiFine_1.20.1_HD_U_I6.jar'>Download</a></td>
    <td><a href='adloadx?f=OptiFine_1.20.1_HD_U_I6.jar'>Mirror</a></td></tr></table>
    <h3>Preview versions</h3>
    <table><tr><td>OptiFine HD U I7 pre1</td>
    <td><a href='adloadx?f=OptiFine_1.20.1_HD_U_I7_pre1.jar'>Mirror</a></td></tr></table>
    """
    versions = OptiFineMetadataParser.parse(html)
    assert len(versions) == 2
    stable = next(item for item in versions if not item.preview)
    preview = next(item for item in versions if item.preview)
    assert stable.minecraft_version == "1.20.1"
    assert stable.filename == "OptiFine_1.20.1_HD_U_I6.jar"
    assert stable.forge_version == "47.2.18"
    assert preview.build == "I7_pre1"
