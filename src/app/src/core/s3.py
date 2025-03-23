"""S3 module for handling file operations in AWS S3."""

import os
from typing import List, Tuple

import boto3
from botocore.exceptions import ClientError
from mypy_boto3_s3.client import S3Client


class S3Handler:
    """Handler for S3 operations related to knowledge base files."""

    def __init__(self) -> None:
        """Initialize the S3 handler with AWS configuration."""
        self.session = boto3.session.Session(region_name=os.getenv("BEDROCK_REGION", "us-east-1"))
        self.s3_client: S3Client = self.session.client("s3", region_name=os.getenv("BEDROCK_REGION", "us-east-1"))
        self.bucket_name = os.getenv("RAG_BUCKET", "multi-agent-blueprint-bedrock-rag")

    def list_files(self) -> List[Tuple[str, int]]:
        """List all files in the knowledge base directory."""
        try:
            response = self.s3_client.list_objects_v2(Bucket=self.bucket_name, Prefix="knowledgeBase/")
            files = []
            for obj in response.get("Contents", []):
                if obj.get("Key") and obj.get("Size") is not None:
                    files.append((obj["Key"], obj["Size"]))
            return sorted(files)
        except ClientError:
            return []

    def get_download_url(self, file_key: str) -> str:
        """Generate a presigned URL for downloading a file."""
        try:
            url = self.s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": file_key},
                ExpiresIn=3600,
            )
            return url
        except ClientError:
            return ""
