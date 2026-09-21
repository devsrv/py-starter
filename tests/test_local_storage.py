import io
from datetime import UTC
from pathlib import Path

import pytest

from src.filesystem.adapters.local_storage import LocalStorage


async def test_upload_bytes_and_download(local_storage):
    assert await local_storage.upload("a/b/hello.txt", b"hi there")
    assert await local_storage.download("a/b/hello.txt") == b"hi there"
    assert await local_storage.exists("a/b/hello.txt")
    assert await local_storage.size("a/b/hello.txt") == 8


async def test_upload_file_like_objects(local_storage):
    assert await local_storage.upload("bin.dat", io.BytesIO(b"\x00\x01"))
    assert await local_storage.download("bin.dat") == b"\x00\x01"
    # text streams are encoded as utf-8
    assert await local_storage.upload("text.txt", io.StringIO("héllo"))
    assert await local_storage.download("text.txt") == "héllo".encode()


async def test_upload_rejects_unknown_content_type(local_storage):
    assert await local_storage.upload("x.txt", 12345) is False  # type: ignore[arg-type]
    assert not await local_storage.exists("x.txt")


async def test_metadata_sidecar_roundtrip(local_storage):
    meta = {"author": "tests", "n": 1}
    await local_storage.upload("doc.txt", b"x", metadata=meta)
    info = await local_storage.get_file_info("doc.txt")
    assert info is not None
    assert info.metadata == meta
    assert info.content_type == "text/plain"
    assert info.name == "doc.txt"
    assert info.path == "doc.txt"
    assert info.last_modified.tzinfo == UTC

    # Re-uploading without metadata clears the stale sidecar
    await local_storage.upload("doc.txt", b"y")
    info = await local_storage.get_file_info("doc.txt")
    assert info.metadata == {}
    assert not (local_storage.base_path / "doc.txt.meta").exists()


async def test_corrupt_metadata_is_ignored(local_storage):
    await local_storage.upload("doc.txt", b"x")
    (local_storage.base_path / "doc.txt.meta").write_text("{not json")
    info = await local_storage.get_file_info("doc.txt")
    assert info.metadata == {}


async def test_download_missing_raises(local_storage):
    with pytest.raises(FileNotFoundError):
        await local_storage.download("nope.txt")
    with pytest.raises(FileNotFoundError):
        await local_storage.size("nope.txt")
    assert await local_storage.get_file_info("nope.txt") is None


async def test_download_to_file(local_storage, tmp_path):
    payload = b"z" * (2 * 1024 * 1024 + 17)  # spans several 1MB chunks
    await local_storage.upload("big.bin", payload)
    dest = tmp_path / "out" / "copy.bin"
    assert await local_storage.download_to_file("big.bin", str(dest))
    assert dest.read_bytes() == payload
    assert await local_storage.download_to_file("missing.bin", str(dest)) is False


async def test_delete(local_storage):
    await local_storage.upload("d.txt", b"x", metadata={"k": "v"})
    assert await local_storage.delete("d.txt")
    assert not await local_storage.exists("d.txt")
    assert not (local_storage.base_path / "d.txt.meta").exists()
    assert await local_storage.delete("d.txt") is False


async def test_exists_is_false_for_directories(local_storage):
    await local_storage.create_folder("dir")
    assert await local_storage.exists("dir") is False


async def test_list_files(local_storage):
    await local_storage.upload("root.txt", b"1")
    await local_storage.upload("sub/one.txt", b"22", metadata={"m": 1})
    await local_storage.upload("sub/deep/two.txt", b"333")

    top = await local_storage.list_files()
    assert [f.path for f in top] == ["root.txt"]

    sub = await local_storage.list_files("sub")
    assert [f.path for f in sub] == ["sub/one.txt"]
    assert sub[0].metadata == {"m": 1}

    everything = await local_storage.list_files(recursive=True)
    assert sorted(f.path for f in everything) == ["root.txt", "sub/deep/two.txt", "sub/one.txt"]
    assert all(not f.name.endswith(".meta") for f in everything)

    assert await local_storage.list_files("does/not/exist") == []


async def test_list_folders(local_storage):
    await local_storage.upload("a/x.txt", b"1234")
    await local_storage.upload("a/nested/y.txt", b"56")
    await local_storage.upload("b/z.txt", b"7")
    await local_storage.upload("top.txt", b"0")

    folders = await local_storage.list_folders()
    assert [f.name for f in folders] == ["a", "b"]
    a = folders[0]
    assert a.path == "a"
    assert a.file_count == 2
    assert a.total_size == 6
    assert await local_storage.list_folders("missing") == []


async def test_create_and_delete_folder(local_storage):
    assert await local_storage.create_folder("f/g")
    assert (local_storage.base_path / "f" / "g").is_dir()

    await local_storage.upload("f/g/file.txt", b"x")
    assert await local_storage.delete_folder("f/g") is False  # not empty, not recursive
    assert await local_storage.delete_folder("f/g", recursive=True)
    assert not (local_storage.base_path / "f" / "g").exists()
    assert await local_storage.delete_folder("f")  # now empty
    assert await local_storage.delete_folder("f") is False  # gone


async def test_never_deletes_storage_root(local_storage):
    await local_storage.upload("keep.txt", b"x")
    assert await local_storage.delete_folder("", recursive=True) is False
    assert await local_storage.delete_folder(".", recursive=True) is False
    assert await local_storage.exists("keep.txt")


@pytest.mark.parametrize("evil", ["../escape.txt", "a/../../escape.txt", "/../../etc/passwd"])
async def test_path_traversal_is_blocked(local_storage, tmp_path, evil):
    assert await local_storage.upload(evil, b"pwned") is False
    assert await local_storage.exists(evil) is False
    with pytest.raises(ValueError):
        await local_storage.download(evil)
    assert not (tmp_path / "escape.txt").exists()


async def test_leading_slash_is_relative_to_root(local_storage):
    assert await local_storage.upload("/abs/file.txt", b"x")
    assert await local_storage.exists("abs/file.txt")


async def test_batch_operations(local_storage):
    results = await local_storage.upload_batch(
        [("b1.txt", b"1", None, None), ("b2.txt", b"2", "text/plain", {"i": 2})]
    )
    assert results == [True, True]
    assert await local_storage.download_batch(["b1.txt", "b2.txt"]) == [b"1", b"2"]
    assert await local_storage.delete_batch(["b1.txt", "b2.txt", "missing"]) == [True, True, False]


def test_base_path_is_created(tmp_path):
    target = tmp_path / "fresh" / "dir"
    LocalStorage(str(target))
    assert target.is_dir()
    assert Path(LocalStorage(str(target)).base_path).is_absolute()
