"""
AWS Pipeline Adapter — Bayer ModelN.io
========================================
Monitors the Bayer ModelN.io pharma data pipeline on AWS.

Monitors:
  - AWS Step Functions (bay-modeln-jobs-workflow, bay-modeln-outbound-jobs-wrkflw)
  - AWS Glue ETL jobs (raw, enriched, rodb, s3-to-sftp)
  - S3 buckets (landing, raw, enriched)
  - Lambda functions (audit, transforms)
  - DynamoDB tables
  - Transfer Family SFTP servers

Config (adapters/aws_pipeline/config.yaml):
  aws_region, step_function_arns, glue_jobs, s3_buckets,
  lambda_functions, dynamodb_tables, sftp_server_ids

Auth: boto3 credential chain (IAM role > env vars AWS_ACCESS_KEY_ID/SECRET > ~/.aws/credentials)

Author: Nova ⚡ | Nightwatch Platform
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, BotoCoreError

from src.adapters.base_adapter import BaseNightwatchAdapter, HealthCheck, CheckStatus, Component
from src.adapters.aws_pipeline.collectors import (
    collect_step_function_status,
    collect_glue_job_status,
    collect_s3_bucket_stats,
    collect_lambda_errors,
    collect_dynamodb_metrics,
    collect_sftp_transfer_stats,
    collect_cloudwatch_logs,
)

log = logging.getLogger("nightwatch.adapter.aws_pipeline")

BOTO3_CONFIG = Config(
    retries={"max_attempts": 3, "mode": "adaptive"},
    connect_timeout=10,
    read_timeout=30,
)


class AWSPipelineAdapter(BaseNightwatchAdapter):
    """
    Nightwatch adapter for AWS-based data pipelines.

    First use case: Bayer ModelN.io pharma data pipeline.
    Reusable for any AWS Step Functions + Glue + S3 pipeline.
    """

    @property
    def application_name(self) -> str:
        return self.config.get("application_name", "AWS Data Pipeline")

    def __init__(self, config: dict):
        super().__init__(config)

        self.aws_region = config.get("aws_region", "us-east-1")
        self.step_function_arns = config.get("step_function_arns", [])
        self.glue_job_names = config.get("glue_jobs", [])
        self.s3_buckets_config = config.get("s3_buckets", {})
        self.lambda_function_names = config.get("lambda_functions", [])
        self.dynamodb_table_names = config.get("dynamodb_tables", [])
        self.sftp_server_ids = config.get("sftp_server_ids", [])
        self.cloudwatch_log_groups = config.get("cloudwatch_log_groups", [])

        # Health check thresholds (configurable)
        thresholds = config.get("thresholds", {})
        self.max_s3_age_hours = thresholds.get("max_s3_age_hours", 2)
        self.max_consecutive_glue_failures = thresholds.get("max_consecutive_glue_failures", 2)
        self.max_lambda_error_rate = thresholds.get("max_lambda_error_rate", 0.05)
        self.max_dynamodb_throttle_rate = thresholds.get("max_dynamodb_throttle_rate", 0.05)
        self.min_sftp_files_per_day = thresholds.get("min_sftp_files_per_day", 1)

        # Lazy-init boto3 clients
        self._sfn_client = None
        self._glue_client = None
        self._s3_client = None
        self._cw_client = None
        self._logs_client = None
        self._transfer_client = None

    def initialize(self) -> None:
        """Test AWS connectivity."""
        try:
            sts = boto3.client("sts", region_name=self.aws_region, config=BOTO3_CONFIG)
            identity = sts.get_caller_identity()
            log.info("aws_auth_ok", account=identity["Account"], arn=identity["Arn"])
            self._initialized = True
        except Exception as e:
            raise RuntimeError(f"AWS authentication failed: {e}")

    # ─── boto3 Client Accessors (lazy init) ────────────────────────────────────

    @property
    def _sfn(self):
        if not self._sfn_client:
            self._sfn_client = boto3.client("stepfunctions", region_name=self.aws_region, config=BOTO3_CONFIG)
        return self._sfn_client

    @property
    def _glue(self):
        if not self._glue_client:
            self._glue_client = boto3.client("glue", region_name=self.aws_region, config=BOTO3_CONFIG)
        return self._glue_client

    @property
    def _s3(self):
        if not self._s3_client:
            self._s3_client = boto3.client("s3", region_name=self.aws_region, config=BOTO3_CONFIG)
        return self._s3_client

    @property
    def _cw(self):
        if not self._cw_client:
            self._cw_client = boto3.client("cloudwatch", region_name=self.aws_region, config=BOTO3_CONFIG)
        return self._cw_client

    @property
    def _logs(self):
        if not self._logs_client:
            self._logs_client = boto3.client("logs", region_name=self.aws_region, config=BOTO3_CONFIG)
        return self._logs_client

    @property
    def _transfer(self):
        if not self._transfer_client:
            self._transfer_client = boto3.client("transfer", region_name=self.aws_region, config=BOTO3_CONFIG)
        return self._transfer_client

    # ─── Data Collection ──────────────────────────────────────────────────────

    def collect_metrics(self) -> dict:
        """Collect all AWS pipeline metrics."""
        metrics = {}

        if self.step_function_arns:
            metrics["step_functions"] = collect_step_function_status(self._sfn, self.step_function_arns)

        if self.glue_job_names:
            metrics["glue_jobs"] = collect_glue_job_status(self._glue, self.glue_job_names)

        if self.s3_buckets_config:
            metrics["s3"] = collect_s3_bucket_stats(self._s3, self.s3_buckets_config)

        if self.lambda_function_names:
            metrics["lambda"] = collect_lambda_errors(self._cw, self.lambda_function_names)

        if self.dynamodb_table_names:
            metrics["dynamodb"] = collect_dynamodb_metrics(self._cw, self.dynamodb_table_names)

        if self.sftp_server_ids:
            metrics["sftp"] = collect_sftp_transfer_stats(self._transfer, self._cw, self.sftp_server_ids)

        return metrics

    def collect_logs(self, lookback_minutes: int = 15) -> list[str]:
        """Collect error logs from CloudWatch Log Groups."""
        if not self.cloudwatch_log_groups:
            return []

        return collect_cloudwatch_logs(
            self._logs,
            self.cloudwatch_log_groups,
            lookback_minutes=lookback_minutes,
            filter_pattern="?ERROR ?FAILED ?Exception",
        )

    # ─── Health Checks ────────────────────────────────────────────────────────

    def run_health_checks(self) -> list[HealthCheck]:
        """Run all health checks for the AWS pipeline."""
        checks = []

        metrics = self.collect_metrics()

        # Step Function checks
        if sfn_metrics := metrics.get("step_functions", {}):
            checks.extend(self._check_step_functions(sfn_metrics))

        # Glue job checks
        if glue_metrics := metrics.get("glue_jobs", {}):
            checks.extend(self._check_glue_jobs(glue_metrics))

        # S3 freshness checks
        if s3_metrics := metrics.get("s3", {}):
            checks.extend(self._check_s3_freshness(s3_metrics))

        # Lambda error rate checks
        if lambda_metrics := metrics.get("lambda", {}):
            checks.extend(self._check_lambda_errors(lambda_metrics))

        # DynamoDB throttling checks
        if dynamo_metrics := metrics.get("dynamodb", {}):
            checks.extend(self._check_dynamodb_throttling(dynamo_metrics))

        # SFTP checks
        if sftp_metrics := metrics.get("sftp", {}):
            checks.extend(self._check_sftp(sftp_metrics))

        return checks

    def _check_step_functions(self, sfn_metrics: dict) -> list[HealthCheck]:
        checks = []
        for arn, data in sfn_metrics.items():
            name = data.get("name", arn)
            if "error" in data:
                checks.append(self._fail(
                    f"sfn_{name}_accessible",
                    f"Cannot access Step Function {name}: {data['error']}",
                    component="AWS Step Functions",
                    arn=arn,
                ))
                continue

            latest = data.get("latest_execution")
            if not latest:
                checks.append(self._warn(
                    f"sfn_{name}_executions",
                    f"No executions found for Step Function {name}",
                    component="AWS Step Functions",
                    arn=arn,
                ))
                continue

            status = latest.get("status", "UNKNOWN")
            if status == "SUCCEEDED":
                checks.append(self._ok(
                    f"sfn_{name}_status",
                    f"Step Function {name} last execution SUCCEEDED",
                    component="AWS Step Functions",
                    arn=arn, status=status,
                ))
            elif status == "RUNNING":
                checks.append(self._ok(
                    f"sfn_{name}_status",
                    f"Step Function {name} is RUNNING",
                    component="AWS Step Functions",
                    arn=arn, status=status,
                ))
            elif status in ("FAILED", "TIMED_OUT", "ABORTED"):
                failed_count = data.get("failed_count_24h", 0)
                checks.append(self._fail(
                    f"sfn_{name}_status",
                    f"Step Function {name} last execution {status} ({failed_count} failures in 24h)",
                    component="AWS Step Functions",
                    arn=arn, status=status, failed_count_24h=failed_count,
                ))

        return checks

    def _check_glue_jobs(self, glue_metrics: dict) -> list[HealthCheck]:
        checks = []
        for job_name, data in glue_metrics.items():
            if "error" in data:
                checks.append(self._fail(
                    f"glue_{job_name}_accessible",
                    f"Cannot access Glue job {job_name}: {data['error']}",
                    component="AWS Glue",
                ))
                continue

            latest = data.get("latest_run")
            if not latest:
                checks.append(self._warn(
                    f"glue_{job_name}_runs",
                    f"No runs found for Glue job {job_name}",
                    component="AWS Glue",
                ))
                continue

            state = latest.get("job_run_state", "UNKNOWN")
            consecutive_failures = data.get("consecutive_failures", 0)

            if state == "SUCCEEDED":
                checks.append(self._ok(
                    f"glue_{job_name}_status",
                    f"Glue job {job_name} last run SUCCEEDED",
                    component="AWS Glue",
                    state=state,
                ))
            elif state == "RUNNING":
                checks.append(self._ok(
                    f"glue_{job_name}_status",
                    f"Glue job {job_name} is RUNNING",
                    component="AWS Glue",
                    state=state,
                ))
            elif state in ("FAILED", "ERROR", "TIMEOUT"):
                if consecutive_failures >= self.max_consecutive_glue_failures:
                    checks.append(self._fail(
                        f"glue_{job_name}_status",
                        f"Glue job {job_name} FAILED {consecutive_failures} times consecutively",
                        component="AWS Glue",
                        state=state, consecutive_failures=consecutive_failures,
                        error=latest.get("error_message", "No error message"),
                    ))
                else:
                    checks.append(self._warn(
                        f"glue_{job_name}_status",
                        f"Glue job {job_name} last run {state} (failure #{consecutive_failures})",
                        component="AWS Glue",
                        state=state, consecutive_failures=consecutive_failures,
                    ))

            # Duration anomaly check
            avg_duration = data.get("avg_duration_7d_seconds")
            current_duration = latest.get("duration_seconds")
            if avg_duration and current_duration and current_duration > avg_duration * 2.5:
                checks.append(self._warn(
                    f"glue_{job_name}_duration",
                    f"Glue job {job_name} duration {current_duration:.0f}s is >2.5x the 7-day average ({avg_duration:.0f}s)",
                    component="AWS Glue",
                    current_seconds=current_duration,
                    avg_7d_seconds=avg_duration,
                ))

        return checks

    def _check_s3_freshness(self, s3_metrics: dict) -> list[HealthCheck]:
        checks = []
        max_age_seconds = self.max_s3_age_hours * 3600

        for path, data in s3_metrics.items():
            if "error" in data:
                checks.append(self._warn(
                    f"s3_{_safe_name(path)}_accessible",
                    f"Cannot access S3 {path}: {data['error']}",
                    component="Amazon S3",
                ))
                continue

            age = data.get("last_modified_age_seconds")
            count = data.get("object_count", 0)

            if count == 0:
                checks.append(self._warn(
                    f"s3_{_safe_name(path)}_objects",
                    f"S3 {path} has no objects",
                    component="Amazon S3",
                    bucket=data.get("bucket"), prefix=data.get("prefix"),
                ))
            elif age is not None and age > max_age_seconds:
                hours_ago = age / 3600
                checks.append(self._warn(
                    f"s3_{_safe_name(path)}_freshness",
                    f"S3 {path} last modified {hours_ago:.1f}h ago (threshold: {self.max_s3_age_hours}h)",
                    component="Amazon S3",
                    bucket=data.get("bucket"), age_hours=round(hours_ago, 2),
                ))
            else:
                checks.append(self._ok(
                    f"s3_{_safe_name(path)}_freshness",
                    f"S3 {path} has {count} objects, last modified {age/60:.0f}m ago",
                    component="Amazon S3",
                    bucket=data.get("bucket"), object_count=count,
                ))

        return checks

    def _check_lambda_errors(self, lambda_metrics: dict) -> list[HealthCheck]:
        checks = []
        for func_name, data in lambda_metrics.items():
            if "error" in data:
                continue

            error_rate = data.get("error_rate", 0)
            errors = data.get("errors_1h", 0)

            if error_rate > self.max_lambda_error_rate:
                checks.append(self._warn(
                    f"lambda_{_safe_name(func_name)}_errors",
                    f"Lambda {func_name} error rate {error_rate:.1%} exceeds threshold {self.max_lambda_error_rate:.1%}",
                    component="AWS Lambda",
                    function=func_name, error_rate=error_rate, errors_1h=errors,
                ))
            else:
                checks.append(self._ok(
                    f"lambda_{_safe_name(func_name)}_errors",
                    f"Lambda {func_name}: {errors} errors, {error_rate:.2%} error rate (1h)",
                    component="AWS Lambda",
                    function=func_name, error_rate=error_rate,
                ))

        return checks

    def _check_dynamodb_throttling(self, dynamo_metrics: dict) -> list[HealthCheck]:
        checks = []
        for table_name, data in dynamo_metrics.items():
            if "error" in data:
                continue

            read_throttles = data.get("read_throttles_1h", 0)
            write_throttles = data.get("write_throttles_1h", 0)

            if read_throttles > 0 or write_throttles > 0:
                checks.append(self._warn(
                    f"dynamo_{_safe_name(table_name)}_throttling",
                    f"DynamoDB {table_name}: {read_throttles} read throttles, {write_throttles} write throttles (1h)",
                    component="Amazon DynamoDB",
                    table=table_name, read_throttles=read_throttles, write_throttles=write_throttles,
                ))
            else:
                checks.append(self._ok(
                    f"dynamo_{_safe_name(table_name)}_throttling",
                    f"DynamoDB {table_name}: no throttling",
                    component="Amazon DynamoDB",
                    table=table_name,
                ))

        return checks

    def _check_sftp(self, sftp_metrics: dict) -> list[HealthCheck]:
        checks = []
        for server_id, data in sftp_metrics.items():
            if "error" in data:
                checks.append(self._warn(
                    f"sftp_{server_id}_accessible",
                    f"Cannot access SFTP server {server_id}: {data['error']}",
                    component="AWS Transfer Family",
                ))
                continue

            state = data.get("state", "UNKNOWN")
            if state != "ONLINE":
                checks.append(self._fail(
                    f"sftp_{server_id}_online",
                    f"SFTP server {server_id} is {state} (expected ONLINE)",
                    component="AWS Transfer Family",
                    server_id=server_id, state=state,
                ))
            else:
                files_out = data.get("files_out_24h", 0)
                if files_out < self.min_sftp_files_per_day:
                    checks.append(self._warn(
                        f"sftp_{server_id}_transfers",
                        f"SFTP server {server_id}: only {files_out} outbound files in 24h (expected >= {self.min_sftp_files_per_day})",
                        component="AWS Transfer Family",
                        server_id=server_id, files_out_24h=files_out,
                    ))
                else:
                    checks.append(self._ok(
                        f"sftp_{server_id}_online",
                        f"SFTP server {server_id} ONLINE, {files_out} outbound files (24h)",
                        component="AWS Transfer Family",
                        server_id=server_id, files_out_24h=files_out,
                    ))

        return checks

    # ─── Component Inventory ──────────────────────────────────────────────────

    def get_component_inventory(self) -> list[Component]:
        components = []

        for arn in self.step_function_arns:
            name = arn.split(":")[-1]
            components.append(Component(
                name=name, type="step_function",
                category="AWS Step Functions",
                description=f"Step Function: {name}",
                metadata={"arn": arn},
            ))

        for job_name in self.glue_job_names:
            components.append(Component(
                name=job_name, type="glue_job",
                category="AWS Glue",
                description=f"Glue ETL job: {job_name}",
            ))

        for bucket, prefixes in self.s3_buckets_config.items():
            if isinstance(prefixes, str):
                prefixes = [prefixes]
            for prefix in prefixes:
                components.append(Component(
                    name=f"{bucket}/{prefix}" if prefix else bucket,
                    type="s3_bucket",
                    category="Amazon S3",
                    description=f"S3 bucket: {bucket}, prefix: {prefix or '/'}",
                    metadata={"bucket": bucket, "prefix": prefix},
                ))

        for func in self.lambda_function_names:
            components.append(Component(name=func, type="lambda_function", category="AWS Lambda"))

        for table in self.dynamodb_table_names:
            components.append(Component(name=table, type="dynamodb_table", category="Amazon DynamoDB"))

        for server_id in self.sftp_server_ids:
            components.append(Component(name=server_id, type="sftp_server", category="AWS Transfer Family"))

        return components

    def describe_architecture(self) -> str:
        app_name = self.application_name
        sfn_names = [arn.split(":")[-1] for arn in self.step_function_arns]
        return (
            f"{app_name} is an AWS data pipeline consisting of:\n"
            f"- Step Functions: {', '.join(sfn_names) if sfn_names else 'none configured'}\n"
            f"- Glue ETL Jobs: {', '.join(self.glue_job_names) if self.glue_job_names else 'none configured'}\n"
            f"- S3 Buckets: {', '.join(self.s3_buckets_config.keys()) if self.s3_buckets_config else 'none configured'}\n"
            f"- Lambda Functions: {', '.join(self.lambda_function_names) if self.lambda_function_names else 'none'}\n"
            f"- DynamoDB Tables: {', '.join(self.dynamodb_table_names) if self.dynamodb_table_names else 'none'}\n"
            f"- SFTP Servers: {', '.join(self.sftp_server_ids) if self.sftp_server_ids else 'none'}\n"
            f"The pipeline processes data through Step Functions orchestration, runs Glue ETL jobs, "
            f"lands data in S3, and delivers to downstream partners via SFTP."
        )


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _safe_name(name: str) -> str:
    """Convert a string to a safe identifier for check names."""
    return name.replace("/", "_").replace("-", "_").replace(".", "_").replace(" ", "_")[:50]
