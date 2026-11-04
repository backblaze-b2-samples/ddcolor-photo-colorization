"""A tiny in-memory stand-in for the boto3 S3 client used by the repo layer.

Tests patch it in at the `get_s3_client` seam, so every repo module (record
store, object I/O, presign) runs its real code against an in-memory bucket.
"""

import hashlib
from datetime import UTC, datetime
from io import BytesIO

from botocore.exceptions import ClientError


def _missing(op: str) -> ClientError:
    return ClientError({"Error": {"Code": "NoSuchKey", "Message": "missing"}}, op)


class FakeS3:
    def __init__(self) -> None:
        self.objects: dict[str, dict] = {}

    def add(self, key: str, data: bytes, content_type: str = "application/octet-stream"):
        self.put_object(Bucket="b", Key=key, Body=data, ContentType=content_type)

    def put_object(self, *, Bucket, Key, Body, ContentType="application/octet-stream"):
        data = Body if isinstance(Body, bytes) else Body.read()
        self.objects[Key] = {
            "Body": data,
            "ContentType": ContentType,
            "LastModified": datetime.now(UTC),
            "ETag": hashlib.md5(data, usedforsecurity=False).hexdigest(),
        }
        return {}

    def get_object(self, *, Bucket, Key, Range=None):
        if Key not in self.objects:
            raise _missing("GetObject")
        return {"Body": BytesIO(self.objects[Key]["Body"])}

    def head_object(self, *, Bucket, Key):
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "404", "Message": "nf"}}, "HeadObject")
        obj = self.objects[Key]
        return {
            "ContentLength": len(obj["Body"]),
            "ContentType": obj["ContentType"],
            "LastModified": obj["LastModified"],
        }

    def list_objects_v2(self, *, Bucket, Prefix="", MaxKeys=1000, ContinuationToken=None):
        contents = [
            {
                "Key": k,
                "Size": len(v["Body"]),
                "LastModified": v["LastModified"],
                "ETag": v["ETag"],
            }
            for k, v in sorted(self.objects.items())
            if k.startswith(Prefix)
        ]
        return {"Contents": contents, "IsTruncated": False}

    def delete_objects(self, *, Bucket, Delete):
        deleted = []
        for entry in Delete["Objects"]:
            if self.objects.pop(entry["Key"], None) is not None:
                deleted.append({"Key": entry["Key"]})
        return {"Deleted": deleted}

    def delete_object(self, *, Bucket, Key):
        self.objects.pop(Key, None)

    def generate_presigned_url(self, op, Params, ExpiresIn):
        return f"https://signed.example/{op}/{Params['Key']}?ttl={ExpiresIn}"
