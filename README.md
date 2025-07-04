# FastAPI Production Starter

🚀 Production-ready FastAPI template with daily log rotation, type safety, MongoDB/Mysql/Redis support, task scheduling, and comprehensive error handling.

**Features:** Auto API docs • Daily logs • Type validation • API auth • Background jobs • Health checks • Cloud and local File System

Perfect for microservices and data processing APIs. Skip the boilerplate, start building features.

## Install Python & Create a new virtual environment

```shell
sudo apt-get install python3-venv
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

## Start fastapi

```shell
uvicorn app:app --reload # for local development
uvicorn app:app --host 0.0.0.0 --port 8000 --workers 4 # in production to expose to the world
```

### Endpoints:

```bash
curl -X GET http://localhost:8000/health

curl -X POST http://localhost:8000/test \
     -H "Content-Type: application/json" \
     -H "X-API-KEY: your-api-key" \
     -d '{
            "org_id": "1"
        }'
```

## Services required in server

-   Redis

```bash
sudo apt update
sudo systemctl status redis
```

### Check app logs

```bash
cat storage/logs/app-yyyy-mm-dd.log
cat storage/logs/error-yyyy-mm-dd.log
```

## Important

make sure to call `await app_boot()` in your entry file (if not using `src.app.main.py` and `app.py` as it is already done there)

### DB Usage

```python
from src.db.async_mongo import mongo_manager, get_collection
from src.db.async_mysql import mysql_manager, fetch_one, execute_query, execute_transaction

async def main():
    await app_boot()

    try:
        await mongo_manager.initialize()
        await mysql_manager.initialize()

        """
        ======================================================
        Mongo Query
        ======================================================
        """
        users_collection = await get_collection("users") # using default database
        user = users_collection.find_one({"_id": user_id})

        analytics_db = mongo_manager.get_database("analytics") # use a different database
        user_stats = await analytics_db.user_stats.find_one({"user_id": user_id})

        """
        ======================================================
        Mysql Query
        ======================================================
        """
        user = await fetch_one("SELECT * FROM users WHERE id = %s", (user_id,))
        users = await execute_query("SELECT * FROM users WHERE active = %s", (True,))

        queries = [
            ("UPDATE accounts SET balance = balance - %s WHERE id = %s", (amount, from_account)),
            ("INSERT INTO transactions (from_account, to_account, amount) VALUES (%s, %s, %s)",
            (from_account, to_account, amount))
        ]
        await execute_transaction(queries)

    except Exception as e:
        logger.error(f"Critical error in batch generate execution: {str(e)}")
        await async_report(f"Critical error in batch generate execution: {str(e)}", NotificationType.ERROR)
        raise
    finally:
        await mongo_manager.close()
        await mysql_manager.close()
```

### Helper & Utilities

```python
await async_report("Message ...", NotificationType.WARNING) # notify (google chat)

get_md5("value") # md5 hash

utcnow() # based on utc
now() # based on app timezone
to_app_timezone(date) # convert date to app tz
```

## Task Scheduling

### Find your venv python path

```bash
which python # inside code root while your venv is activated

# should return something like: /home/sourav/apps/py-starter/venv/bin/python
```

### Run while local development

```bash
python -m src.schedule.tasks
```

### Setup Cron in Production

```bash
crontab -e

# add this line at the bottom
* * * * * cd /home/sourav/apps/py-starter && /home/sourav/apps/py-starter/venv/bin/python -m src.schedule.tasks >> /var/log/scheduler.log 2>&1

# check cron logs
cat /var/log/scheduler.log
```

## Filesystem

Refer `src.filesystem.file_manager.py` to check all supported methods

```python
"""Quick Guide of how to use the cloud file manager."""

file_manager = FileManager() # using default filemanager driver (check boot.py)

# To manually register or use a driver (preferably in boot.py)
minio_storage = S3CompatibleStorage.for_minio(
    bucket_name=Config.MINIO_BUCKET,
    endpoint_url=Config.MINIO_ENDPOINT,
    access_key=Config.MINIO_ACCESS_KEY,
    secret_key=Config.MINIO_SECRET_KEY,
)
await file_manager.add_provider(StorageProvider.MINIO, minio_storage, set_as_default=True)

# use multiple adaptars on the fly
filesystem = FileManager()
resume_filesys = self.filesystem.get_provider(StorageProvider.DO_SPACES.value)

# download remote file to tmp
file_path = "media/abc.txt"
temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=Path(file_path).suffix)
temp_path = temp_file.name
temp_file.close()

await file_manager.download_to_file(
    file_path=file_path,
    local_file_path=temp_path
)

# Upload
content = b"Hello, World! This is a test file."
success = await file_manager.upload("test/hello.txt", content, metadata={"author": "Python Script"})
print(f"Upload successful: {success}")

# Check if file exists
exists = await file_manager.exists("test/hello.txt")
print(f"File exists: {exists}")

# Get file size
if exists:
    file_size = await file_manager.size("test/hello.txt")
    print(f"File size: {file_size} bytes")

copied = await file_manager.copy('test/hello.txt', 'test/hello_copy.txt', source_provider=StorageProvider.S3, dest_provider=StorageProvider.LOCAL)
print(f"File copied in local: {copied}")


""" Performance improvements with async """
async def example_performance_improvements():
    file_manager = FileManager()

    # Process multiple files concurrently instead of sequentially
    async def process_file(file_path):
        if await file_manager.exists(file_path):
            content = await file_manager.download(file_path)
            # Process content...
            processed_content = content.upper()
            await file_manager.upload(f'processed_{file_path}', processed_content)
            return True
        return False

    file_paths = ['file1.txt', 'file2.txt', 'file3.txt', 'file4.txt']

    # Process all files concurrently
    results = await asyncio.gather(*[process_file(path) for path in file_paths])

    # Cross-provider operations with better performance
    # Copy files from S3 to local storage concurrently
    async def backup_to_local(file_path):
        return await file_manager.copy(
            file_path, f'backup/{file_path}',
            source_provider=StorageProvider.S3,
            dest_provider=StorageProvider.LOCAL
        )

    s3_files = await file_manager.list_files(provider=StorageProvider.S3)
    backup_results = await asyncio.gather(*[
        backup_to_local(file.path) for file in s3_files[:10]  # Backup first 10 files
    ])
```

## TODO

-   Route Middleware
-   auto clean older log files error + app
-   cli arg based commands
-   email
