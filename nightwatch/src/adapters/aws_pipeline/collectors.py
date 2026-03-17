"""
AWS Pipeline Collectors
========================
Low-level AWS data collectors for the Bayer ModelN.io pipeline.

Each collector is a standalone function that takes boto3 clients
and returns structured data. Keeping collection separate from
health check logic makes testing and extension easier.

Author: Nova ⚡ | Nightwatch Platform
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import boto3
from botocore.exceptions import ClientError, BotoCoreError

log = logging.getLogger("nightwatch.aws_pipeline.collectors")


# ─── Step Functions ───────────────────────────────────────────────────────────

def collect_step_function_status(sfn_client, state_machine_arns: list[str]) -> dict:
    """
    Collect recent execution status for each state machine.

    Returns:
        {
            "<arn>": {
                "name": str,
                "latest_execution": {"status": str, "started_at": str, "duration_seconds": float},
                "recent_executions": [{"status": str, "started_at": str}],
                "running_count": int,
                "failed_count_24h": int,
            }
        }
    """
    result = {}

    for arn in state_machine_arns:
        try:
            # Get recent executions (last 20)
            response = sfn_client.list_executions(
                stateMachineArn=arn,
                maxResults=20,
            )
            executions = response.get("executions", [])

            if not executions:
                result[arn] = {"name": _arn_name(arn), "latest_execution": None, "running_count": 0, "failed_count_24h": 0}
                continue

            # Analyze executions
            running = [e for e in executions if e["status"] == "RUNNING"]
            now = datetime.now(timezone.utc)
            cutoff = now - timedelta(hours=24)
            recent_failed = [
                e for e in executions
                if e["status"] in ("FAILED", "TIMED_OUT", "ABORTED")
                and e.get("startDate", now) > cutoff
            ]

            latest = executions[0]
            duration = None
            if latest.get("stopDate") and latest.get("startDate"):
                duration = (latest["stopDate"] - latest["startDate"]).total_seconds()

            result[arn] = {
                "name": _arn_name(arn),
                "arn": arn,
                "latest_execution": {
                    "status": latest["status"],
                    "started_at": latest["startDate"].isoformat() if latest.get("startDate") else None,
                    "stopped_at": latest.get("stopDate", {}).isoformat() if latest.get("stopDate") else None,
                    "duration_seconds": duration,
                },
                "running_count": len(running),
                "failed_count_24h": len(recent_failed),
                "recent_statuses": [e["status"] for e in executions[:5]],
            }

        except (ClientError, BotoCoreError) as e:
            log.error("sfn_collect_error", arn=arn, error=str(e))
            result[arn] = {"name": _arn_name(arn), "error": str(e)}

    return result


# ─── Glue Jobs ────────────────────────────────────────────────────────────────

def collect_glue_job_status(glue_client, job_names: list[str]) -> dict:
    """
    Collect recent run status for each Glue job.

    Returns:
        {
            "<job_name>": {
                "latest_run": {"job_run_state": str, "started_on": str, "duration_seconds": float, "error_message": str},
                "consecutive_failures": int,
                "avg_duration_7d_seconds": float,
            }
        }
    """
    result = {}

    for job_name in job_names:
        try:
            response = glue_client.get_job_runs(JobName=job_name, MaxResults=10)
            runs = response.get("JobRuns", [])

            if not runs:
                result[job_name] = {"latest_run": None, "consecutive_failures": 0}
                continue

            latest = runs[0]
            duration = latest.get("ExecutionTime")  # seconds
            error_msg = latest.get("ErrorMessage", "")

            # Count consecutive failures
            consecutive = 0
            for run in runs:
                if run["JobRunState"] in ("FAILED", "ERROR", "TIMEOUT"):
                    consecutive += 1
                else:
                    break

            # Average duration over last 7 days (successful runs only)
            now = datetime.now(timezone.utc)
            cutoff = now - timedelta(days=7)
            successful_runs = [
                r for r in runs
                if r["JobRunState"] in ("SUCCEEDED",)
                and r.get("StartedOn", now) > cutoff
                and r.get("ExecutionTime")
            ]
            avg_duration = (
                sum(r["ExecutionTime"] for r in successful_runs) / len(successful_runs)
                if successful_runs else None
            )

            result[job_name] = {
                "job_name": job_name,
                "latest_run": {
                    "job_run_state": latest["JobRunState"],
                    "started_on": latest.get("StartedOn", "").isoformat() if latest.get("StartedOn") else None,
                    "duration_seconds": duration,
                    "error_message": error_msg[:500] if error_msg else None,
                    "dpu_seconds": latest.get("DPUSeconds"),
                },
                "consecutive_failures": consecutive,
                "avg_duration_7d_seconds": avg_duration,
                "recent_states": [r["JobRunState"] for r in runs[:5]],
            }

        except (ClientError, BotoCoreError) as e:
            log.error("glue_collect_error", job=job_name, error=str(e))
            result[job_name] = {"job_name": job_name, "error": str(e)}

    return result


# ─── S3 Buckets ───────────────────────────────────────────────────────────────

def collect_s3_bucket_stats(s3_client, buckets_config: dict) -> dict:
    """
    Collect object count, size, and freshness for S3 bucket/prefix combinations.

    Args:
        buckets_config: {"bucket_name": ["prefix1", "prefix2"]} or {"bucket_name": "prefix"}

    Returns:
        {
            "<bucket>/<prefix>": {
                "object_count": int,
                "total_size_bytes": int,
                "last_modified_age_seconds": float,
                "newest_object": str,
            }
        }
    """
    result = {}
    now = datetime.now(timezone.utc)

    for bucket, prefixes in buckets_config.items():
        if isinstance(prefixes, str):
            prefixes = [prefixes]

        for prefix in prefixes:
            key = f"{bucket}/{prefix}" if prefix else bucket
            try:
                paginator = s3_client.get_paginator("list_objects_v2")
                pages = paginator.paginate(Bucket=bucket, Prefix=prefix)

                objects = []
                for page in pages:
                    objects.extend(page.get("Contents", []))

                if not objects:
                    result[key] = {
                        "bucket": bucket,
                        "prefix": prefix,
                        "object_count": 0,
                        "total_size_bytes": 0,
                        "last_modified_age_seconds": None,
                        "newest_object": None,
                    }
                    continue

                newest = max(objects, key=lambda o: o["LastModified"])
                age_seconds = (now - newest["LastModified"]).total_seconds()
                total_size = sum(o["Size"] for o in objects)

                result[key] = {
                    "bucket": bucket,
                    "prefix": prefix,
                    "object_count": len(objects),
                    "total_size_bytes": total_size,
                    "last_modified_age_seconds": age_seconds,
                    "newest_object": newest["Key"],
                }

            except (ClientError, BotoCoreError) as e:
                log.error("s3_collect_error", bucket=bucket, prefix=prefix, error=str(e))
                result[key] = {"bucket": bucket, "prefix": prefix, "error": str(e)}

    return result


# ─── Lambda ───────────────────────────────────────────────────────────────────

def collect_lambda_errors(cloudwatch_client, function_names: list[str], lookback_minutes: int = 60) -> dict:
    """
    Collect Lambda error rates via CloudWatch metrics.

    Returns:
        {
            "<function_name>": {
                "errors_1h": int,
                "invocations_1h": int,
                "error_rate": float,
                "throttles_1h": int,
            }
        }
    """
    result = {}
    now = datetime.now(timezone.utc)
    start_time = now - timedelta(minutes=lookback_minutes)

    for func_name in function_names:
        try:
            metrics = {}
            for metric_name in ["Errors", "Invocations", "Throttles"]:
                response = cloudwatch_client.get_metric_statistics(
                    Namespace="AWS/Lambda",
                    MetricName=metric_name,
                    Dimensions=[{"Name": "FunctionName", "Value": func_name}],
                    StartTime=start_time,
                    EndTime=now,
                    Period=lookback_minutes * 60,
                    Statistics=["Sum"],
                )
                datapoints = response.get("Datapoints", [])
                metrics[metric_name] = sum(dp["Sum"] for dp in datapoints)

            invocations = metrics.get("Invocations", 0)
            errors = metrics.get("Errors", 0)
            error_rate = (errors / invocations) if invocations > 0 else 0.0

            result[func_name] = {
                "function_name": func_name,
                "errors_1h": int(errors),
                "invocations_1h": int(invocations),
                "error_rate": round(error_rate, 4),
                "throttles_1h": int(metrics.get("Throttles", 0)),
            }

        except (ClientError, BotoCoreError) as e:
            log.error("lambda_collect_error", function=func_name, error=str(e))
            result[func_name] = {"function_name": func_name, "error": str(e)}

    return result


# ─── DynamoDB ─────────────────────────────────────────────────────────────────

def collect_dynamodb_metrics(cloudwatch_client, table_names: list[str], lookback_minutes: int = 60) -> dict:
    """
    Collect DynamoDB read/write capacity and throttling metrics.
    """
    result = {}
    now = datetime.now(timezone.utc)
    start_time = now - timedelta(minutes=lookback_minutes)

    for table_name in table_names:
        try:
            metrics = {}
            for metric_name in ["ConsumedReadCapacityUnits", "ConsumedWriteCapacityUnits",
                                 "ReadThrottleEvents", "WriteThrottleEvents"]:
                response = cloudwatch_client.get_metric_statistics(
                    Namespace="AWS/DynamoDB",
                    MetricName=metric_name,
                    Dimensions=[{"Name": "TableName", "Value": table_name}],
                    StartTime=start_time,
                    EndTime=now,
                    Period=lookback_minutes * 60,
                    Statistics=["Sum"],
                )
                datapoints = response.get("Datapoints", [])
                metrics[metric_name] = sum(dp["Sum"] for dp in datapoints)

            result[table_name] = {
                "table_name": table_name,
                "read_capacity_consumed": metrics.get("ConsumedReadCapacityUnits", 0),
                "write_capacity_consumed": metrics.get("ConsumedWriteCapacityUnits", 0),
                "read_throttles_1h": int(metrics.get("ReadThrottleEvents", 0)),
                "write_throttles_1h": int(metrics.get("WriteThrottleEvents", 0)),
            }

        except (ClientError, BotoCoreError) as e:
            log.error("dynamodb_collect_error", table=table_name, error=str(e))
            result[table_name] = {"table_name": table_name, "error": str(e)}

    return result


# ─── Transfer Family (SFTP) ───────────────────────────────────────────────────

def collect_sftp_transfer_stats(transfer_client, cloudwatch_client, server_ids: list[str]) -> dict:
    """
    Collect SFTP transfer statistics from Transfer Family.
    """
    result = {}
    now = datetime.now(timezone.utc)
    start_time = now - timedelta(hours=24)

    for server_id in server_ids:
        try:
            server = transfer_client.describe_server(ServerId=server_id)
            server_info = server.get("Server", {})

            # Get transfer metrics from CloudWatch
            metrics = {}
            for metric_name in ["FilesIn", "FilesOut", "BytesIn", "BytesOut"]:
                response = cloudwatch_client.get_metric_statistics(
                    Namespace="AWS/Transfer",
                    MetricName=metric_name,
                    Dimensions=[{"Name": "ServerId", "Value": server_id}],
                    StartTime=start_time,
                    EndTime=now,
                    Period=86400,
                    Statistics=["Sum"],
                )
                datapoints = response.get("Datapoints", [])
                metrics[metric_name] = sum(dp["Sum"] for dp in datapoints)

            result[server_id] = {
                "server_id": server_id,
                "state": server_info.get("State", "UNKNOWN"),
                "endpoint": server_info.get("EndpointDetails", {}).get("AddressAllocationIds", []),
                "files_in_24h": int(metrics.get("FilesIn", 0)),
                "files_out_24h": int(metrics.get("FilesOut", 0)),
                "bytes_in_24h": int(metrics.get("BytesIn", 0)),
                "bytes_out_24h": int(metrics.get("BytesOut", 0)),
            }

        except (ClientError, BotoCoreError) as e:
            log.error("sftp_collect_error", server_id=server_id, error=str(e))
            result[server_id] = {"server_id": server_id, "error": str(e)}

    return result


# ─── CloudWatch Logs ──────────────────────────────────────────────────────────

def collect_cloudwatch_logs(
    logs_client,
    log_groups: list[str],
    lookback_minutes: int = 15,
    filter_pattern: str = "ERROR",
) -> list[str]:
    """
    Collect error logs from CloudWatch Log Groups.
    """
    now = datetime.now(timezone.utc)
    start_time = int((now - timedelta(minutes=lookback_minutes)).timestamp() * 1000)
    end_time = int(now.timestamp() * 1000)

    all_logs = []
    for log_group in log_groups:
        try:
            response = logs_client.filter_log_events(
                logGroupName=log_group,
                startTime=start_time,
                endTime=end_time,
                filterPattern=filter_pattern,
                limit=50,
            )
            for event in response.get("events", []):
                timestamp = datetime.fromtimestamp(event["timestamp"] / 1000, tz=timezone.utc)
                all_logs.append(f"[{timestamp.isoformat()}] [{log_group}] {event['message']}")
        except (ClientError, BotoCoreError) as e:
            log.error("cloudwatch_logs_error", log_group=log_group, error=str(e))

    return sorted(all_logs)[-100:]  # Return last 100 lines


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _arn_name(arn: str) -> str:
    """Extract the resource name from an ARN."""
    return arn.split(":")[-1] if ":" in arn else arn
