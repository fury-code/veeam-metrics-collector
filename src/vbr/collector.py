import requests
import urllib3
import pytz
import time
from datetime import datetime
import dateutil.parser
import influxdb_client
from influxdb_client.client.write_api import SYNCHRONOUS

urllib3.disable_warnings()


def backup_replication(env_config):
    """
    This function collects various metrics from the Veeam Backup & Replication Server and writes this data
    to an InfluxDB
    """
    vbr_base_url = (
        f'https://{env_config["vbr_backup_server"]}:{env_config["vbr_backup_port"]}/api'
    )

    def convert_to_datetime(timestamp_str):
        if timestamp_str is None:
            timezone = env_config["timezone"]
            timezone = pytz.timezone(timezone)
            now = datetime.now(timezone)
            timestamp_str = now.strftime("%Y-%m-%dT%H:%M:%S%z")
        try:
            return datetime.strptime(timestamp_str, "%Y-%m-%dT%H:%M:%S.%fZ")
        except ValueError:
            try:
                return datetime.strptime(timestamp_str, "%Y-%m-%dT%H:%M:%SZ")
            except ValueError:
                try:
                    # Handle the specific case with an extra period before 'Z'
                    return datetime.strptime(timestamp_str, "%Y-%m-%dT%H:%M:%S.Z")
                except ValueError:
                    # Handle the specific case with a timezone offset
                    return dateutil.parser.isoparse(timestamp_str)

    # Get bearer token for Veeam Backup & Replication
    token_url = f"{vbr_base_url}/oauth2/token"
    token_headers = {
        "accept": "application/json",
        "x-api-version": "1.1-rev1",
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

    # APIs configuration
    vbr_base_url = vbr_base_url + "/v1"
    vbr_headers = {
        "accept": "application/json",
        "x-api-version": "1.1-rev1",
        "Authorization": "Bearer " + access_token,
    }

    idb_client = influxdb_client.InfluxDBClient(
        url=env_config["influxdb_url"],
        token=env_config["influxdb_token"],
        org=env_config["influxdb_org"],
        verify_ssl=False,
    )
    write_api = idb_client.write_api(write_options=SYNCHRONOUS)

    # Veeam Backup & Replication Information. This part will check VBR Information
    info_url = f"{vbr_base_url}/serverInfo"
    response = requests.get(info_url, headers=vbr_headers, verify=False)
    data = response.json()

    vbr_id = data["vbrId"]
    vbr_name = data["name"]
    vbr_version = data["buildVersion"]
    vbr_database_vendor = data["databaseVendor"]

    p = (
        influxdb_client.Point("veeam_vbr_info")
        .tag("veeamVBRId", vbr_id)
        .tag("veeamVBRName", vbr_name)
        .tag("veeamVBRVersion", vbr_version)
        .tag("veeamVBR", env_config["vbr_backup_server"])
        .tag("veeamDatabaseVendor", vbr_database_vendor)
        .field("vbr", 1)
    )
    write_api.write(
        bucket=env_config["influxdb_bucket"], org=env_config["influxdb_org"], record=p
    )

    # Veeam Backup & Replication Sessions. This part will check VBR Sessions
    sessions_url = f"{vbr_base_url}/sessions?limit=1000"
    response = requests.get(sessions_url, headers=vbr_headers, verify=False)
    try:
        data = response.json()["data"]
    except KeyError:
        data = False

    if not data:
        print("There are no new veeam_vbr_sessions")
    else:
        for session in data:
            session_job_name = session["name"]
            session_type = session["sessionType"]
            session_job_state = session["state"]
            if session["result"] is None:
                continue
            else:
                session_job_result = session["result"]["result"]

            if session_job_result == "Success":
                job_status = 4
            elif session_job_result == "Warning":
                job_status = 3
            elif session_job_result == "Failed":
                job_status = 2
            else:
                # Others status
                job_status = 1

            session_job_result_message = session["result"]["message"]
            session_creation_time = convert_to_datetime(session["creationTime"])
            session_end_time = convert_to_datetime(session["endTime"])
            session_end_time_unix = int(time.mktime(session_end_time.timetuple()))
            session_time_duration = (
                session_end_time - session_creation_time
            ).total_seconds()

            p = (
                influxdb_client.Point("veeam_vbr_sessions")
                .tag("veeamVBR", env_config["vbr_backup_server"])
                .tag("veeamVBRSessionJobName", session_job_name)
                .tag("veeamVBRSessiontype", session_type)
                .tag("veeamVBRSessionJobState", session_job_state)
                .tag("veeamVBRSessionJobResultMessage", session_job_result_message)
                .field("veeamSessionJobResult", job_status)
                .field("veeamBackupSessionTimeDuration", session_time_duration)
                .time(session_end_time_unix, write_precision="s")
            )
            write_api.write(
                bucket=env_config["influxdb_bucket"],
                org=env_config["influxdb_org"],
                record=p,
            )

    # Veeam Backup & Replication Managed Servers. This part will check VBR Managed Servers.
    managed_servers_url = f"{vbr_base_url}/backupInfrastructure/managedServers"
    response = requests.get(managed_servers_url, headers=vbr_headers, verify=False)
    try:
        data = response.json()["data"]
    except KeyError:
        data = False

    num_servers = 0

    if not data:
        print("There are no managed servers")
    else:
        for server in data:
            server_name = server["name"]
            server_type = server["type"]
            server_description = server["description"]
            if not server_description:
                server_description = "None"

            p = (
                influxdb_client.Point("veeam_vbr_managedservers")
                .tag("veeamVBR", env_config["vbr_backup_server"])
                .tag("veeamVBRMSName", server_name)
                .tag("veeamVBRMStype", server_type)
                .tag("veeamVBRMSDescription", server_description)
                .field("veeamVBRMSInternalID", num_servers)
            )
            write_api.write(
                bucket=env_config["influxdb_bucket"],
                org=env_config["influxdb_org"],
                record=p,
            )

            num_servers += 1

    # Veeam Backup & Replication Repositories. This part will check VBR Repositories
    repository_url = f"{vbr_base_url}/backupInfrastructure/repositories"
    response = requests.get(repository_url, headers=vbr_headers, verify=False)
    try:
        data = response.json()["data"]
    except KeyError:
        data = False

    if not data:
        print("There are no repositories")
    else:
        for repo in data:
            repo_name = repo["name"]
            repo_type = repo["type"]
            repo_description = repo["description"]
            if not repo_description:
                repo_description = "None"

            repository_state_url = f"{repository_url}/states?idFilter={repo['id']}"
            state_response = requests.get(
                repository_state_url, headers=vbr_headers, verify=False
            )
            try:
                state_data = state_response.json()["data"][0]
            except KeyError:
                data = False
            repo_capacity = state_data["capacityGB"]
            repo_free = state_data["freeGB"]
            repo_used = state_data["usedSpaceGB"]

            if repo_type == "Nfs":
                repo_path = data["share"]["sharePath"]
                repo_per_vm = data["repository"]["advancedSettings"]["perVmBackup"]
                repo_max_tasks = data["repository"]["maxTaskCount"]

                p = (
                    influxdb_client.Point("veeam_vbr_repositories")
                    .tag("veeamVBRRepoName", repo_name)
                    .tag("veeamVBRRepotype", repo_type)
                    .tag("veeamVBRMSDescription", repo_description)
                    .tag("veeamVBRRepopath", repo_path)
                    .tag("veeamVBRRepoPerVM", repo_per_vm)
                    .field("veeamVBRRepoMaxtasks", repo_max_tasks)
                    .field("veeamVBRRepoCapacity", repo_capacity)
                    .field("veeamVBRRepoFree", repo_free)
                    .field("veeamVBRRepoUsed", repo_used)
                )
                write_api.write(
                    bucket=env_config["influxdb_bucket"],
                    org=env_config["influxdb_org"],
                    record=p,
                )

            else:
                p = (
                    influxdb_client.Point("veeam_vbr_repositories")
                    .tag("veeamVBRRepoName", repo_name)
                    .tag("veeamVBRRepotype", repo_type)
                    .tag("veeamVBRMSDescription", repo_description)
                    .field("veeamVBRRepoCapacity", repo_capacity)
                    .field("veeamVBRRepoFree", repo_free)
                    .field("veeamVBRRepoUsed", repo_used)
                )
                write_api.write(
                    bucket=env_config["influxdb_bucket"],
                    org=env_config["influxdb_org"],
                    record=p,
                )

    # Veeam Backup & Replication Proxies. This part will check VBR Proxies
    proxy_url = f"{vbr_base_url}/backupInfrastructure/proxies"
    response = requests.get(proxy_url, headers=vbr_headers, verify=False)
    try:
        data = response.json()["data"]
    except KeyError:
        data = False

    if not data:
        print("There are no proxies")
    else:
        for proxy in data:
            proxy_name = proxy["name"]
            proxy_type = proxy["type"]
            proxy_description = proxy["description"]
            if not proxy_description:
                proxy_description = "None"

            proxy_mode = proxy["server"]["transportMode"]
            proxy_task = proxy["server"]["maxTaskCount"]

            p = (
                influxdb_client.Point("veeam_vbr_proxies")
                .tag("veeamVBR", env_config["vbr_backup_server"])
                .tag("veeamVBRProxyName", proxy_name)
                .tag("veeamVBRProxytype", proxy_type)
                .tag("veeamVBRProxyDescription", proxy_description)
                .tag("veeamVBRProxyMode", proxy_mode)
                .field("veeamVBRProxyTask", proxy_task)
            )
            write_api.write(
                bucket=env_config["influxdb_bucket"],
                org=env_config["influxdb_org"],
                record=p,
            )

    # Veeam Backup & Replication Backup Objects. This part will check VBR Backup Objects
    objects_url = f"{vbr_base_url}/backupObjects"
    response = requests.get(objects_url, headers=vbr_headers, verify=False)
    try:
        data = response.json()["data"]
    except KeyError:
        data = False

    if not data:
        print("There are no objects")
    else:
        for obj in data:
            object_name = obj["name"]
            object_type = obj["type"]
            object_platform = obj["platformName"]
            object_vitype = obj["viType"]
            object_id = obj["objectId"]
            object_path = obj["path"]
            if not object_path:
                object_path = "None"
            object_rp_count = obj["restorePointsCount"]

            p = (
                influxdb_client.Point("veeam_vbr_backupobjects")
                .tag("veeamVBR", env_config["vbr_backup_server"])
                .tag("veeamVBRBobjectName", object_name)
                .tag("veeamVBRBobjecttype", object_type)
                .tag("veeamVBRBobjectPlatform", object_platform)
                .tag("veeamVBRBobjectviType", object_vitype)
                .tag("veeamVBRBobjectObjectId", object_id)
                .tag("veeamVBRBobjectPath", object_path)
                .field("restorePointsCount", object_rp_count)
            )
            write_api.write(
                bucket=env_config["influxdb_bucket"],
                org=env_config["influxdb_org"],
                record=p,
            )
