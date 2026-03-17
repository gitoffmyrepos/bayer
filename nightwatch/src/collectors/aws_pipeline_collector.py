#!/usr/bin/env python3
"""
Nightwatch AWS Pipeline Collector
==================================
Custom Prometheus metrics exporter for the Bayer ModelN.io pipeline on AWS.

Polls:
- AWS Step Functions execution history
- AWS Glue job run status and duration
- S3 bucket object counts and freshness
- SFTP transfer counts (via Transfer Family logs in S3)

Exposes metrics on :8080/metrics in Prometheus exposition format.

All AWS config from environment variables:
  AWS_REGION, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
  STEP_FUNCTION_ARNS (comma-separated)
  GLUE_JOB_NAMES (comma-separated)
  S3_BUCKETS_CONFIG (JSON: {"bucket": "prefix"})
  SCRAPE_INTERVAL_SECONDS (default: 30)
  PORT (default: 8080)

Author: Nova ⚡ | Nightwatch Platform
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, BotoCoreError
from flask import Flask, Response
from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    Info,
    generate_latest,
    CONTENT_TYPE_LATEST,
)
from prometheus_client.core import GaugeMetricFamily, CounterMetricFamily
import threading

# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "message": "%(message)s"}',
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("nightwatch.aws-collector")

# ─────────────────────────────────────────────────────────────────────────────
# Configuration from environment
# ─────────────────────────────────────────────────────────────────────────────
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")
AWS_SESSION_TOKEN = os.environ.get("AWS_SESSION_TOKEN")  # For assumed roles
SCRAPE_INTERVAL_SECONDS = int(os.environ.get("SCRAPE_INTERVAL_SECONDS", "30"))
PORT = int(os.environ.get("PORT", "8080"))

# Step Functions to monitor (comma-separated ARNs or names)
STEP_FUNCTION_ARNS = [
    arn.strip()
    for arn in os.environ.get(
        "STEP_FUNCTION_ARNS",
        "arn:aws:states:us-east-1:ACCOUNT:stateMachine:bay-modeln-jobs-workflow,"
        "arn:aws:states:us-east-1:ACCOUNT:stateMachine:bay-modeln-outbound-jobs-wrkflw",
    ).split(",")
    if arn.strip()
]

# Glue jobs to monitor (comma-separated)
GLUE_JOB_NAMES = [
    name.strip()
    for name in os.environ.get(
        "GLUE_JOB_NAMES",
        "bay-modeln-raw-job-us-east-1,"
        "bay-modeln-enriched-job-us-east-1,"
        "bay-modeln-rodb-job-us-east-1,"
        "bay-modeln-s3-to-sftp-pythonshell-job-us-east-1",
    ).split(",")
    if name.strip()
]

# S3 buckets and prefixes to monitor: {"bucket": "prefix"} or {"bucket": ["prefix1", "prefix2"]}
S3_BUCKETS_CONFIG_STR = os.environ.get(
    "S3_BUCKETS_CONFIG",
    json.dumps({
        "s3-landing-us-east-1": ["USRMT/Inbound/Source/", "USRMT/Outbound/Source/"],
        "S3-Raw-bucket-us-east-1": [""],
        "s3-Enriched-us-east-1": [""],
    }),
)
try:
    S3_BUCKETS_CONFIG: Dict[str, List[str]] = {
        bucket: (prefixes if isinstance(prefixes, list) else [prefixes])
        for bucket, prefixes in json.loads(S3_BUCKETS_CONFIG_STR).items()
    }
except json.JSONDecodeError as e:
    log.error(f"Failed to parse S3_BUCKETS_CONFIG: {e}")
    S3_BUCKETS_CONFIG = {}

# SFTP Transfer Family server ID
TRANSFER_SERVER_ID = os.environ.get("TRANSFER_SERVER_ID", "")

# ─────────────────────────────────────────────────────────────────────────────
# Prometheus Metrics Registry
# ─────────────────────────────────────────────────────────────────────────────
registry = CollectorRegistry()

# Step Functions metrics
SF_EXECUTION_STATUS = Gauge(
    "nightwatch_stepfunction_execution_status",
    "Step Function execution status (1=active, 0=inactive)",
    ["state_machine", "execution_name", "status"],
    registry=registry,
)
SF_DURATION_SECONDS = Histogram(
    "nightwatch_stepfunction_duration_seconds",
    "Step Function execution duration in seconds",
    ["state_machine"],
    buckets=[30, 60, 120, 300, 600, 1200, 1800, 3600, 7200],
    registry=registry,
)
SF_LAST_EXECUTION_TIMESTAMP = Gauge(
    "nightwatch_stepfunction_last_execution_timestamp",
    "Unix timestamp of the most recent Step Function execution",
    ["state_machine", "status"],
    registry=registry,
)
SF_EXECUTION_TOTAL = Counter(
    "nightwatch_stepfunction_executions_total",
    "Total Step Function executions by status",
    ["state_machine", "status"],
    registry=registry,
)

# Glue Job metrics
GLUE_JOB_STATUS = Gauge(
    "nightwatch_glue_job_status",
    "Glue job run status (1=active state, 0=inactive)",
    ["job_name", "status"],
    registry=registry,
)
GLUE_JOB_DURATION_SECONDS = Gauge(
    "nightwatch_glue_job_duration_seconds",
    "Most recent Glue job run duration in seconds",
    ["job_name"],
    registry=registry,
)
GLUE_JOB_LAST_RUN_TIMESTAMP = Gauge(
    "nightwatch_glue_job_last_run_timestamp",
    "Unix timestamp of the most recent Glue job run",
    ["job_name", "status"],
    registry=registry,
)
GLUE_JOB_DPU_SECONDS = Gauge(
    "nightwatch_glue_job_dpu_seconds",
    "DPU-seconds consumed by the most recent Glue job run",
    ["job_name"],
    registry=registry,
)
GLUE_JOB_CONSECUTIVE_FAILURES = Gauge(
    "nightwatch_glue_job_consecutive_failures",
    "Number of consecutive failures for this Glue job",
    ["job_name"],
    registry=registry,
)

# S3 metrics
S3_OBJECT_COUNT = Gauge(
    "nightwatch_s3_object_count",
    "Number of objects in S3 bucket/prefix",
    ["bucket", "prefix"],
    registry=registry,
)
S3_LAST_MODIFIED_AGE_SECONDS = Gauge(
    "nightwatch_s3_last_modified_age_seconds",
    "Seconds since the most recently modified object in S3 bucket/prefix",
    ["bucket", "prefix"],
    registry=registry,
)
S3_TOTAL_SIZE_BYTES = Gauge(
    "nightwatch_s3_total_size_bytes",
    "Total size in bytes of objects in S3 bucket/prefix",
    ["bucket", "prefix"],
    registry=registry,
)

# SFTP Transfer Family metrics
SFTP_TRANSFER_COUNT = Gauge(
    "nightwatch_sftp_transfer_count",
    "Number of SFTP transfers in the last scrape window",
    ["direction"],  # inbound / outbound
    registry=registry,
)
SFTP_BYTES_TRANSFERRED = Gauge(
    "nightwatch_sftp_bytes_transferred",
    "Total bytes transferred via SFTP",
    ["direction"],
    registry=registry,
)

# Collector health metrics
COLLECTOR_SCRAPE_DURATION = Histogram(
    "nightwatch_collector_scrape_duration_seconds",
    "Time spent collecting metrics from each AWS service",
    ["service"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
    registry=registry,
)
COLLECTOR_SCRAPE_ERRORS = Counter(
    "nightwatch_collector_scrape_errors_total",
    "Total number of AWS API errors during metric collection",
    ["service", "error_type"],
    registry=registry,
)
COLLECTOR_LAST_SCRAPE_TIMESTAMP = Gauge(
    "nightwatch_collector_last_scrape_timestamp",
    "Unix timestamp of the most recent successful scrape",
    ["service"],
    registry=registry,
)

# Collector info
COLLECTOR_INFO = Info(
    "nightwatch_collector",
    "Nightwatch AWS pipeline collector information",
    registry=registry,
)
COLLECTOR_INFO.info({
    "version": "1.0.0",
    "region": AWS_REGION,
    "pipeline": "bayer-modeln",
})

# ─────────────────────────────────────────────────────────────────────────────
# AWS Client Factory
# ─────────────────────────────────────────────────────────────────────────────

def make_aws_client(service: str):
    """Create boto3 client with retry config."""
    boto_config = Config(
        region_name=AWS_REGION,
        retries={"max_attempts": 3, "mode": "adaptive"},
        connect_timeout=10,
        read_timeout=30,
    )
    kwargs = {"config": boto_config}
    if AWS_ACCESS_KEY_ID:
        kwargs["aws_access_key_id"] = AWS_ACCESS_KEY_ID
        kwargs["aws_secret_access_key"] = AWS_SECRET_ACCESS_KEY
    if AWS_SESSION_TOKEN:
        kwargs["aws_session_token"] = AWS_SESSION_TOKEN
    return boto3.client(service, **kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# Step Functions Collector
# ─────────────────────────────────────────────────────────────────────────────

def collect_stepfunctions_metrics():
    """Poll Step Functions for recent executions and emit Prometheus metrics."""
    start = time.time()
    try:
        sfn = make_aws_client("stepfunctions")

        for sf_arn in STEP_FUNCTION_ARNS:
            # Extract human-readable name from ARN
            sm_name = sf_arn.split(":")[-1] if ":" in sf_arn else sf_arn

            try:
                # Get recent executions (last 50, max 1000)
                paginator = sfn.get_paginator("list_executions")
                page_iter = paginator.paginate(
                    stateMachineArn=sf_arn,
                    PaginationConfig={"MaxItems": 50},
                )

                latest_by_status: Dict[str, dict] = {}
                status_counts: Dict[str, int] = {}

                for page in page_iter:
                    for execution in page.get("executions", []):
                        status = execution["status"]
                        status_counts[status] = status_counts.get(status, 0) + 1

                        # Track the most recent execution per status
                        if status not in latest_by_status:
                            latest_by_status[status] = execution
                        elif execution["startDate"] > latest_by_status[status]["startDate"]:
                            latest_by_status[status] = execution

                # Emit status metrics for latest executions
                all_statuses = ["RUNNING", "SUCCEEDED", "FAILED", "TIMED_OUT", "ABORTED"]
                for status in all_statuses:
                    exec_info = latest_by_status.get(status)
                    exec_name = exec_info["name"] if exec_info else "none"
                    is_active = 1.0 if exec_info else 0.0
                    SF_EXECUTION_STATUS.labels(
                        state_machine=sm_name,
                        execution_name=exec_name,
                        status=status,
                    ).set(is_active)

                    if exec_info:
                        start_date = exec_info["startDate"]
                        SF_LAST_EXECUTION_TIMESTAMP.labels(
                            state_machine=sm_name,
                            status=status,
                        ).set(start_date.timestamp())

                # Get duration for the most recent execution (any status)
                all_executions = list(
                    sfn.list_executions(stateMachineArn=sf_arn, maxResults=1)
                    .get("executions", [])
                )
                if all_executions:
                    most_recent = all_executions[0]
                    # Describe to get stop date
                    try:
                        detail = sfn.describe_execution(executionArn=most_recent["executionArn"])
                        start_dt = detail["startDate"]
                        stop_dt = detail.get("stopDate")
                        if stop_dt:
                            duration = (stop_dt - start_dt).total_seconds()
                            SF_DURATION_SECONDS.labels(state_machine=sm_name).observe(duration)
                        elif detail["status"] == "RUNNING":
                            # Still running — report current duration
                            now = datetime.now(timezone.utc)
                            running_duration = (now - start_dt).total_seconds()
                            GLUE_JOB_DURATION_SECONDS.labels(job_name=sm_name).set(running_duration)
                    except (ClientError, BotoCoreError) as e:
                        log.warning(f"Could not describe execution {most_recent['executionArn']}: {e}")

                COLLECTOR_LAST_SCRAPE_TIMESTAMP.labels(service="stepfunctions").set(time.time())
                log.debug(f"Step Functions {sm_name}: {status_counts}")

            except (ClientError, BotoCoreError) as e:
                error_code = getattr(e, "response", {}).get("Error", {}).get("Code", type(e).__name__)
                log.error(f"Error collecting Step Functions metrics for {sm_name}: {e}")
                COLLECTOR_SCRAPE_ERRORS.labels(
                    service="stepfunctions",
                    error_type=error_code,
                ).inc()

    except Exception as e:
        log.exception(f"Unexpected error in collect_stepfunctions_metrics: {e}")
        COLLECTOR_SCRAPE_ERRORS.labels(service="stepfunctions", error_type="unexpected").inc()
    finally:
        duration = time.time() - start
        COLLECTOR_SCRAPE_DURATION.labels(service="stepfunctions").observe(duration)


# ─────────────────────────────────────────────────────────────────────────────
# Glue Job Collector
# ─────────────────────────────────────────────────────────────────────────────

def collect_glue_metrics():
    """Poll Glue for job run history and emit Prometheus metrics."""
    start = time.time()
    try:
        glue = make_aws_client("glue")

        for job_name in GLUE_JOB_NAMES:
            try:
                response = glue.get_job_runs(
                    JobName=job_name,
                    MaxResults=10,  # Last 10 runs
                )
                runs = response.get("JobRuns", [])

                if not runs:
                    log.info(f"No runs found for Glue job: {job_name}")
                    continue

                # Most recent run
                latest_run = runs[0]
                latest_status = latest_run["JobRunState"]
                latest_start = latest_run.get("StartedOn")
                latest_end = latest_run.get("CompletedOn")

                # Emit status gauges for all possible states
                all_states = ["STARTING", "RUNNING", "STOPPING", "STOPPED", "SUCCEEDED", "FAILED", "TIMEOUT", "ERROR", "WAITING"]
                for state in all_states:
                    is_active = 1.0 if latest_status == state else 0.0
                    GLUE_JOB_STATUS.labels(job_name=job_name, status=state).set(is_active)

                # Duration
                if latest_start and latest_end:
                    duration = (latest_end - latest_start).total_seconds()
                    GLUE_JOB_DURATION_SECONDS.labels(job_name=job_name).set(duration)
                    GLUE_JOB_LAST_RUN_TIMESTAMP.labels(
                        job_name=job_name,
                        status=latest_status,
                    ).set(latest_end.timestamp())
                elif latest_start:
                    # Still running
                    now = datetime.now(timezone.utc)
                    running_duration = (now - latest_start).total_seconds()
                    GLUE_JOB_DURATION_SECONDS.labels(job_name=job_name).set(running_duration)
                    GLUE_JOB_LAST_RUN_TIMESTAMP.labels(
                        job_name=job_name,
                        status=latest_status,
                    ).set(latest_start.timestamp())

                # DPU-seconds
                dpu_seconds = latest_run.get("DPUSeconds", 0.0) or 0.0
                GLUE_JOB_DPU_SECONDS.labels(job_name=job_name).set(dpu_seconds)

                # Count consecutive failures
                consecutive_failures = 0
                for run in runs:
                    if run["JobRunState"] in ("FAILED", "ERROR", "TIMEOUT"):
                        consecutive_failures += 1
                    else:
                        break  # Stop at first non-failure
                GLUE_JOB_CONSECUTIVE_FAILURES.labels(job_name=job_name).set(consecutive_failures)

                COLLECTOR_LAST_SCRAPE_TIMESTAMP.labels(service="glue").set(time.time())
                log.debug(f"Glue job {job_name}: {latest_status}, consecutive_failures={consecutive_failures}")

            except glue.exceptions.EntityNotFoundException:
                log.warning(f"Glue job not found: {job_name} (may not exist yet in this account)")
            except (ClientError, BotoCoreError) as e:
                error_code = getattr(e, "response", {}).get("Error", {}).get("Code", type(e).__name__)
                log.error(f"Error collecting Glue metrics for {job_name}: {e}")
                COLLECTOR_SCRAPE_ERRORS.labels(
                    service="glue",
                    error_type=error_code,
                ).inc()

    except Exception as e:
        log.exception(f"Unexpected error in collect_glue_metrics: {e}")
        COLLECTOR_SCRAPE_ERRORS.labels(service="glue", error_type="unexpected").inc()
    finally:
        duration = time.time() - start
        COLLECTOR_SCRAPE_DURATION.labels(service="glue").observe(duration)


# ─────────────────────────────────────────────────────────────────────────────
# S3 Collector
# ─────────────────────────────────────────────────────────────────────────────

def collect_s3_metrics():
    """List S3 objects in monitored buckets and emit freshness/count metrics."""
    start = time.time()
    try:
        s3 = make_aws_client("s3")
        now = datetime.now(timezone.utc)

        for bucket, prefixes in S3_BUCKETS_CONFIG.items():
            for prefix in prefixes:
                try:
                    paginator = s3.get_paginator("list_objects_v2")
                    page_iter = paginator.paginate(
                        Bucket=bucket,
                        Prefix=prefix,
                        PaginationConfig={"MaxItems": 10000},
                    )

                    object_count = 0
                    total_size = 0
                    most_recent_modified: Optional[datetime] = None

                    for page in page_iter:
                        for obj in page.get("Contents", []):
                            object_count += 1
                            total_size += obj.get("Size", 0)
                            last_mod = obj.get("LastModified")
                            if last_mod:
                                if most_recent_modified is None or last_mod > most_recent_modified:
                                    most_recent_modified = last_mod

                    S3_OBJECT_COUNT.labels(bucket=bucket, prefix=prefix).set(object_count)
                    S3_TOTAL_SIZE_BYTES.labels(bucket=bucket, prefix=prefix).set(total_size)

                    if most_recent_modified:
                        age_seconds = (now - most_recent_modified).total_seconds()
                        S3_LAST_MODIFIED_AGE_SECONDS.labels(
                            bucket=bucket,
                            prefix=prefix,
                        ).set(age_seconds)
                    else:
                        # No objects — set age to a large number to trigger staleness alerts
                        S3_LAST_MODIFIED_AGE_SECONDS.labels(
                            bucket=bucket,
                            prefix=prefix,
                        ).set(86400 * 365)  # 1 year = "never"

                    COLLECTOR_LAST_SCRAPE_TIMESTAMP.labels(service="s3").set(time.time())
                    log.debug(f"S3 {bucket}/{prefix}: {object_count} objects, {total_size} bytes")

                except s3.exceptions.NoSuchBucket:
                    log.warning(f"S3 bucket not found: {bucket} (bucket may not exist yet)")
                except ClientError as e:
                    error_code = e.response.get("Error", {}).get("Code", "unknown")
                    if error_code == "AccessDenied":
                        log.error(f"Access denied to S3 bucket {bucket}/{prefix} — check IAM permissions")
                    else:
                        log.error(f"Error listing S3 bucket {bucket}/{prefix}: {e}")
                    COLLECTOR_SCRAPE_ERRORS.labels(service="s3", error_type=error_code).inc()

    except Exception as e:
        log.exception(f"Unexpected error in collect_s3_metrics: {e}")
        COLLECTOR_SCRAPE_ERRORS.labels(service="s3", error_type="unexpected").inc()
    finally:
        duration = time.time() - start
        COLLECTOR_SCRAPE_DURATION.labels(service="s3").observe(duration)


# ─────────────────────────────────────────────────────────────────────────────
# SFTP Transfer Family Collector
# ─────────────────────────────────────────────────────────────────────────────

def collect_sftp_metrics():
    """
    Poll AWS Transfer Family for file transfer activity.
    Transfer Family doesn't have direct API for transfer counts,
    so we check CloudWatch metrics via boto3.
    Falls back to 0 if not configured.
    """
    start = time.time()
    try:
        if not TRANSFER_SERVER_ID:
            log.debug("TRANSFER_SERVER_ID not set, skipping SFTP metrics")
            SFTP_TRANSFER_COUNT.labels(direction="inbound").set(0)
            SFTP_TRANSFER_COUNT.labels(direction="outbound").set(0)
            return

        cw = make_aws_client("cloudwatch")

        now = datetime.now(timezone.utc)
        # Get last 5 minutes of transfer metrics
        period = 300

        for direction, metric_name in [("inbound", "FilesIn"), ("outbound", "FilesOut")]:
            try:
                response = cw.get_metric_statistics(
                    Namespace="AWS/Transfer",
                    MetricName=metric_name,
                    Dimensions=[{"Name": "ServerId", "Value": TRANSFER_SERVER_ID}],
                    StartTime=datetime.fromtimestamp(now.timestamp() - period, tz=timezone.utc),
                    EndTime=now,
                    Period=period,
                    Statistics=["Sum"],
                )
                datapoints = response.get("Datapoints", [])
                total = sum(dp.get("Sum", 0.0) for dp in datapoints)
                SFTP_TRANSFER_COUNT.labels(direction=direction).set(total)
                log.debug(f"SFTP {direction}: {total} files transferred in last {period}s")

            except (ClientError, BotoCoreError) as e:
                log.error(f"Error collecting SFTP {direction} metrics: {e}")
                SFTP_TRANSFER_COUNT.labels(direction=direction).set(0)

        for direction, metric_name in [("inbound", "BytesIn"), ("outbound", "BytesOut")]:
            try:
                response = cw.get_metric_statistics(
                    Namespace="AWS/Transfer",
                    MetricName=metric_name,
                    Dimensions=[{"Name": "ServerId", "Value": TRANSFER_SERVER_ID}],
                    StartTime=datetime.fromtimestamp(now.timestamp() - period, tz=timezone.utc),
                    EndTime=now,
                    Period=period,
                    Statistics=["Sum"],
                )
                total = sum(dp.get("Sum", 0.0) for dp in response.get("Datapoints", []))
                SFTP_BYTES_TRANSFERRED.labels(direction=direction).set(total)
            except (ClientError, BotoCoreError) as e:
                log.warning(f"Error collecting SFTP bytes {direction}: {e}")

        COLLECTOR_LAST_SCRAPE_TIMESTAMP.labels(service="sftp").set(time.time())

    except Exception as e:
        log.exception(f"Unexpected error in collect_sftp_metrics: {e}")
        COLLECTOR_SCRAPE_ERRORS.labels(service="sftp", error_type="unexpected").inc()
    finally:
        duration = time.time() - start
        COLLECTOR_SCRAPE_DURATION.labels(service="sftp").observe(duration)


# ─────────────────────────────────────────────────────────────────────────────
# Main collection loop
# ─────────────────────────────────────────────────────────────────────────────

def collect_all_metrics():
    """Run all collectors. Called on scrape or in background loop."""
    log.info("Running full metrics collection cycle")
    start = time.time()

    collect_stepfunctions_metrics()
    collect_glue_metrics()
    collect_s3_metrics()
    collect_sftp_metrics()

    total = time.time() - start
    log.info(f"Metrics collection complete in {total:.2f}s")


def background_collection_loop():
    """Background thread that refreshes metrics on a schedule."""
    while True:
        try:
            collect_all_metrics()
        except Exception as e:
            log.exception(f"Unhandled error in collection loop: {e}")
        time.sleep(SCRAPE_INTERVAL_SECONDS)


# ─────────────────────────────────────────────────────────────────────────────
# Flask App
# ─────────────────────────────────────────────────────────────────────────────

app = Flask(__name__)


@app.route("/metrics")
def metrics_endpoint():
    """Prometheus /metrics scrape endpoint."""
    output = generate_latest(registry)
    return Response(output, status=200, content_type=CONTENT_TYPE_LATEST)


@app.route("/health")
def health_endpoint():
    """Health check endpoint for Kubernetes liveness/readiness probes."""
    return Response(
        json.dumps({"status": "ok", "collector": "nightwatch-aws-pipeline"}),
        status=200,
        content_type="application/json",
    )


@app.route("/ready")
def ready_endpoint():
    """Readiness probe — check if we have at least one scrape cycle complete."""
    # Check if we have collected any metrics (last scrape within 5x interval)
    last_scrape = max(
        (
            COLLECTOR_LAST_SCRAPE_TIMESTAMP.labels(service=svc)._value.get()
            for svc in ("stepfunctions", "glue", "s3")
        ),
        default=0.0,
    )
    if last_scrape > 0:
        return Response(
            json.dumps({"status": "ready", "last_scrape": last_scrape}),
            status=200,
            content_type="application/json",
        )
    else:
        return Response(
            json.dumps({"status": "not_ready", "reason": "no_scrape_completed"}),
            status=503,
            content_type="application/json",
        )


@app.route("/config")
def config_endpoint():
    """Show current configuration (no secrets)."""
    return Response(
        json.dumps({
            "aws_region": AWS_REGION,
            "step_function_arns": STEP_FUNCTION_ARNS,
            "glue_job_names": GLUE_JOB_NAMES,
            "s3_buckets": list(S3_BUCKETS_CONFIG.keys()),
            "scrape_interval_seconds": SCRAPE_INTERVAL_SECONDS,
            "transfer_server_id": TRANSFER_SERVER_ID or "(not set)",
        }, indent=2),
        status=200,
        content_type="application/json",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    log.info("=" * 60)
    log.info("Nightwatch AWS Pipeline Collector v1.0.0")
    log.info(f"AWS Region: {AWS_REGION}")
    log.info(f"Step Functions: {STEP_FUNCTION_ARNS}")
    log.info(f"Glue Jobs: {GLUE_JOB_NAMES}")
    log.info(f"S3 Buckets: {list(S3_BUCKETS_CONFIG.keys())}")
    log.info(f"Scrape interval: {SCRAPE_INTERVAL_SECONDS}s")
    log.info(f"Listening on port: {PORT}")
    log.info("=" * 60)

    # Run initial collection synchronously so we have data before first scrape
    log.info("Running initial metrics collection...")
    collect_all_metrics()

    # Start background collection thread
    collector_thread = threading.Thread(
        target=background_collection_loop,
        name="nightwatch-collector",
        daemon=True,
    )
    collector_thread.start()
    log.info(f"Background collection thread started (interval={SCRAPE_INTERVAL_SECONDS}s)")

    # Start Flask server
    app.run(host="0.0.0.0", port=PORT, threaded=True)
