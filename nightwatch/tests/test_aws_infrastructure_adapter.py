import boto3
import pytest
from botocore.stub import Stubber

from src.adapters.aws_infrastructure.adapter import AWSInfrastructureAdapter


@pytest.fixture
def adapter(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "test")
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    return AWSInfrastructureAdapter({"region": "us-east-1"})


def test_ec2_stopped_instance_is_a_finding(adapter):
    adapter._snapshot = {
        "eks": [],
        "ec2": [
            {
                "id": "i-123",
                "name": "demo-web",
                "state": "stopped",
                "public_ip": None,
                "instance_status": "not-applicable",
                "system_status": "not-applicable",
            }
        ],
        "ecs": [],
    }

    checks = adapter.run_health_checks()

    assert any(
        check.name == "ec2_i-123_state" and check.status.value == "fail"
        for check in checks
    )


def test_ecs_capacity_mismatch_is_a_finding(adapter):
    adapter._snapshot = {
        "eks": [],
        "ec2": [],
        "ecs": [
            {
                "cluster": "demo",
                "service": "api",
                "desired": 2,
                "running": 0,
                "pending": 0,
            }
        ],
    }

    checks = adapter.run_health_checks()

    assert any(
        check.name == "ecs_demo_api_capacity" and check.status.value == "fail"
        for check in checks
    )


def test_running_ec2_impaired_status_is_a_finding(adapter):
    adapter._snapshot = {
        "eks": [],
        "ec2": [
            {
                "id": "i-impaired",
                "name": "demo-api",
                "state": "running",
                "public_ip": None,
                "instance_status": "impaired",
                "system_status": "ok",
            }
        ],
        "ecs": [],
    }

    checks = adapter.run_health_checks()

    assert any(
        check.name == "ec2_i-impaired_instance_health"
        and check.status.value == "fail"
        for check in checks
    )


def test_service_collection_failure_preserves_last_known_good_inventory(
    adapter, monkeypatch
):
    prior_eks = {
        "name": "prior-eks",
        "status": "ACTIVE",
        "version": "1.30",
        "endpoint_public": False,
    }
    adapter._snapshot = {"eks": [prior_eks], "ec2": [], "ecs": []}

    def fail_eks():
        raise RuntimeError("EKS unavailable")

    monkeypatch.setattr(adapter, "_collect_eks", fail_eks)
    monkeypatch.setattr(adapter, "_collect_ec2", lambda: [])
    monkeypatch.setattr(adapter, "_collect_ecs", lambda: [])

    snapshot = adapter.collect_metrics()

    assert snapshot["eks"] == [prior_eks]
    assert "eks" in adapter._collection_errors


def test_provider_failure_marks_retained_inventory_stale_without_refreshing_timestamp(
    adapter, monkeypatch
):
    prior = {
        "id": "i-prior",
        "name": "prior-web",
        "state": "running",
        "public_ip": None,
        "instance_status": "ok",
        "system_status": "ok",
    }
    key = ("ec2", "i-prior")
    adapter._snapshot = {"eks": [], "ec2": [prior], "ecs": []}
    adapter._resource_observed_at[key] = "2026-08-04T12:00:00+00:00"

    monkeypatch.setattr(adapter, "_collect_eks", lambda: [])
    monkeypatch.setattr(
        adapter,
        "_collect_ec2",
        lambda: (_ for _ in ()).throw(RuntimeError("EC2 unavailable")),
    )
    monkeypatch.setattr(adapter, "_collect_ecs", lambda: [])

    adapter.collect_metrics()
    component = adapter.get_component_inventory()[0]

    assert component.metadata["last_seen"] == "2026-08-04T12:00:00+00:00"
    assert component.metadata["stale"] is True


def test_instance_status_failure_does_not_refresh_prior_health_timestamp(adapter):
    prior = {
        "id": "i-running",
        "name": "api",
        "state": "running",
        "public_ip": None,
        "instance_status": "ok",
        "system_status": "ok",
    }
    key = ("ec2", "i-running")
    adapter._snapshot["ec2"] = [prior]
    adapter._resource_observed_at[key] = "2026-08-04T12:00:00+00:00"

    class EC2Client:
        def describe_instances(self, **kwargs):
            return {
                "Reservations": [
                    {
                        "Instances": [
                            {
                                "InstanceId": "i-running",
                                "State": {"Name": "running"},
                                "Tags": [{"Key": "Name", "Value": "api"}],
                            }
                        ]
                    }
                ]
            }

        def describe_instance_status(self, **kwargs):
            raise RuntimeError("status API unavailable")

    adapter._ec2_client = EC2Client()
    adapter._cycle_observed_at = "2026-08-04T12:05:00+00:00"
    adapter._snapshot["ec2"] = adapter._collect_ec2()
    component = adapter.get_component_inventory()[0]

    assert component.metadata["instance_status"] == "ok"
    assert component.metadata["last_seen"] == "2026-08-04T12:00:00+00:00"
    assert component.metadata["stale"] is True


def test_eks_resource_failure_preserves_prior_resource_and_new_success(adapter):
    prior_broken = {
        "name": "broken-eks",
        "status": "ACTIVE",
        "version": "1.29",
        "endpoint_public": False,
    }
    adapter._snapshot["eks"] = [prior_broken]

    class EKSClient:
        def list_clusters(self, **kwargs):
            return {"clusters": ["new-eks", "broken-eks"]}

        def describe_cluster(self, name):
            if name == "broken-eks":
                raise RuntimeError("describe failed")
            return {
                "cluster": {
                    "name": name,
                    "status": "ACTIVE",
                    "version": "1.31",
                    "resourcesVpcConfig": {"endpointPublicAccess": False},
                }
            }

    adapter._eks_client = EKSClient()

    clusters = adapter._collect_eks()

    assert [cluster["name"] for cluster in clusters] == ["new-eks", "broken-eks"]
    assert clusters[1] == prior_broken
    assert "eks:broken-eks" in adapter._collection_errors


def test_ecs_batch_failure_preserves_prior_service(adapter):
    prior_service = {
        "cluster": "demo",
        "service": "api",
        "desired": 2,
        "running": 2,
        "pending": 0,
    }
    adapter._snapshot["ecs"] = [prior_service]

    class ECSClient:
        def list_clusters(self, **kwargs):
            return {"clusterArns": ["arn:aws:ecs:us-east-1:123:cluster/demo"]}

        def list_services(self, **kwargs):
            return {
                "serviceArns": [
                    "arn:aws:ecs:us-east-1:123:service/demo/api"
                ]
            }

        def describe_services(self, **kwargs):
            raise RuntimeError("batch unavailable")

    adapter._ecs_client = ECSClient()

    services = adapter._collect_ecs()

    assert services == [prior_service]
    assert "ecs:demo:batch:0" in adapter._collection_errors


def test_collect_metrics_normalizes_read_only_aws_inventory(adapter):
    eks = boto3.client("eks", region_name="us-east-1")
    ec2 = boto3.client("ec2", region_name="us-east-1")
    ecs = boto3.client("ecs", region_name="us-east-1")
    adapter._eks_client = eks
    adapter._ec2_client = ec2
    adapter._ecs_client = ecs

    with Stubber(eks) as eks_stub, Stubber(ec2) as ec2_stub, Stubber(ecs) as ecs_stub:
        eks_stub.add_response("list_clusters", {"clusters": ["demo-eks"]})
        eks_stub.add_response(
            "describe_cluster",
            {
                "cluster": {
                    "name": "demo-eks",
                    "arn": "arn:aws:eks:us-east-1:123456789012:cluster/demo-eks",
                    "createdAt": "2026-08-04T00:00:00Z",
                    "version": "1.31",
                    "endpoint": "https://example.invalid",
                    "roleArn": "arn:aws:iam::123456789012:role/demo",
                    "resourcesVpcConfig": {
                        "subnetIds": [],
                        "securityGroupIds": [],
                        "endpointPublicAccess": True,
                        "endpointPrivateAccess": False,
                    },
                    "kubernetesNetworkConfig": {},
                    "logging": {"clusterLogging": []},
                    "identity": {},
                    "status": "ACTIVE",
                    "certificateAuthority": {},
                    "platformVersion": "eks.1",
                    "tags": {},
                    "accessConfig": {},
                    "upgradePolicy": {},
                    "zonalShiftConfig": {},
                    "deletionProtection": False,
                }
            },
            {"name": "demo-eks"},
        )
        ec2_stub.add_response(
            "describe_instances",
            {
                "Reservations": [
                    {
                        "Instances": [
                            {
                                "InstanceId": "i-123",
                                "ImageId": "ami-12345678",
                                "State": {"Code": 80, "Name": "stopped"},
                                "PrivateDnsName": "",
                                "PublicDnsName": "",
                                "StateTransitionReason": "",
                                "KeyName": "demo",
                                "AmiLaunchIndex": 0,
                                "ProductCodes": [],
                                "InstanceType": "t3.micro",
                                "LaunchTime": "2026-08-04T00:00:00Z",
                                "Placement": {
                                    "AvailabilityZone": "us-east-1a",
                                    "GroupName": "",
                                    "Tenancy": "default",
                                },
                                "Monitoring": {"State": "disabled"},
                                "SubnetId": "subnet-12345678",
                                "VpcId": "vpc-12345678",
                                "PrivateIpAddress": "10.0.0.10",
                                "Architecture": "x86_64",
                                "RootDeviceType": "ebs",
                                "RootDeviceName": "/dev/xvda",
                                "BlockDeviceMappings": [],
                                "VirtualizationType": "hvm",
                                "ClientToken": "demo",
                                "Hypervisor": "xen",
                                "NetworkInterfaces": [],
                                "EbsOptimized": False,
                                "EnaSupport": True,
                                "CpuOptions": {
                                    "CoreCount": 1,
                                    "ThreadsPerCore": 1,
                                },
                                "CapacityReservationSpecification": {
                                    "CapacityReservationPreference": "open"
                                },
                                "HibernationOptions": {"Configured": False},
                                "MetadataOptions": {
                                    "State": "applied",
                                    "HttpTokens": "required",
                                    "HttpPutResponseHopLimit": 1,
                                    "HttpEndpoint": "enabled",
                                },
                                "EnclaveOptions": {"Enabled": False},
                                "Tags": [
                                    {"Key": "Name", "Value": "demo-web"}
                                ],
                            }
                        ],
                        "Groups": [],
                        "OwnerId": "123456789012",
                        "ReservationId": "r-12345678",
                    }
                ]
            },
        )
        ec2_stub.add_response(
            "describe_instance_status",
            {
                "InstanceStatuses": [
                    {
                        "AvailabilityZone": "us-east-1a",
                        "InstanceId": "i-123",
                        "InstanceState": {"Code": 80, "Name": "stopped"},
                        "InstanceStatus": {
                            "Details": [],
                            "Status": "not-applicable",
                        },
                        "SystemStatus": {
                            "Details": [],
                            "Status": "not-applicable",
                        },
                    }
                ]
            },
            {"IncludeAllInstances": True},
        )
        ecs_stub.add_response(
            "list_clusters",
            {
                "clusterArns": [
                    "arn:aws:ecs:us-east-1:123456789012:cluster/demo"
                ]
            },
        )
        ecs_stub.add_response(
            "list_services",
            {
                "serviceArns": [
                    "arn:aws:ecs:us-east-1:123456789012:service/demo/api"
                ]
            },
            {"cluster": "arn:aws:ecs:us-east-1:123456789012:cluster/demo"},
        )
        ecs_stub.add_response(
            "describe_services",
            {
                "services": [
                    {
                        "serviceArn": "arn:aws:ecs:us-east-1:123456789012:service/demo/api",
                        "serviceName": "api",
                        "clusterArn": "arn:aws:ecs:us-east-1:123456789012:cluster/demo",
                        "status": "ACTIVE",
                        "desiredCount": 2,
                        "runningCount": 0,
                        "pendingCount": 0,
                        "launchType": "FARGATE",
                        "platformVersion": "LATEST",
                        "platformFamily": "Linux",
                        "taskDefinition": "api:1",
                        "deploymentConfiguration": {
                            "deploymentCircuitBreaker": {
                                "enable": False,
                                "rollback": False,
                            },
                            "maximumPercent": 200,
                            "minimumHealthyPercent": 100,
                        },
                        "deployments": [],
                        "roleArn": "arn:aws:iam::123456789012:role/demo",
                        "events": [],
                        "createdAt": "2026-08-04T00:00:00Z",
                        "placementConstraints": [],
                        "placementStrategy": [],
                        "schedulingStrategy": "REPLICA",
                        "enableECSManagedTags": False,
                        "propagateTags": "NONE",
                        "enableExecuteCommand": False,
                        "availabilityZoneRebalancing": "DISABLED",
                    }
                ],
                "failures": [],
            },
            {
                "cluster": "arn:aws:ecs:us-east-1:123456789012:cluster/demo",
                "services": [
                    "arn:aws:ecs:us-east-1:123456789012:service/demo/api"
                ],
            },
        )

        snapshot = adapter.collect_metrics()

    assert snapshot == {
        "eks": [
            {
                "name": "demo-eks",
                "status": "ACTIVE",
                "version": "1.31",
                "endpoint_public": True,
            }
        ],
        "ec2": [
            {
                "id": "i-123",
                "name": "demo-web",
                "state": "stopped",
                "public_ip": None,
                "instance_status": "not-applicable",
                "system_status": "not-applicable",
            }
        ],
        "ecs": [
            {
                "cluster": "demo",
                "service": "api",
                "desired": 2,
                "running": 0,
                "pending": 0,
            }
        ],
    }
