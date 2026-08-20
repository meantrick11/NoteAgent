from pathlib import Path

import noteagent


def test_noteagent_imports_from_src():
    package_path = Path(noteagent.__file__).resolve()
    assert "src" in package_path.parts
    assert package_path.parts[-2:] == ("noteagent", "__init__.py")
