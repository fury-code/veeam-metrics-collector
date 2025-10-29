import os

import sentry_sdk
from dotenv import load_dotenv

from vb365.collector import microsoft365
from vbr.collector import backup_replication

load_dotenv()

# Sentry initialization
SENTRY_DSN_KEY = os.getenv("SENTRY_DSN_KEY")

if SENTRY_DSN_KEY:
    sentry_sdk.init(
        dsn=os.getenv("SENTRY_DSN_KEY"),
        # Set traces_sample_rate to 1.0 to capture 100%
        # of transactions for performance monitoring.
        traces_sample_rate=1.0,
        # Set profiles_sample_rate to 1.0 to profile 100%
        # of sampled transactions.
        # We recommend adjusting this value in production.
        profiles_sample_rate=1.0,
    )

# Environment variables
env_config = {
    # Global
    "timezone": os.getenv("TZ"),
    # InfluxDB
    "influxdb_url": os.getenv("INFLUXDBURL"),
    "influxdb_bucket": os.getenv("INFLUXDBBUCKET"),
    "influxdb_token": os.getenv("INFLUXDBTOKEN"),
    "influxdb_org": os.getenv("INFLUXDBORG"),
    # Veeam general
    "veeam_username": os.getenv("VEEAMUSERNAME"),
    "veeam_password": os.getenv("VEEAMPASSWORD"),
    # VBR specific
    "vbr_backup_server": os.getenv("VBRBACKUPSERVER"),
    "vbr_backup_port": os.getenv("VBRBACKUPPORT"),
    # VB365 specific
    "vb365_rest_server": os.getenv("VB365RESTSERVER"),
    "vb365_rest_port": os.getenv("VB365RESTPORT"),
    "vb365_version": os.getenv("VB365VERSION"),
}

backup_replication(env_config)
microsoft365(env_config)
