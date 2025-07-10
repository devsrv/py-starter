# Production Deployment Guide for Task Scheduler

This guide covers various methods to deploy the task scheduler in production.

## 1. Systemd Service (Recommended for Linux VPS/EC2)

### Installation

```bash
# Copy the service file
sudo cp src/schedule/stub/systemd/scheduler.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable the service to start on boot
sudo systemctl enable scheduler

# Start the service
sudo systemctl start scheduler

# Check status
sudo systemctl status scheduler

# View logs
sudo journalctl -u scheduler -f
```

### Management Commands

```bash
# Stop the service
sudo systemctl stop scheduler

# Restart the service
sudo systemctl restart scheduler

# Disable from starting on boot
sudo systemctl disable scheduler
```

## 2. Supervisor

### Installation

```bash
# Install supervisor
sudo apt-get install supervisor

# Copy configuration
sudo cp src/schedule/stub/supervisor/scheduler.conf /etc/supervisor/conf.d/

# Reload supervisor
sudo supervisorctl reread
sudo supervisorctl update

# Start the scheduler
sudo supervisorctl start resume-parser-scheduler
```

### Management Commands

```bash
# Check status
sudo supervisorctl status resume-parser-scheduler

# View logs
tail -f /var/log/supervisor/resume-parser-scheduler.log

# Restart
sudo supervisorctl restart resume-parser-scheduler

# Stop
sudo supervisorctl stop resume-parser-scheduler
```
