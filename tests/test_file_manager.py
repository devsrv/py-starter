import json

import pytest

from src.filesystem.adapters.local_storage import LocalStorage
from src.filesystem.file_manager import FileManager
from src.filesystem.providers import StorageProvider


class TestRegistry:
    async def test_uninitialized_manager_raises(self):
        await FileManager.reset()
        fm = FileManager()
        assert fm.is_initialized is False
        assert fm.providers == []
        with pytest.raises(RuntimeError, match="not initialized"):
            fm.get_provider()

    async def test_first_provider_becomes_default(self, local_storage, tmp_path):
        await FileManager.reset()
        fm = FileManager()
        other = LocalStorage(str(tmp_path / "other"))
        await fm.add_provider(StorageProvider.S3, local_storage)
        await fm.add_provider(StorageProvider.LOCAL, other)
        assert fm.default_provider_name == "s3"
        assert fm.get_provider() is local_storage
        assert fm.get_provider(StorageProvider.LOCAL) is other
        assert fm.get_provider("local") is other

    async def test_set_as_default_overrides(self, local_storage, tmp_path):
        await FileManager.reset()
        fm = FileManager()
        other = LocalStorage(str(tmp_path / "other"))
        await fm.add_provider(StorageProvider.S3, local_storage)
        await fm.add_provider(StorageProvider.LOCAL, other, set_as_default=True)
        assert fm.default_provider_name == "local"

    async def test_registry_is_shared_between_instances(self, file_manager):
        assert FileManager().get_provider() is file_manager.get_provider()

    async def test_unknown_provider_raises(self, file_manager):
        with pytest.raises(RuntimeError, match="not found"):
            file_manager.get_provider(StorageProvider.MINIO)

    async def test_set_default_provider(self, file_manager, tmp_path):
        assert await file_manager.set_default_provider(StorageProvider.S3) is False
        await file_manager.add_provider(StorageProvider.S3, LocalStorage(str(tmp_path / "s3")))
        assert await file_manager.set_default_provider(StorageProvider.S3) is True
        assert file_manager.default_provider_name == "s3"

    async def test_remove_provider_reassigns_default(self, file_manager, tmp_path):
        await file_manager.add_provider(StorageProvider.S3, LocalStorage(str(tmp_path / "s3")))
        assert await file_manager.remove_provider(StorageProvider.LOCAL) is True
        assert file_manager.default_provider_name == "s3"
        assert await file_manager.remove_provider(StorageProvider.LOCAL) is False
        assert await file_manager.remove_provider(StorageProvider.S3) is True
        assert file_manager.default_provider_name is None
        assert file_manager.is_initialized is False


class TestConvenience:
    async def test_text_roundtrip(self, file_manager):
        assert await file_manager.upload_text("t.txt", "héllo")
        assert await file_manager.download_text("t.txt") == "héllo"

    async def test_json_roundtrip(self, file_manager):
        data = {"a": [1, 2, {"b": None}]}
        assert await file_manager.upload_json("d.json", data)
        assert await file_manager.download_json("d.json") == data
        raw = await file_manager.download("d.json")
        assert json.loads(raw) == data

    async def test_upload_local_file(self, file_manager, tmp_path):
        src = tmp_path / "local.bin"
        src.write_bytes(b"local bytes")
        assert await file_manager.upload_file("remote.bin", str(src), metadata={"k": "v"})
        assert await file_manager.download("remote.bin") == b"local bytes"
        info = await file_manager.get_file_info("remote.bin")
        assert info.metadata == {"k": "v"}

    async def test_download_to_file(self, file_manager, tmp_path):
        await file_manager.upload("x.txt", b"xyz")
        dest = tmp_path / "dl.txt"
        await file_manager.download_to_file("x.txt", str(dest))
        assert dest.read_bytes() == b"xyz"
        with pytest.raises(FileNotFoundError):
            await file_manager.download_to_file("missing.txt", str(dest))

    async def test_exists_size_delete(self, file_manager):
        await file_manager.upload("e.txt", b"12345")
        assert await file_manager.exists("e.txt")
        assert await file_manager.size("e.txt") == 5
        assert await file_manager.delete("e.txt")
        assert not await file_manager.exists("e.txt")

    async def test_list_files_sorting(self, file_manager, local_storage):
        await file_manager.upload("a.txt", b"1")
        await file_manager.upload("b.txt", b"2")
        # make a.txt the newest
        import os
        import time

        now = time.time()
        os.utime(local_storage.base_path / "a.txt", (now + 100, now + 100))
        os.utime(local_storage.base_path / "b.txt", (now, now))
        files = await file_manager.list_files()
        assert [f.name for f in files] == ["a.txt", "b.txt"]
        unsorted = await file_manager.list_files(sort_by_date=False)
        assert {f.name for f in unsorted} == {"a.txt", "b.txt"}

    async def test_folders(self, file_manager):
        assert await file_manager.create_folder("f1/f2")
        await file_manager.upload("f1/f2/x.txt", b"x")
        folders = await file_manager.list_folders()
        assert [f.name for f in folders] == ["f1"]
        assert await file_manager.delete_folder("f1") is False
        assert await file_manager.delete_folder("f1", recursive=True)


class TestCrossProvider:
    @pytest.fixture
    async def two_providers(self, file_manager, tmp_path):
        s3_like = LocalStorage(str(tmp_path / "s3"))
        await file_manager.add_provider(StorageProvider.S3, s3_like)
        return file_manager, s3_like

    async def test_copy_between_providers_keeps_metadata(self, two_providers):
        fm, s3_like = two_providers
        await fm.upload("src.txt", b"data", metadata={"origin": "local"})
        assert await fm.copy(
            "src.txt",
            "dst.txt",
            source_provider=StorageProvider.LOCAL,
            dest_provider=StorageProvider.S3,
        )
        assert await s3_like.download("dst.txt") == b"data"
        assert (await s3_like.get_file_info("dst.txt")).metadata == {"origin": "local"}
        assert await fm.exists("src.txt")  # copy keeps the source

    async def test_copy_within_same_provider(self, file_manager):
        await file_manager.upload("a.txt", b"a")
        assert await file_manager.copy("a.txt", "b.txt")
        assert await file_manager.download("b.txt") == b"a"

    async def test_copy_missing_source_returns_false(self, file_manager):
        assert await file_manager.copy("ghost.txt", "b.txt") is False

    async def test_move(self, two_providers):
        fm, s3_like = two_providers
        await fm.upload("m.txt", b"move me")
        assert await fm.move("m.txt", "moved.txt", dest_provider=StorageProvider.S3)
        assert not await fm.exists("m.txt")
        assert await s3_like.download("moved.txt") == b"move me"
        assert await fm.move("m.txt", "again.txt") is False


class TestBatch:
    async def test_batch_ops(self, file_manager):
        ok = await file_manager.upload_batch(
            [("1.txt", b"1", None, None), ("2.txt", b"2", "text/plain", {"n": 2})]
        )
        assert ok == [True, True]
        assert await file_manager.download_batch(["1.txt", "2.txt"]) == [b"1", b"2"]
        assert await file_manager.exists_batch(["1.txt", "nope"]) == [True, False]
        infos = await file_manager.get_file_info_batch(["2.txt", "nope"])
        assert infos[0].metadata == {"n": 2}
        assert infos[1] is None
        assert await file_manager.delete_batch(["1.txt", "2.txt"]) == [True, True]
