import * as cdk from "aws-cdk-lib";
import * as ecr from "aws-cdk-lib/aws-ecr";
import * as ecs from "aws-cdk-lib/aws-ecs";
import * as ecsp from "aws-cdk-lib/aws-ecs-patterns";
import * as iam from "aws-cdk-lib/aws-iam";
import * as logs from "aws-cdk-lib/aws-logs";
import { aws_secretsmanager as secretsmanager } from "aws-cdk-lib";
import * as ecrdeploy from "cdk-ecr-deployment";
import { Construct } from "constructs";
import { CommonStack, CommonStackProps } from "../common/stack";
import { DockerImageAsset } from "aws-cdk-lib/aws-ecr-assets";

export interface AppStackProps extends CommonStackProps {
  ragBucket: cdk.aws_s3.IBucket;
  authUserPoolId: string;
  authUserPoolClientId: string;
  authUserPoolClientSecret: string;
  supervisorAgentId: string;
  supervisorAgentAliasId: string;
}

export class AppStack extends CommonStack {
  constructor(scope: Construct, id: string, props: AppStackProps) {
    super(scope, id, props);

    const ecsCluster = new cdk.aws_ecs.Cluster(this, this.getResourceId("ecs-cluster"), {
      clusterName: this.getResourceId("ecs-cluster"),
      containerInsights: true,
    });

    const logGroup = new logs.LogGroup(this, this.getResourceId("app-log-group"), {
      logGroupName: this.getResourceId("app-log-group"),
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    const langfuseSecret = secretsmanager.Secret.fromSecretNameV2(
      this,
      this.getResourceId("langfuse-secret"),
      "langfuse/api",
    );

    const ecsInstanceRole = new iam.Role(this, this.getResourceId("app-instance-role"), {
      roleName: this.getResourceId("app-instance-role"),
      assumedBy: new iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName("AmazonSSMReadOnlyAccess"),
        iam.ManagedPolicy.fromAwsManagedPolicyName("AmazonBedrockFullAccess"),
        iam.ManagedPolicy.fromAwsManagedPolicyName("service-role/AmazonECSTaskExecutionRolePolicy"),
      ],
    });
    props.ragBucket.grantRead(ecsInstanceRole);

    const timestampTag = new Date().getTime().toString();
    const ecrRepo = new ecr.Repository(this, this.getResourceId("app-repo"), {
      repositoryName: this.getResourceId("app-repo"),
      emptyOnDelete: true,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });
    const ecsContainerImage = new DockerImageAsset(this, this.getResourceId("app-ecr-image"), {
      directory: `${CommonStack.Path.Root}/${CommonStack.Path.Source.App}`,
    });

    ecsContainerImage.node.addDependency(ecrRepo);
    const ecrDeployment = new ecrdeploy.ECRDeployment(this, this.getResourceId("app-ecr-deployment"), {
      src: new ecrdeploy.DockerImageName(ecsContainerImage.imageUri),
      dest: new ecrdeploy.DockerImageName(ecrRepo.repositoryUriForTag(timestampTag)),
    });
    ecrDeployment.node.addDependency(ecsContainerImage);

    const taskDefinitionId = this.getResourceId("app-service-task");
    const taskDefinition = new ecs.FargateTaskDefinition(this, taskDefinitionId, {
      cpu: 1024,
      memoryLimitMiB: 2048,
      taskRole: ecsInstanceRole,
    });
    taskDefinition.addContainer(this.getResourceId("app-container"), {
      image: ecs.ContainerImage.fromEcrRepository(ecrRepo, timestampTag),
      containerName: this.getResourceId("app-container"),
      readonlyRootFilesystem: true,
      portMappings: [{ containerPort: 8501 }],
      environment: {
        RUNTIME_ENV: "dev",
        AWS_REGION: this.getRegion(),
        BEDROCK_REGION: this.getRegion(),
        LANGFUSE_PUBLIC_KEY: langfuseSecret.secretValueFromJson("LANGFUSE_PUBLIC_KEY").toString(),
        LANGFUSE_SECRET_KEY: langfuseSecret.secretValueFromJson("LANGFUSE_SECRET_KEY").toString(),
        SUPERVISOR_AGENT_ID: props.supervisorAgentId,
        SUPERVISOR_AGENT_ALIAS_ID: props.supervisorAgentAliasId,
        RAG_BUCKET: props.ragBucket.bucketName,
        USER_POOL_ID: props.authUserPoolId,
        USER_POOL_CLIENT_ID: props.authUserPoolClientId,
        USER_POOL_CLIENT_SECRET: props.authUserPoolClientSecret,
      },
      logging: ecs.LogDrivers.awsLogs({
        streamPrefix: "app",
        logGroup: logGroup,
      }),
    });

    const ecsService = new ecsp.ApplicationLoadBalancedFargateService(this, this.getResourceId("app-ecs-service"), {
      cluster: ecsCluster,
      desiredCount: 1,
      taskDefinition: taskDefinition,
      serviceName: this.getResourceId("app-service"),
      runtimePlatform: {
        cpuArchitecture: ecs.CpuArchitecture.X86_64,
        operatingSystemFamily: ecs.OperatingSystemFamily.LINUX,
      },
      platformVersion: ecs.FargatePlatformVersion.LATEST,
      loadBalancerName: this.getResourceId("app-lb"),
      publicLoadBalancer: true,
      assignPublicIp: true,
      circuitBreaker: {
        rollback: true,
      },
      healthCheckGracePeriod: cdk.Duration.seconds(60),
    });
    ecsService.targetGroup.configureHealthCheck({
      path: "/healthz",
      port: "8501",
      interval: cdk.Duration.seconds(30),
      timeout: cdk.Duration.seconds(20),
      unhealthyThresholdCount: 2,
      healthyThresholdCount: 2,
      healthyHttpCodes: "200",
    });
    ecsService.node.addDependency(ecrDeployment);

    new cdk.CfnOutput(this, this.getResourceId("app-service-url"), {
      value: `http://${ecsService.loadBalancer.loadBalancerDnsName}`,
      exportName: this.getResourceId("app-service-url"),
    });
  }
}
