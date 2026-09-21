# FastAPI Production Starter

🚀 Production-ready FastAPI template with daily log rotation, type safety, MongoDB/Mysql/Redis support, task scheduling, and comprehensive error handling.

**Features:** Auto API docs • Daily logs • Type validation • API auth • Rate limiting • Background jobs • Health checks • Cloud and local File System • Test suite

Perfect for microservices and data processing APIs. Skip the boilerplate, start building features.

## Setup

> Using `uv` for faster dependency management. Python 3.11+ is required, `.python-version` pins 3.12 so `uv` picks a version that has prebuilt wheels for everything.

```shell
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install all dependencies from pyproject.toml (creates .venv for you)
# dev tools (ruff, mypy, pytest, fakeredis) are included by default
uv sync

# Production box, skip the dev tools
uv sync --no-dev

# With the boto type stubs as well
uv sync --all-extras

# Configure environment
cp .env.example .env
```

## Development

### Code Quality

Using `ruff` for fast linting and formatting:

```shell
# Format code
uv run ruff format .

# Lint and auto-fix
uv run ruff check . --fix

# Type checking
uv run mypy src/ app.py boot.py

# All in one (format check + lint + mypy)
.scripts/check.sh
```

### Testing

```shell
uv run pytest                     # everything, with coverage summary
uv run pytest --no-cov            # faster, no coverage table
uv run pytest tests/test_app.py   # one file
uv run pytest -k "redis or mongo" # by keyword
uv run pytest -x                  # stop at first failure
```

Tests don't need Mongo, MySQL, Redis or any cloud account. Drivers are faked, Redis is `fakeredis`, and files go to a temp dir. `tests/conftest.py` pins the env vars before anything from `src` is imported, so your local `.env` never leaks into a test run.

### Managing Dependencies

```shell
# Add a package
uv add package-name

# Add with specific version
uv add package-name==1.2.3

# Add as dev dependency
uv add --dev package-name

# Update a package
uv lock --upgrade-package <package_name>
uv sync
```

## Start fastapi

```shell
# Using uv (no venv activation needed!)
uv run uvicorn app:app --reload # for local development
uv run uvicorn app:app --host 0.0.0.0 --port 8000 --workers 4 # in production to expose to the world

# Or if you prefer to activate the venv first:
source .venv/bin/activate
uvicorn app:app --reload
```

If you sit behind nginx / a load balancer add `--proxy-headers --forwarded-allow-ips=<proxy ip>` so rate limiting sees the real client IP.

**CORS Configuration**:

-   **Development**: leave `ALLOWED_ORIGINS` empty to allow everything, or set a comma-separated list
-   **Production**: `ALLOWED_ORIGINS` is required, the app refuses to boot without it

### Endpoints:

```bash
curl -X GET http://localhost:8000/health

curl -X POST http://localhost:8000/test \
     -H "Content-Type: application/json" \
     -H "X-API-KEY: your-api-key" \
     -d '{
            "org_id": 1
        }'
```

`/test` shows the pattern for a protected route: `Depends(verify_api_key)` checks `X-API-KEY` against `HTTP_SECRET`, `@limiter.limit()` rate limits it, and the pydantic model validates the body. Swagger UI is at `/docs`.

## Configuration

Everything is read from `.env` into `src/config.py` once at import. Empty values fall back to defaults, booleans are strict (`true/false/1/0/yes/no/on/off`), and a bad value fails fast with a clear message.

| Variable                      | Default                     | Notes                                                                  |
| ----------------------------- | --------------------------- | ---------------------------------------------------------------------- |
| `APP_MODE`                    | `development`               | `development` or `production`                                          |
| `APP_DEBUG`                   | `true`                      | Debug logging (ignored in production)                                  |
| `TZ`                          | `America/New_York`          | App timezone, also used for log rollover and cron schedules            |
| `STORAGE_DIR`                 | `<project>/storage`         | Where logs and local files are written                                 |
| `ALLOWED_ORIGINS`             | empty                       | Comma separated. Required in production                                |
| `HTTP_SECRET`                 | empty                       | Value for the `X-API-KEY` header. Required in production               |
| `DEFAULT_FILESYSTEM`          | `local`                     | `local`, `s3`, `do_spaces`, `minio`                                    |
| `LOCAL_STORAGE_PATH`          | `media`                     | Inside `storage/app/`                                                  |
| `AWS_*`, `DO_SPACES_*`, `MINIO_*` | empty                   | A cloud provider is only registered when its keys are filled in        |
| `MONGO_URI`, `MONGO_DB_NAME`  | `mongodb://localhost:27017`, `app` |                                                                |
| `MONGO_TLS`                   | empty                       | Empty = let the URI decide (`mongodb+srv://` is TLS). `true`/`false` to force |
| `MYSQL_*`                     | `localhost:3306`, `root`, `test` |                                                                   |
| `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB`, `REDIS_PASSWORD` | `localhost:6379`, `0`, none |                                                |
| `GOOGLE_CHAT_DEV_TEAM_WEBHOOK` | empty                      | Used by `async_report()` in production                                 |

## Services required in server

-   Redis (only if you use the cache or websocket rate limiter)

```bash
sudo apt update
sudo apt install redis-server
sudo systemctl status redis
```

### Check app logs

```bash
cat storage/logs/app-yyyy-mm-dd.log
cat storage/logs/error-yyyy-mm-dd.log
```

A new file is started every day at midnight in the app timezone. In debug mode the console shows line numbers too.

## Important

make sure to call `await app_boot()` in your entry file (if not using `src.app.main.py` and `app.py` as it is already done there). It validates the config, sets up logging and registers the storage providers.

### DB Usage

```python
from src.db.async_mongo import mongo_manager, get_collection
from src.db.async_mysql import mysql_manager, fetch_one, execute_query, insert_one, update_records, execute_transaction

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
        user = await users_collection.find_one({"_id": user_id})

        analytics_db = mongo_manager.get_database("analytics") # use a different database
        user_stats = await analytics_db.user_stats.find_one({"user_id": user_id})

        """
        ======================================================
        Mysql Query
        ======================================================
        """
        user = await fetch_one("SELECT * FROM users WHERE id = %s", (user_id,))
        users = await execute_query("SELECT * FROM users WHERE active = %s", (True,))

        new_id = await insert_one("users", {"name": "a", "org_id": 1})
        await update_records("users", {"name": "b"}, "id = %s", (new_id,))

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

Always pass values through `params`. Table and column names given to `insert_one` / `update_records` / `delete_records` are validated and backtick quoted, so a bad key raises instead of ending up in the SQL.

### Cache

```python
from src.cache.redis_service import redis_service

cache = await redis_service.ensure_connected() # shared connection, connects on first use

await cache.set("user:1", {"name": "a"}, ttl=300) # dicts/lists are json encoded
user = await cache.get("user:1")
count = await cache.increment("hits:today", ttl=86400)
```

### Helper & Utilities

```python
await async_report("Message ...", NotificationType.WARNING) # notify (google chat), just logs outside production

get_md5("value") # md5 hash

utcnow() # based on utc
now() # based on app timezone
to_app_timezone(date) # convert date to app tz
```

## API Rate Limit

### Websocket

Needs Redis. If Redis is down the limiter lets the request through and logs an error, it won't take your sockets down with it. Full doc in `src/docs/websocket-rate-limiting.md`.

#### Basic Usage (Connection Rate Limiting)

```python
from src.utils.ws_rate_limiter import ws_rate_limit

@router.websocket("/endpoint")
@ws_rate_limit(requests=10, window=60, scope="connection")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    # Your WebSocket logic here
```

**Parameters:**

-   `requests`: Maximum number of connections allowed (default: 10)
-   `window`: Time window in seconds (default: 60)
-   `scope`: "connection" for limiting new connections, "message" for limiting messages

#### Advanced Usage (Message Rate Limiting)

For rate limiting individual messages within an active WebSocket connection:

```python
from src.utils.ws_rate_limiter import check_message_rate_limit

@router.websocket("/endpoint")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    try:
        while True:
            data = await websocket.receive_text()

            # Check rate limit for each message
            if not await check_message_rate_limit(
                websocket,
                "generate",
                requests=20,
                window=60
            ):
                await websocket.send_json({
                    "type": "error",
                    "content": "Rate limit exceeded. Please slow down."
                })
                continue

            # Process message...
    except WebSocketDisconnect:
        pass
```

### REST API

Follow app.py. The endpoint must take `request: Request`, that's how slowapi finds the client.

```python
@app.get("/things")
@limiter.limit("10/minute")
async def things(request: Request, response: Response):
    #...
```

## Task Scheduling

Cron expressions run in the app timezone (`TZ`).

#### Using decorators (recommended)

```python
from src.schedule.async_scheduler import scheduler

@scheduler.schedule("*/2 * * * *", name="data_sync")
async def sync_data():
    # async function

@scheduler.schedule("0 9 * * 1-5", name="weekday_report")
def generate_weekday_report():
    # This is a sync function - it will run in an executor
```

#### Using convenience methods

```python
async def check_queue():
    # ...

 scheduler.everyMinute(check_queue, name="queue_check")
 # everyMinute | everyFiveMinutes | everyTenMinutes | everyThirtyMinutes | hourly | hourlyAt | daily | dailyAt | weekly | weeklyOn | monthly | monthlyOn

```

#### Adding tasks with custom parameters

```python
async def send_notification(user_id: int, message: str):
   # ...

task = scheduler.add_task(
   send_notification,
   "0 10 * * *",  # Daily at 10 AM
   name="daily_reminder",
   args=(123,),  # user_id
   kwargs={"message": "Don't forget to check your tasks!"},
   max_retries=5,
   retry_delay=120,  # 2 minutes
)
```

Failed tasks retry `max_retries` times, `retry_delay` seconds apart, then go back to their normal schedule. A task that is still running when its next tick comes is skipped, not started twice.

### Run while local development

```bash
python -m src.schedule.example_usage # create your own schedule task files, e.g. src/schedule/tasks.py
```

### Setup in Production

```bash
which python # inside code root while your venv is activated

# should return something like: /home/sourav/apps/py-starter/.venv/bin/python
```

Now refer to `src/schedule/stub/README.md` and replace `/home/ubuntu/apps/py-starter` with your project path and `<which python>`

## Filesystem

Refer `src.filesystem.file_manager.py` to check all supported methods

Local storage is always registered. S3 / Spaces / MinIO are registered by `boot.py` only when their keys are in `.env`, so a fresh checkout boots with just `local`. Paths that try to leave the storage root (`../../etc/passwd`) are rejected.

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
resume_filesys = filesystem.get_provider(StorageProvider.DO_SPACES)

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

## Project layout

```
app.py                      FastAPI app, routes, auth dependency
boot.py                     app_boot(): config validation, logging, storage providers
src/config.py               all env vars in one place
src/app/main.py             entry for standalone scripts
src/cache/                  RedisCache + shared redis_service
src/db/                     mongo (sync), async_mongo (motor), async_mysql (aiomysql)
src/filesystem/             FileManager, LocalStorage, S3CompatibleStorage
src/logging/                DailyFileHandler
src/models/                 pydantic request models
src/report/notify.py        Google Chat notifications
src/schedule/               cron scheduler + deployment stubs
src/utils/                  helpers, perf tracker, http + ws rate limiters
tests/                      pytest suite (no external services needed)
storage/                    logs and local files (gitignored)
```

## TODO

-   Route Middleware
-   auto clean older log files error + app
-   cli arg based commands
-   email
