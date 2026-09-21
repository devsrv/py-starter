"""
S3CompatibleStorage tests. No network: `session.client(...)` is swapped for a fake
async context manager yielding a FakeS3 object that records the boto calls.
"""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

from src.filesystem.adapters.s3_compatible_storage import (
    DELETE_BATCH_SIZE,
    S3CompatibleStorage,
)

CREDS = {"access_key_id": "AK", "secret_access_key": "SK"}
NOW = datetime(2025, 1, 1, tzinfo=UTC)


def client_error(code="404", op="HeadObject"):
    return ClientError({"Error": {"Code": code, "Message": "boom"}}, op)


class FakePaginator:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    async def paginate(self, **kwargs):
        self.calls.append(kwargs)
        for page in self.pages:
            yield page


class FakeS3:
    def __init__(self):
        self.upload_fileobj = AsyncMock()
        self.get_object = AsyncMock()
        self.download_file = AsyncMock()
        self.delete_object = AsyncMock()
        self.head_object = AsyncMock()
        self.put_object = AsyncMock()
        self.delete_objects = AsyncMock()
        self.paginator = FakePaginator([])

    def get_paginator(self, name):
        assert name == "list_objects_v2"
        return self.paginator


@pytest.fixture
def storage():
    s = S3CompatibleStorage(bucket_name="bucket", **CREDS)
    fake = FakeS3()

    @asynccontextmanager
    async def _client():
        yield fake

    s._client = _client  # type: ignore[method-assign]
    s.fake = fake  # type: ignore[attr-defined]
    return s


class TestConstruction:
    def test_aws_defaults(self):
        s = S3CompatibleStorage(bucket_name="b", **CREDS)
        assert s.provider == "aws"
        assert s.endpoint_url is None
        assert "endpoint_url" not in s.client_config
        assert s.client_config == {"use_ssl": True, "verify": True}

    def test_requires_bucket(self):
        with pytest.raises(ValueError, match="bucket_name"):
            S3CompatibleStorage(**CREDS)

    def test_requires_credentials(self):
        with pytest.raises(ValueError, match="Access key"):
            S3CompatibleStorage(bucket_name="b")

    def test_unknown_provider_without_endpoint(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            S3CompatibleStorage(bucket_name="b", provider="nimbus", **CREDS)

    def test_unknown_provider_with_endpoint_is_fine(self):
        s = S3CompatibleStorage(
            bucket_name="b", provider="nimbus", endpoint_url="https://x.y", **CREDS
        )
        assert s.client_config["endpoint_url"] == "https://x.y"

    def test_digitalocean_helper(self):
        s = S3CompatibleStorage.for_digitalocean("space", "sgp1", "k", "s")
        assert s.endpoint_url == "https://sgp1.digitaloceanspaces.com"
        assert s.bucket_name == "space"
        assert s.region == "sgp1"

    def test_wasabi_helper(self):
        s = S3CompatibleStorage.for_wasabi("b", "us-west-1", "k", "s")
        assert s.endpoint_url == "https://s3.us-west-1.wasabisys.com"

    def test_minio_helper_detects_ssl(self):
        plain = S3CompatibleStorage.for_minio("b", "http://localhost:9000", "k", "s")
        assert plain.client_config["use_ssl"] is False
        tls = S3CompatibleStorage.for_minio("b", "https://minio.internal", "k", "s")
        assert tls.client_config["use_ssl"] is True
        # explicit kwarg wins and does not raise "multiple values for use_ssl"
        forced = S3CompatibleStorage.for_minio("b", "http://localhost:9000", "k", "s", use_ssl=True)
        assert forced.client_config["use_ssl"] is True

    def test_provider_is_case_insensitive(self):
        s = S3CompatibleStorage(bucket_name="b", provider="DigitalOcean", region="nyc3", **CREDS)
        assert s.endpoint_url == "https://nyc3.digitaloceanspaces.com"


class TestUpload:
    async def test_upload_bytes_guesses_content_type_and_stringifies_metadata(self, storage):
        assert await storage.upload("docs/readme.md", b"# hi", metadata={"n": 1})
        args, kwargs = storage.fake.upload_fileobj.call_args
        assert args[1:] == ("bucket", "docs/readme.md")
        assert args[0].read() == b"# hi"
        assert kwargs["ExtraArgs"]["ContentType"] == "text/markdown"
        assert kwargs["ExtraArgs"]["Metadata"] == {"n": "1"}

    async def test_upload_explicit_content_type(self, storage):
        await storage.upload("blob", b"x", content_type="application/x-custom")
        assert (
            storage.fake.upload_fileobj.call_args.kwargs["ExtraArgs"]["ContentType"]
            == "application/x-custom"
        )

    async def test_upload_rejects_bad_content(self, storage):
        with pytest.raises(TypeError):
            await storage.upload("x", 123)  # type: ignore[arg-type]

    async def test_upload_failure_returns_false(self, storage):
        storage.fake.upload_fileobj.side_effect = client_error("AccessDenied", "PutObject")
        assert await storage.upload("x", b"1") is False
        storage.fake.upload_fileobj.side_effect = EndpointConnectionError(endpoint_url="http://x")
        assert await storage.upload("x", b"1") is False


class TestReads:
    async def test_download(self, storage):
        body = AsyncMock()
        body.read.return_value = b"payload"
        storage.fake.get_object.return_value = {"Body": body}
        assert await storage.download("k") == b"payload"
        storage.fake.get_object.assert_awaited_with(Bucket="bucket", Key="k")

    async def test_download_missing_raises(self, storage):
        storage.fake.get_object.side_effect = client_error("NoSuchKey", "GetObject")
        with pytest.raises(FileNotFoundError):
            await storage.download("k")

    async def test_download_to_file(self, storage):
        assert await storage.download_to_file("k", "/tmp/x")
        storage.fake.download_file.assert_awaited_with("bucket", "k", "/tmp/x")
        storage.fake.download_file.side_effect = client_error()
        assert await storage.download_to_file("k", "/tmp/x") is False

    async def test_exists_and_size(self, storage):
        storage.fake.head_object.return_value = {"ContentLength": 11}
        assert await storage.exists("k")
        assert await storage.size("k") == 11
        storage.fake.head_object.side_effect = client_error()
        assert await storage.exists("k") is False
        with pytest.raises(FileNotFoundError):
            await storage.size("k")

    async def test_get_file_info(self, storage):
        storage.fake.head_object.return_value = {
            "ContentLength": 3,
            "LastModified": NOW,
            "ContentType": "image/png",
            "ETag": '"abc"',
            "Metadata": {"a": "b"},
        }
        info = await storage.get_file_info("img/pic.png")
        assert info.name == "pic.png"
        assert info.path == "img/pic.png"
        assert info.size == 3
        assert info.etag == "abc"
        assert info.metadata == {"a": "b"}
        storage.fake.head_object.side_effect = client_error()
        assert await storage.get_file_info("x") is None


class TestListing:
    async def test_list_files_skips_folder_markers_and_sorts(self, storage):
        older = datetime(2024, 1, 1, tzinfo=UTC)
        storage.fake.paginator = FakePaginator(
            [
                {"Contents": [{"Key": "dir/", "Size": 0, "LastModified": NOW}]},
                {
                    "Contents": [
                        {"Key": "dir/a.txt", "Size": 1, "LastModified": older, "ETag": '"e1"'},
                        {"Key": "dir/b.jpg", "Size": 2, "LastModified": NOW},
                        {"Key": "dir/broken"},  # malformed entry
                    ]
                },
            ]
        )
        files = await storage.list_files("dir")
        assert [f.path for f in files] == ["dir/b.jpg", "dir/a.txt"]
        assert files[0].content_type == "image/jpeg"
        assert files[1].etag == "e1"
        assert files[0].etag is None
        assert storage.fake.paginator.calls == [
            {"Bucket": "bucket", "Prefix": "dir/", "Delimiter": "/"}
        ]

    async def test_list_files_recursive_has_no_delimiter(self, storage):
        await storage.list_files("/dir/", recursive=True)
        assert storage.fake.paginator.calls == [{"Bucket": "bucket", "Prefix": "dir/"}]

    async def test_list_files_root_and_errors(self, storage):
        await storage.list_files()
        assert storage.fake.paginator.calls[0]["Prefix"] == ""

        async def boom(**kwargs):
            raise client_error("AccessDenied", "ListObjectsV2")
            yield  # pragma: no cover

        storage.fake.paginator.paginate = boom
        assert await storage.list_files() == []

    async def test_list_folders(self, storage):
        pages = iter(
            [
                [{"CommonPrefixes": [{"Prefix": "photos/"}, {"Prefix": "empty/"}]}],
                [{"Contents": [{"Key": "photos/1.jpg", "Size": 10, "LastModified": NOW}]}],
                [{}],
            ]
        )

        class SeqPaginator:
            async def paginate(self, **kwargs):
                for page in next(pages):
                    yield page

        storage.fake.get_paginator = lambda name: SeqPaginator()
        folders = await storage.list_folders()
        assert [f.name for f in folders] == ["photos", "empty"]
        assert folders[0].file_count == 1
        assert folders[0].total_size == 10
        assert folders[0].last_modified == NOW
        assert folders[1].file_count == 0
        assert folders[1].last_modified.tzinfo is not None


class TestWrites:
    async def test_delete(self, storage):
        assert await storage.delete("k")
        storage.fake.delete_object.assert_awaited_with(Bucket="bucket", Key="k")
        storage.fake.delete_object.side_effect = client_error()
        assert await storage.delete("k") is False

    async def test_create_folder(self, storage):
        assert await storage.create_folder("a/b")
        storage.fake.put_object.assert_awaited_with(Bucket="bucket", Key="a/b/")
        assert await storage.create_folder("") is False

    async def test_delete_folder_refuses_non_empty_unless_recursive(self, storage):
        storage.fake.paginator = FakePaginator(
            [{"Contents": [{"Key": "f/"}, {"Key": "f/sub/deep.txt"}]}]
        )
        assert await storage.delete_folder("f") is False
        storage.fake.delete_objects.assert_not_awaited()

        assert await storage.delete_folder("f", recursive=True)
        payload = storage.fake.delete_objects.call_args.kwargs["Delete"]
        assert payload["Objects"] == [{"Key": "f/"}, {"Key": "f/sub/deep.txt"}]

    async def test_delete_folder_marker_only_counts_as_empty(self, storage):
        storage.fake.paginator = FakePaginator([{"Contents": [{"Key": "f/"}]}])
        assert await storage.delete_folder("f")
        storage.fake.delete_objects.assert_awaited_once()

    async def test_delete_folder_chunks_large_batches(self, storage):
        keys = [{"Key": f"big/{i}.txt"} for i in range(DELETE_BATCH_SIZE + 5)]
        storage.fake.paginator = FakePaginator([{"Contents": keys}])
        assert await storage.delete_folder("big", recursive=True)
        assert storage.fake.delete_objects.await_count == 2
        sizes = [
            len(c.kwargs["Delete"]["Objects"]) for c in storage.fake.delete_objects.await_args_list
        ]
        assert sizes == [DELETE_BATCH_SIZE, 5]

    async def test_delete_folder_never_wipes_bucket_root(self, storage):
        assert await storage.delete_folder("", recursive=True) is False
        assert await storage.delete_folder("/", recursive=True) is False

    async def test_delete_folder_error(self, storage):
        storage.fake.paginator = FakePaginator([{"Contents": [{"Key": "f/x"}]}])
        storage.fake.delete_objects.side_effect = client_error("AccessDenied", "DeleteObjects")
        assert await storage.delete_folder("f", recursive=True) is False
