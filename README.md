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

## Task Scheduling

### Find your venv python path

```bash
which python # inside code root while your venv is activated

# should return something like: /home/sourav/apps/py-starter/venv/bin/python
```

### Run while local development

```bash
/home/sourav/apps/py-starter/venv/bin/python /home/sourav/apps/py-starter/src/schedule/tasks.py
```

### Setup Cron in Production

```bash
crontab -e

# add this line at the bottom
/home/sourav/apps/py-starter/venv/bin/python /home/sourav/apps/py-starter/src/schedule/tasks.py >> /var/log/scheduler.log 2>&1

# check cron logs
cat /var/log/scheduler.log
```

## TODO

-   while in development report in log file
-   Route Middleware
-   cli arg based commands
-   email
