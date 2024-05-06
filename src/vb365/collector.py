import requests
import urllib3
import pytz
import time
from datetime import datetime
import influxdb_client
from influxdb_client.client.write_api import SYNCHRONOUS

urllib3.disable_warnings()


def microsoft365(env_config):
    """
    This function collects various metrics from the Veeam Backup for Microsoft 365 and writes this data
    to an InfluxDB
    """

    def convert_to_datetime(timestamp_str):
        timestamp_str = timestamp_str[:-4] + timestamp_str[-1]
        if timestamp_str is None:
            timezone = env_config["timezone"]
            timezone = pytz.timezone(timezone)
            now = datetime.now(timezone)
            timestamp_str = now.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        try:
            return datetime.strptime(timestamp_str, "%Y-%m-%dT%H:%M:%S.%fZ")
        except ValueError:
            return datetime.strptime(timestamp_str, "%Y-%m-%dT%H:%M:%SZ")

    vb365_base_url = (
        f'https://{env_config["vb365_rest_server"]}:{env_config["vb365_rest_port"]}/v7'
    )

    # Get Bearer token
    token_url = f"{vb365_base_url}/token"
    token_headers = {
        "accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {
        "grant_type": "password",
        "username": env_config["veeam_username"],
        "password": env_config["veeam_password"],
    }

    response = requests.post(token_url, headers=token_headers, data=data, verify=False)
    status_code = response.status_code

    access_token = ""
    if status_code == 200:
        access_token = response.json()["access_token"]
    else:
        print("An error has occured")

    vb365_headers = {
        "accept": "application/json",
        "Authorization": "Bearer " + access_token,
    }

    idb_client = influxdb_client.InfluxDBClient(
        url=env_config["influxdb_url"],
        token=env_config["influxdb_token"],
        org=env_config["influxdb_org"],
        verify_ssl=False,
    )
    write_api = idb_client.write_api(write_options=SYNCHRONOUS)

    # Veeam Backup for Microsoft 365 Version. This part will check the Veeam Backup for Microsoft 365 version
    service_url = f"{vb365_base_url}/ServiceInstance"
    response = requests.get(service_url, headers=vb365_headers, verify=False)
    data = response.json()

    vb365_version = data["version"]

    p = (
        influxdb_client.Point("veeam_office365_version")
        .tag("veeamVersion", vb365_version)
        .tag("veeamServer", env_config["vb365_rest_server"])
        .field("v", 1)
    )

    write_api.write(
        bucket=env_config["influxdb_bucket"], org=env_config["influxdb_org"], record=p
    )

    # Veeam Backup for Microsoft 365 Organization. This part will check on our Organization and retrieve Licensing Information
    organization_url = f"{vb365_base_url}/Organizations"
    response = requests.get(organization_url, headers=vb365_headers, verify=False)
    data = response.json()

    for org in data:
        org_id = org["id"]
        org_name = org["name"]

        # Licensing
        license_url = f"{organization_url}/{org_id}/LicensingInformation"
        license_response = requests.get(
            license_url, headers=vb365_headers, verify=False
        )
        license_data = license_response.json()

        licensed_users = license_data["licensedUsers"]
        new_users = license_data["newUsers"]

        p = (
            influxdb_client.Point("veeam_office365_organization")
            .tag("veeamOrgName", org_name)
            .field("licensedUsers", licensed_users)
            .field("newUsers", new_users)
        )

        write_api.write(
            bucket=env_config["influxdb_bucket"],
            org=env_config["influxdb_org"],
            record=p,
        )

        # Veeam Backup for Microsoft 365 Users. This part will check the total Users and if they are protected or not
        licensed_users_url = f"{vb365_base_url}/LicensedUsers"
        response = requests.get(licensed_users_url, headers=vb365_headers, verify=False)
        data = response.json()["results"]

        while "next" in response.json()["_links"]:
            next_url = f'https://{env_config["vb365_rest_server"]}:{env_config["vb365_rest_port"]}{response.json()["_links"]["next"]["href"]}'
            response = requests.get(next_url, headers=vb365_headers, verify=False)
            data.extend(response.json()["results"])

        for user in data:
            user_name = user["name"]
            user_backup = user["isBackedUp"]

            if user_backup:
                protected_user = 1
            else:
                protected_user = 2

            licensed_state = user["licenseState"]

            if licensed_state == "Licensed":
                licensed_user = 1
            elif licensed_state == "Unlicensed":
                licensed_user = 2

            p = (
                influxdb_client.Point("veeam_office365_overview_OD")
                .tag("veeamOrgName", org_name)
                .tag("veeamUserName", user_name)
                .field("protectedUser", protected_user)
                .field("licensedUser", licensed_user)
            )

            write_api.write(
                bucket=env_config["influxdb_bucket"],
                org=env_config["influxdb_org"],
                record=p,
            )

    # Veeam Backup for Microsoft 365 Backup Repositories. This part will check the capacity and used space of the Backup Repositories

    repo_url = f"{vb365_base_url}/BackupRepositories"
    response = requests.get(repo_url, headers=vb365_headers, verify=False)
    data = response.json()

    for repo in data:
        repository = repo["name"]
        capacity = repo["capacityBytes"]
        free_space = repo["freeSpaceBytes"]

        # Veeam Backup for Microsoft 365 Object Storage Repositories. This part will check the capacity and used space of the Object Storage Repositories
        # Object storage not implemented

        p = (
            influxdb_client.Point("veeam_office365_repository")
            .tag("repository", repository)
            .field("capacity", capacity)
            .field("freeSpace", free_space)
        )

        write_api.write(
            bucket=env_config["influxdb_bucket"],
            org=env_config["influxdb_org"],
            record=p,
        )

    # Veeam Backup for Microsoft 365 Backup Proxies. This part will check the Name and Threads Number of the Backup Proxies
    proxy_url = f"{vb365_base_url}/Proxies?extendedView=true"
    response = requests.get(proxy_url, headers=vb365_headers, verify=False)
    data = response.json()

    for proxy in data:
        hostname = proxy["hostName"]
        status = proxy["status"]
        threads_number = proxy["threadsNumber"]

        p = (
            influxdb_client.Point("veeam_office365_proxies")
            .tag("proxies", hostname)
            .tag("status", status)
            .field("threadsNumber", threads_number)
        )

        write_api.write(
            bucket=env_config["influxdb_bucket"],
            org=env_config["influxdb_org"],
            record=p,
        )

    # Veeam Backup for Microsoft 365 Backup Jobs. This part will check the different Jobs, and the Job Sessions per every Job
    jobs_url = f"{vb365_base_url}/Jobs"
    response = requests.get(jobs_url, headers=vb365_headers, verify=False)
    data = response.json()

    for job in data:
        job_name = job["name"]
        job_id = job["id"]

        session_url = f"{vb365_base_url}/JobSessions?jobId={job_id}"
        session_response = requests.get(
            session_url, headers=vb365_headers, verify=False
        )
        session_data = session_response.json()["results"]

        while "next" in session_response.json()["_links"]:
            next_url = f'https://{env_config["vb365_rest_server"]}:{env_config["vb365_rest_port"]}{session_response.json()["_links"]["next"]["href"]}'
            session_response = requests.get(
                next_url, headers=vb365_headers, verify=False
            )
            session_data.extend(session_response.json()["results"])

        for session in session_data[:1000]:
            session_status = session["status"]

            if not session_status == "Running":
                creation_time = convert_to_datetime(session["creationTime"])
                end_time = convert_to_datetime(session["endTime"])
                end_time_unix = int(time.mktime(end_time.timetuple()))
                session_time_duration = (end_time - creation_time).total_seconds()

                if session_status == "Success":
                    session_status = 4
                elif session_status == "Warning":
                    session_status = 3
                elif session_status == "Failed":
                    session_status = 2
                else:
                    # Other status
                    session_status = 1

                processing_rate = session["statistics"]["processingRateBytesPS"]
                read_rate = session["statistics"]["readRateBytesPS"]
                write_rate = session["statistics"]["writeRateBytesPS"]
                transferred_data = session["statistics"]["transferredDataBytes"]
                processed_objects = session["statistics"]["processedObjects"]
                bottleneck = session["statistics"]["bottleneck"]

                p = (
                    influxdb_client.Point("veeam_office365_jobs")
                    .tag("veeamServer", env_config["vb365_rest_server"])
                    .tag("veeamjobname", job_name)
                    .tag("bottleneck", bottleneck)
                    .field("totalDuration", session_time_duration)
                    .field("status", session_status)
                    .field("processingRate", processing_rate)
                    .field("readRate", read_rate)
                    .field("writeRate", write_rate)
                    .field("transferredData", transferred_data)
                    .field("processedObjects", processed_objects)
                    .time(end_time_unix, write_precision="s")
                )

                write_api.write(
                    bucket=env_config["influxdb_bucket"],
                    org=env_config["influxdb_org"],
                    record=p,
                )

    # Veeam Backup for Microsoft 365 Restore Portal. This part will check the if Restore Portal is enabled
    # not implemented

    # Veeam Backup for Microsoft 365 RBAC Roles. This part will check the the RBAC Roles, and what privileges they have
    # not implemented
