# FastAPI Production Starter

🚀 Production-ready FastAPI template with daily log rotation, type safety, MongoDB/Redis support, task scheduling, and comprehensive error handling.

**Features:** Auto API docs • Daily logs • Type validation • API auth • Background jobs • Health checks

Perfect for microservices and data processing APIs. Skip the boilerplate, start building features.

## Install Python & Create a new virtual environment

```shell
sudo apt-get install python3-venv
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
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
cat src/storage/logs/app-yyyy-mm-dd.log
cat src/storage/logs/error-yyyy-mm-dd.log
```

### Helper & Utilities

```python
await async_report("Message ...", NotificationType.WARNING) # notify (google chat)

get_md5("value") # md5 hash

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

## TODO

-   while in development report in log file
-   Route Middleware
-   cli arg based commands
-   email
