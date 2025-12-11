"""Tests for filesystem utilities."""


from app.utils.filesystem import temp_workspace


def test_temp_workspace_creates_directory():
    with temp_workspace("test_") as temp_dir:
        assert temp_dir.exists()
        assert temp_dir.is_dir()
        assert "test_" in temp_dir.name


def test_temp_workspace_cleans_up():
    temp_path = None
    with temp_workspace("cleanup_test_") as temp_dir:
        temp_path = temp_dir
        # Create a file inside
        test_file = temp_dir / "test.txt"
        test_file.write_text("test content")
        assert test_file.exists()

    # After context exits, directory should be cleaned up
    assert temp_path is not None
    assert not temp_path.exists()


def test_temp_workspace_multiple_instances():
    # Multiple workspaces should have different paths
    with temp_workspace("first_") as dir1:
        with temp_workspace("second_") as dir2:
            assert dir1 != dir2
            assert dir1.exists()
            assert dir2.exists()


def test_temp_workspace_with_nested_files():
    with temp_workspace("nested_") as temp_dir:
        # Create nested structure
        subdir = temp_dir / "subdir"
        subdir.mkdir()
        (subdir / "file1.txt").write_text("content1")
        (subdir / "file2.txt").write_text("content2")

        assert (subdir / "file1.txt").exists()
        assert (subdir / "file2.txt").exists()

    # All should be cleaned up
    assert not temp_dir.exists()


def test_temp_workspace_exception_handling():
    temp_path = None
    try:
        with temp_workspace("exception_test_") as temp_dir:
            temp_path = temp_dir
            (temp_dir / "file.txt").write_text("test")
            raise ValueError("Test exception")
    except ValueError:
        pass

    # Directory should still be cleaned up even after exception
    assert temp_path is not None
    assert not temp_path.exists()
