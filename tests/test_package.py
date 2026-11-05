import acequias
import server


def test_acequias_imports_with_version():
    assert acequias.__version__ == "0.1.0"


def test_server_package_imports():
    assert server.__name__ == "server"
