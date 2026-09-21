# Production Deployment Guide for Task Scheduler

The scheduler is a plain long-running Python process, so run it under something
that restarts it on crash and starts it on boot. Both stubs run
`python -m src.schedule.tasks`, so create `src/schedule/tasks.py` that registers
your tasks and calls `await scheduler.start()` (see `example_usage.py`).

Before copying either file, find your interpreter and project root:

```bash
which python   # run inside the project root with the venv activated
# e.g. /home/ubuntu/apps/py-starter/.venv/bin/python
```

and replace every `/home/ubuntu/apps/py-starter` in the stub.

## 1. Systemd Service (Recommended for Linux VPS/EC2)

```bash
sudo cp src/schedule/stub/systemd/scheduler.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable scheduler     # start on boot
sudo systemctl start scheduler
sudo systemctl status scheduler
sudo journalctl -u scheduler -f     # follow logs
```

Management:

```bash
sudo systemctl stop scheduler
sudo systemctl restart scheduler
sudo systemctl disable scheduler
```

## 2. Supervisor

```bash
sudo apt-get install supervisor
sudo cp src/schedule/stub/supervisor/scheduler.conf /etc/supervisor/conf.d/
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start scheduler
```

Management:

```bash
sudo supervisorctl status scheduler
tail -f /var/log/supervisor/scheduler.log
sudo supervisorctl restart scheduler
sudo supervisorctl stop scheduler
```
