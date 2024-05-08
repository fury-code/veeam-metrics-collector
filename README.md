# Grafana Dashboards

# Veeam Backup Metrics Collector
This is a metrics collector written in Python which queries data from 
Veeam backup solutions and writes it to InfluxDB.

This project is inspired by another project from [Jorge de la Cruz](https://github.com/jorgedlcruz/veeam-backup-for-microsoft365-grafana).

## Getting started
You can use the default container image from this repository.
```bash
docker pull ghcr.io/fury-code/veeam-metrics-collector:latest
```

You can configure your experience with the following environment variables.
```
INFLUXDBURL=
INFLUXDBBUCKET=
INFLUXDBTOKEN=
INFLUXDBORG=
VEEAMUSERNAME=
VEEAMPASSWORD=
VBRBACKUPSERVER=
VBRBACKUPPORT=
VB365RESTSERVER=
VB365RESTPORT=
SENTRY_DSN_KEY=
TZ=
```

### Sentry
If you are using [Sentry](https://sentry.io/welcome/) in your organization 
then you can enable it with the `SENTRY_DSN_KEY` variable. If not, just 
leave it empty the disable the functionality.

## Feedback
If you have feedback don't hesitate to create an issue or improve this 
code base with a pull request.

