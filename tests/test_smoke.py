"""Phase 1 smoke test: the package imports and declares a version. Zero-cost."""

import dagwell


def test_import_and_version():
    assert isinstance(dagwell.__version__, str)
    assert dagwell.__version__


if __name__ == "__main__":
    test_import_and_version()
    print("smoke: PASS")
