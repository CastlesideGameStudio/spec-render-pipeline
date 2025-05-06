#!/usr/bin/env python3
"""
Delete EVERY object (and every version, if versioning is enabled) from a
Linode Object-Storage bucket.

Required environment variables
  BUCKET                    bucket name, e.g. castlesidegamestudio-spec-sheets
  LINODE_S3_ENDPOINT        us-east-1.linodeobjects.com   (or region of bucket)
  AWS_ACCESS_KEY_ID         your Linode access key
  AWS_SECRET_ACCESS_KEY     your Linode secret key

Optional environment variables
  DRY_RUN=1                 list what would be deleted but do nothing
  PREFIX=foo/bar/           limit wipe to keys under that prefix
"""

from __future__ import annotations
import os
import sys
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

# -------- configuration from env ------------------------------------------
BUCKET = os.getenv("BUCKET")
ENDPT  = os.getenv("LINODE_S3_ENDPOINT")
KEY    = os.getenv("AWS_ACCESS_KEY_ID")
SEC    = os.getenv("AWS_SECRET_ACCESS_KEY")
PREFIX = os.getenv("PREFIX", "")
DRY    = os.getenv("DRY_RUN", "0") == "1"

for v in ("BUCKET", "LINODE_S3_ENDPOINT",
          "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
    if not os.getenv(v):
        sys.exit(f"ERROR: env {v} is required")

# -------- boto3 client -----------------------------------------------------
session = boto3.session.Session()
s3 = session.client(
    "s3",
    endpoint_url=f"https://{ENDPT}",
    aws_access_key_id=KEY,
    aws_secret_access_key=SEC,
    region_name="us-east-1",
    config=Config(signature_version="s3v4"),
)

def delete_batch(items: list[dict]) -> None:
    if DRY:
        for obj in items:
            print("DRY_RUN", obj)
        return
    resp = s3.delete_objects(Bucket=BUCKET, Delete={"Objects": items})
    for d in resp.get("Deleted", []):
        print("deleted", d.get("Key"), d.get("VersionId", ""))

# -------- main -------------------------------------------------------------
def main() -> None:
    paginator = s3.get_paginator("list_object_versions")
    pages = paginator.paginate(Bucket=BUCKET, Prefix=PREFIX)
    batch: list[dict] = []
    total = 0

    for page in pages:
        for obj in page.get("Versions", []) + page.get("DeleteMarkers", []):
            batch.append({"Key": obj["Key"], "VersionId": obj["VersionId"]})
            if len(batch) == 1000:
                delete_batch(batch)
                total += len(batch)
                batch.clear()

    if batch:
        delete_batch(batch)
        total += len(batch)

    verb = "Would delete" if DRY else "Deleted"
    print(f"{verb} {total} object versions from {BUCKET}")

if __name__ == "__main__":
    main()
