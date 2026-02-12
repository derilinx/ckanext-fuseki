import datetime
import json
import os
from io import BytesIO
from urllib.parse import urljoin, urlparse
import mimetypes
import logging

import requests
from requests_toolbelt.multipart.encoder import MultipartEncoder
from ckan import model
from ckan.common import config
from ckan.plugins.toolkit import get_action, asbool
from rq import get_current_job

from ckanext.fuseki import backend, db, helpers
from ckan.plugins.toolkit import get_action
from ckan import model

# --- Configuration ---
CKAN_URL = config.get("ckan.site_url", "http://localhost:5000")
FUSEKI_CKAN_TOKEN = os.environ.get("FUSEKI_CKAN_TOKEN", "")
SSL_VERIFY = asbool(os.environ.get("FUSEKI_SSL_VERIFY", True))
SPARQL_RES_NAME = "SPARQL"

if not SSL_VERIFY:
    requests.packages.urllib3.disable_warnings()


# --- Logging Handler ---
class StoringHandler(logging.Handler):
    """Store logs in database for job tracking."""
    def __init__(self, task_id, job_dict):
        super().__init__()
        self.task_id = task_id
        self.job_dict = job_dict

    def emit(self, record):
        conn = db.ENGINE.connect()
        try:
            conn.execute(
                db.LOGS_TABLE.insert().values(
                    job_id=self.task_id,
                    timestamp=datetime.datetime.utcnow(),
                    message=str(record.getMessage()),
                    level=str(record.levelname),
                    module=str(record.module),
                    funcName=str(record.funcName),
                    lineno=record.lineno,
                )
            )
        finally:
            conn.close()


# --- JSON encoder ---
class DatetimeJsonEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            return obj.isoformat()
        return super().default(obj)


# --- CKAN helpers ---
def resource_search(dataset_id, res_name):
    local_ckan = get_action("package_show")({"ignore_auth": True}, {"id": dataset_id})
    for res in local_ckan["resources"]:
        if res["name"] == res_name:
            return res
    return None


def callback_fuseki_hook(result_url, job_dict):
    """Send job status to callback URL."""
    headers = {
        "Authorization": FUSEKI_CKAN_TOKEN,
        "Content-Type": "application/json",
    }
    try:
        result = requests.post(
            result_url,
            data=json.dumps(job_dict, cls=DatetimeJsonEncoder),
            headers=headers,
            verify=SSL_VERIFY,
        )
        return result.status_code == 200
    except requests.ConnectionError:
        return False


# --- Upload a SPARQL link resource ---
from ckan.plugins.toolkit import get_action
from ckan import model

def upload_link(dataset_id, link_url):
    """
    Create or update SPARQL link using CKAN internal action API.
    No HTTP. No API key. No headers.
    """

    context = {
        "model": model,
        "session": model.Session,
        "user": "admin",        # must be a sysadmin user
        "ignore_auth": False,
    }

    # Check if resource already exists
    pkg = get_action("package_show")(context, {"id": dataset_id})
    existing = None
    for r in pkg["resources"]:
        if r["name"] == "SPARQL":
            existing = r
            break

    data = {
        "package_id": dataset_id,
        "url": link_url,
        "name": "SPARQL",
        "format": "SPARQL",
        "mimetype": "text/html",
    }

    if existing:
        data["id"] = existing["id"]
        return get_action("resource_patch")(context, data)
    else:
        return get_action("resource_create")(context, data)



# --- Upload a file resource ---
def file_upload(dataset_id, filename, filedata, res_id=None, format=""):
    """
    Uploads a file to CKAN, automatically detects MIME type.
    """
    mime_type, _ = mimetypes.guess_type(filename)
    if mime_type is None:
        mime_type = "application/octet-stream"

    data_stream = BytesIO(filedata)

    fields = {"upload": (filename, data_stream, mime_type)}
    if res_id:
        fields["id"] = res_id
        url = f"{CKAN_URL.rstrip('/')}/api/3/action/resource_patch"
    else:
        fields.update({"package_id": dataset_id, "name": filename, "format": format})
        url = f"{CKAN_URL.rstrip('/')}/api/3/action/resource_create"

    mp_encoder = MultipartEncoder(fields=fields)
    headers = {
        "Authorization": FUSEKI_CKAN_TOKEN,
        "Content-Type": mp_encoder.content_type,
    }

    response = requests.post(url, headers=headers, data=mp_encoder, verify=SSL_VERIFY)
    response.raise_for_status()
    return response.json()


# --- Main update function ---
def update(dataset_name, dataset_id, res_ids, callback_url, last_updated,
           persistant=False, reasoning=False, reasoner="", unionDefaultGraph=False):
    context = {"session": model.meta.create_local_session(), "ignore_auth": True}
    dataset_url = f"{CKAN_URL}/dataset/{dataset_name}"

    metadata = {
        "ckan_url": CKAN_URL,
        "pkg_id": dataset_id,
        "resource_ids": res_ids,
        "task_created": last_updated,
        "original_url": dataset_url,
        "persistant": persistant,
        "reasoning": reasoning,
        "reasoner": reasoner,
    }

    job_info = {}
    job_dict = {"metadata": metadata, "status": "running", "job_info": job_info}
    job_id = get_current_job().id
    errored = False
    db.init()

    # Logging
    logger = logging.getLogger(job_id)
    handler = StoringHandler(job_id, job_dict)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.addHandler(logging.StreamHandler())
    logger.setLevel(logging.DEBUG)

    callback_fuseki_hook(callback_url, job_dict)

    _graph = backend.get_graph(dataset_id)
    if not _graph:
        _graph = backend.graph_create(dataset_url, dataset_id, persistant, reasoning, reasoner)

    for res_id in res_ids:
        _res = get_action("resource_show")(context, {"id": res_id})
        try:
            backend.resource_upload(_res, _graph)
        except Exception as e:
            logger.error(f"Upload {_res['url']} failed: {e}")
            errored = True
        else:
            logger.info(f"Upload {_res['url']} successfull to {_graph}")

    pkg_dict = get_action("package_show")(context, {"id": dataset_id})
    sparql_url = helpers.fuseki_sparql_url(pkg_dict)
    try:
        upload_link(dataset_id, sparql_url)
        logger.info(f"SPARQL link added: {sparql_url}")
    except Exception as e:
        logger.error(f"Failed to add SPARQL link: {e}")
        errored = True

    job_dict["status"] = "complete"
    callback_fuseki_hook(callback_url, job_dict)
    return "error" if errored else None
