import hashlib
import json
import logging
import os
from datetime import datetime, timedelta, timezone

import azure.functions as func
from azure.core.exceptions import ResourceNotFoundError
from azure.data.tables import TableServiceClient, UpdateMode
from azure.identity import DefaultAzureCredential

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

TABLE_NAME = "VisitorCounter"
PARTITION_KEY = "counter"
ROW_KEY = "1"

# trigger rebuild

DEDUPE_WINDOW_SECONDS = 1800  # 30 minutes


def _get_table_client():
    endpoint = os.environ["COSMOS_TABLE_ENDPOINT"]
    credential = DefaultAzureCredential()
    service_client = TableServiceClient(endpoint=endpoint, credential=credential)
    return service_client.get_table_client(TABLE_NAME)


def _get_client_ip(req: func.HttpRequest) -> str:
    forwarded_for = req.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return req.headers.get("X-Azure-ClientIP", "unknown")


def _hash_ip(ip: str) -> str:
    return hashlib.sha256(ip.encode("utf-8")).hexdigest()


def increment_visitor_count(table_client) -> int:
    try:
        entity = table_client.get_entity(partition_key=PARTITION_KEY, row_key=ROW_KEY)
        new_count = int(entity["count"]) + 1
        entity["count"] = new_count
        table_client.update_entity(entity, mode=UpdateMode.MERGE)
    except ResourceNotFoundError:
        new_count = 1
        table_client.create_entity({
            "PartitionKey": PARTITION_KEY,
            "RowKey": ROW_KEY,
            "count": new_count,
        })
    return new_count


def get_current_count(table_client) -> int:
    try:
        entity = table_client.get_entity(partition_key=PARTITION_KEY, row_key=ROW_KEY)
        return int(entity["count"])
    except ResourceNotFoundError:
        return 0


def has_visited_recently(table_client, ip_hash: str) -> bool:
    try:
        session_entity = table_client.get_entity(partition_key="session", row_key=ip_hash)
    except ResourceNotFoundError:
        return False

    last_seen_str = session_entity.get("last_seen")
    if not last_seen_str:
        return False

    last_seen = datetime.fromisoformat(last_seen_str)
    elapsed = datetime.now(timezone.utc) - last_seen
    return elapsed < timedelta(seconds=DEDUPE_WINDOW_SECONDS)


def record_visit(table_client, ip_hash: str) -> None:
    table_client.upsert_entity({
        "PartitionKey": "session",
        "RowKey": ip_hash,
        "last_seen": datetime.now(timezone.utc).isoformat(),
    })


@app.route(route="counter", methods=["GET"])
def counter(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Visitor counter function triggered.")
    try:
        table_client = _get_table_client()
        ip_hash = _hash_ip(_get_client_ip(req))

        if has_visited_recently(table_client, ip_hash):
            current_count = get_current_count(table_client)
            return func.HttpResponse(
                json.dumps({"count": current_count}),
                status_code=200,
                mimetype="application/json",
            )

        new_count = increment_visitor_count(table_client)
        record_visit(table_client, ip_hash)

        return func.HttpResponse(
            json.dumps({"count": new_count}),
            status_code=200,
            mimetype="application/json",
        )
    except Exception as exc:
        logging.exception("Failed to update visitor counter: %s", exc)
        return func.HttpResponse(
            json.dumps({"error": "Unable to update visitor counter"}),
            status_code=500,
            mimetype="application/json",
        )