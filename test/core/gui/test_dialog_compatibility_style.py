from src.gui.style import APP_STYLE


def test_message_box_is_forced_dark_with_white_text() -> None:
    assert "QMessageBox {" in APP_STYLE
    assert "background: #20221f;" in APP_STYLE
    assert "QMessageBox QLabel" in APP_STYLE
    assert "color: #ffffff;" in APP_STYLE
    assert "background: #f1f1f1;" not in APP_STYLE
    assert "color: #767676;" not in APP_STYLE


def test_launcher_appends_forced_dark_compatibility_layer() -> None:
    assert "QDialog," in APP_STYLE
    assert "QMessageBox," in APP_STYLE
    assert "QMenu," in APP_STYLE
    assert "QToolTip" in APP_STYLE
    assert "QLineEdit:disabled" in APP_STYLE
    assert "color: #ffffff;" in APP_STYLE


def test_compact_layout_has_smaller_navigation_and_titles() -> None:
    assert 'QPushButton#NavButton[compactLayout="true"]' in APP_STYLE
    assert 'QWidget#PageViewport[compactLayout="true"] QLabel#PageTitle' in APP_STYLE
