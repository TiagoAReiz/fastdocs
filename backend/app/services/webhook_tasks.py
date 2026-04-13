import hashlib
import hmac
import json
import logging

import requests

from app.core.celery_app import celery_app

log = logging.getLogger(__name__)


@celery_app.task(
    name="app.services.webhook_tasks.send_webhook",
    bind=True,
    max_retries=3,
    autoretry_for=(requests.RequestException,),
    retry_backoff=True,
    retry_backoff_max=30,
)
def send_webhook(
    self,
    webhook_url: str,
    webhook_secret: str | None,
    payload: dict,
) -> dict:
    body = json.dumps(payload, sort_keys=True)
    headers = {"Content-Type": "application/json"}

    if webhook_secret:
        signature = hmac.new(
            webhook_secret.encode(), body.encode(), hashlib.sha256
        ).hexdigest()
        headers["X-FastDocs-Signature"] = f"sha256={signature}"

    log.info("sending webhook to %s (attempt %d)", webhook_url, self.request.retries + 1)
    resp = requests.post(webhook_url, data=body, headers=headers, timeout=10)
    resp.raise_for_status()

    return {"status": resp.status_code}
