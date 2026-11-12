"""Print the AWS runtime .env built from the local .env.

Keeps provider keys and the demo password, generates fresh server secrets, and swaps
MinIO settings for the S3 bucket reached through the instance role.
Usage: DOMAIN=... FILES_BUCKET=... python3 deploy/aws/runtime_env.py .env
"""

import os
import secrets
import sys

DROP = {"S3_ENDPOINT", "S3_ACCESS_KEY", "S3_SECRET_KEY", "HAWLAK_AGENT_CONTROL_URL", "DATABASE_URL"}
GENERATE = {"INTERNAL_API_TOKEN", "HAWLAK_CONTROL_TOKEN", "POSTGRES_PASSWORD"}

domain, bucket = os.environ["DOMAIN"], os.environ["FILES_BUCKET"]
lines = []
for line in open(sys.argv[1], encoding="utf-8"):
    key = line.split("=", 1)[0].strip()
    if line.lstrip().startswith("#") or "=" not in line or key in DROP | GENERATE:
        continue
    lines.append(line.rstrip("\n"))

values = {key: secrets.token_urlsafe(32) for key in sorted(GENERATE)}
values |= {
    "PUBLIC_HOSTNAME": domain,
    "PUBLIC_BASE_URL": f"https://{domain}",
    "DASHBOARD_ORIGIN": f"https://{domain}",
    "S3_REGION": os.environ.get("AWS_REGION", "eu-north-1"),
    "S3_BUCKET": bucket,
}
lines = [line for line in lines if line.split("=", 1)[0] not in values]
print("\n".join(lines + [f"{key}={value}" for key, value in values.items()]))
