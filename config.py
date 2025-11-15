import os
CONFIG = {
    "github_repo": "InnoDev69/hardwareMonitor",
    "log_file": "logs/hardware_metrics.txt",
    "db_file": "logs/hardware_metrics.db",
    "log_compression": True,
    "check_updates_interval": 86400,
    "metrics_interval": 5,
    "update_timeout": 30,
    "debug": True,
    "github_token": os.getenv("GITHUB_TOKEN", ""),
    "flask_host": "0.0.0.0",
    "flask_port": 4000,
    "flask_debug": False
}