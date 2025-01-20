import { amazonaurora, bedrock } from "@cdklabs/generative-ai-cdk-constructs";
import * as cdk from "aws-cdk-lib";
import * as iam from "aws-cdk-lib/aws-iam";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as lambda_python from "@aws-cdk/aws-lambda-python-alpha";

import { Construct } from "constructs";
import { CommonStack, CommonStackProps } from "../common/stack";
import { NodejsFunction } from "aws-cdk-lib/aws-lambda-nodejs";
import { LambdaDestination } from "aws-cdk-lib/aws-s3-notifications";
import { EventType } from "aws-cdk-lib/aws-s3";
import { readFileSync } from "fs";

export interface BedrockStackProps extends CommonStackProps {
  vectorStore: amazonaurora.AmazonAuroraVectorStore;
}

export class BedrockStack extends CommonStack {
  public readonly ragBucket: cdk.aws_s3.IBucket;
  public readonly supervisorAgentId: string;
  public readonly supervisorAgentAliasId: string;

  constructor(scope: Construct, id: string, props: BedrockStackProps) {
    super(scope, id, props);

    const ragBucket = new cdk.aws_s3.Bucket(this, this.getResourceId("bedrock-rag"), {
      blockPublicAccess: cdk.aws_s3.BlockPublicAccess.BLOCK_ALL,
      encryption: cdk.aws_s3.BucketEncryption.S3_MANAGED,
      bucketName: this.getResourceId("bedrock-rag"),
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
      enforceSSL: true,
    });
    this.ragBucket = ragBucket;

    if (!this.bundlingRequired) {
      // skip stack if not selected (https://github.com/aws/aws-cdk/issues/6743)
      console.info(`Skipping ${this.stackName}`);
      this.supervisorAgentId = "";
      this.supervisorAgentAliasId = "";
      return;
    }

    const knowledgeBase = new bedrock.KnowledgeBase(this, this.getResourceId("bedrock-knowledge-base"), {
      name: this.getResourceId("bedrock-knowledge-base"),
      instruction: "Use this knowledge base to answer questions about medical protocols and studies.",
      description: "Knowledge base that contains medical protocols and studies.",
      embeddingsModel: bedrock.BedrockFoundationModel.TITAN_EMBED_TEXT_V2_512,
      vectorStore: props.vectorStore,
    });

    const ragSource = new bedrock.S3DataSource(this, this.getResourceId("bedrock-rag-source"), {
      bucket: ragBucket,
      description: "Contains medical protocols and studies.",
      knowledgeBase: knowledgeBase,
      dataSourceName: this.getResourceId("bedrock-rag-source"),
      chunkingStrategy: bedrock.ChunkingStrategy.HIERARCHICAL_TITAN,
      parsingStrategy: bedrock.ParsingStategy.foundationModel({
        parsingModel: bedrock.BedrockFoundationModel.ANTHROPIC_CLAUDE_3_5_SONNET_V1_0,
      }),
    });

    const ragSyncLambdaRole = new iam.Role(this, this.getResourceId("bedrock-rag-sync-lambda-role"), {
      assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
      roleName: this.getResourceId("bedrock-rag-sync-lambda-role"),
      inlinePolicies: {
        ["bedrockPolicy"]: new iam.PolicyDocument({
          statements: [
            new iam.PolicyStatement({
              resources: ["*"],
              actions: ["bedrock:*"],
            }),
          ],
        }),
      },
      managedPolicies: [iam.ManagedPolicy.fromAwsManagedPolicyName("service-role/AWSLambdaBasicExecutionRole")],
    });

    const ragSyncLambda = new NodejsFunction(this, this.getResourceId("bedrock-rag-sync-lambda"), {
      entry: CommonStack.Path.Source.RAGDataSync,
      functionName: this.getResourceId("bedrock-rag-sync-lambda"),
      runtime: lambda.Runtime.NODEJS_LATEST,
      architecture: lambda.Architecture.ARM_64,
      handler: "handler",
      timeout: cdk.Duration.minutes(5),
      role: ragSyncLambdaRole,
      environment: {
        KNOWLEDGE_BASE_ID: knowledgeBase.knowledgeBaseId,
        DATA_SOURCE_ID: ragSource.dataSourceId,
      },
    });
    ragSyncLambda.node.addDependency(ragSource);
    ragBucket.grantRead(ragSyncLambda);
    ragBucket.addEventNotification(EventType.OBJECT_CREATED, new LambdaDestination(ragSyncLambda), {
      prefix: "knowledgeBase",
    });

    const ragDeployment = new cdk.aws_s3_deployment.BucketDeployment(
      this,
      this.getResourceId("bedrock-rag-deployment"),
      {
        sources: [cdk.aws_s3_deployment.Source.asset(`${CommonStack.Path.Root}/${CommonStack.Path.Source.Protocols}`)],
        destinationBucket: ragBucket,
        destinationKeyPrefix: "knowledgeBase",
        retainOnDelete: false,
      },
    );
    ragDeployment.node.addDependency(ragSyncLambda);

    const clinicalTrialsLambda = new lambda_python.PythonFunction(
      this,
      this.getResourceId("bedrock-lambda-clinical-trials"),
      {
        functionName: this.getResourceId("bedrock-lambda-clinical-trials"),
        description: "Lambda function that fetches relevant clinical trials.",
        runtime: lambda.Runtime.PYTHON_3_12,
        timeout: cdk.Duration.minutes(1),
        memorySize: 512,
        handler: "lambda_handler",
        index: "app.py",
        entry: `${CommonStack.Path.Root}/${CommonStack.Path.Source.ClinicalTrials}`,
      },
    );

    const clinicalTrialsAction = new bedrock.AgentActionGroup(
      this,
      this.getResourceId("bedrock-action-clinical-trials"),
      {
        actionGroupName: this.getResourceId("bedrock-action-clinical-trials"),
        description: "Use these functions to get information about relevant clinical trials.",
        actionGroupExecutor: {
          lambda: clinicalTrialsLambda,
        },
        actionGroupState: "ENABLED",
        apiSchema: bedrock.ApiSchema.fromAsset(
          `${CommonStack.Path.Root}/${CommonStack.Path.Source.ClinicalTrials}/schema.json`,
        ),
      },
    );

    const agentRole = new iam.Role(this, this.getResourceId("bedrock-agent-role"), {
      assumedBy: new iam.ServicePrincipal("bedrock.amazonaws.com"),
    });
    agentRole.addToPolicy(
      new iam.PolicyStatement({
        actions: ["bedrock:*", "iam:PassRole"],
        resources: ["*"],
      }),
    );

    const clinicalTrialAgentInstructions = readFileSync(
      `${CommonStack.Path.Source.Prompts}/trial_agent_instruction.txt`,
      "utf-8",
    );
    const clinicalTrialAgent = new bedrock.Agent(this, this.getResourceId("bedrock-clinical-trial-agent"), {
      name: this.getResourceId("bedrock-clinical-trial-agent"),
      aliasName: this.getResourceId("bedrock-clinical-trial-agent-alias"),
      description: "Clinical Trial Agent",
      foundationModel: bedrock.BedrockFoundationModel.ANTHROPIC_CLAUDE_3_5_SONNET_V1_0,
      instruction: clinicalTrialAgentInstructions,
      actionGroups: [clinicalTrialsAction],
      existingRole: agentRole,
      enableUserInput: true,
      idleSessionTTL: cdk.Duration.minutes(10),
      shouldPrepareAgent: true,
    });

    const studyProtocolKB = readFileSync(`${CommonStack.Path.Source.Prompts}/protocol_agent_kb.txt`, "utf-8");
    const studyProtocolOrchestration = readFileSync(
      `${CommonStack.Path.Source.Prompts}/protocol_agent_orchestration.txt`,
      "utf-8",
    );
    const studyProtocolAgentInstructions = readFileSync(
      `${CommonStack.Path.Source.Prompts}/protocol_agent_instruction.txt`,
      "utf-8",
    );
    const studyProtocolAgent = new bedrock.Agent(this, this.getResourceId("bedrock-study-protocol-agent"), {
      name: this.getResourceId("bedrock-study-protocol-agent"),
      aliasName: this.getResourceId("bedrock-study-protocol-agent-alias"),
      description: "Study Protocol Agent",
      foundationModel: bedrock.BedrockFoundationModel.ANTHROPIC_CLAUDE_3_5_SONNET_V1_0,
      instruction: studyProtocolAgentInstructions,
      knowledgeBases: [knowledgeBase],
      existingRole: agentRole,
      enableUserInput: true,
      idleSessionTTL: cdk.Duration.minutes(10),
      shouldPrepareAgent: true,
      promptOverrideConfiguration: {
        promptConfigurations: [
          {
            promptType: bedrock.PromptType.KNOWLEDGE_BASE_RESPONSE_GENERATION,
            basePromptTemplate: studyProtocolKB,
            inferenceConfiguration: {
              temperature: 0.0,
              topP: 1,
              topK: 250,
              maximumLength: 4096,
              stopSequences: [],
            },
            promptState: bedrock.PromptState.ENABLED,
            parserMode: bedrock.ParserMode.DEFAULT,
            promptCreationMode: bedrock.PromptCreationMode.OVERRIDDEN,
          },
          {
            promptType: bedrock.PromptType.ORCHESTRATION,
            basePromptTemplate: studyProtocolOrchestration,
            promptState: bedrock.PromptState.ENABLED,
            inferenceConfiguration: {
              temperature: 0.0,
              topP: 1,
              topK: 250,
              maximumLength: 4096,
              stopSequences: ["</invoke>", "</answer>", "</error>"],
            },
            parserMode: bedrock.ParserMode.DEFAULT,
            promptCreationMode: bedrock.PromptCreationMode.OVERRIDDEN,
          },
        ],
      },
    });

    const customResourceRole = new iam.Role(this, this.getResourceId("bedrock-custom-resource-role"), {
      assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
    });
    customResourceRole.addToPolicy(
      new iam.PolicyStatement({
        actions: ["bedrock:*", "iam:PassRole"],
        resources: ["*"],
      }),
    );

    const supervisorAgentInstruction = readFileSync(
      `${CommonStack.Path.Source.Prompts}/supervisor_agent_instruction.txt`,
      "utf-8",
    );
    // Create supervisor agent with agent collaboration enabled via CR, as this is not supported by CFN yet
    const createSupervisorAgent = new cdk.custom_resources.AwsCustomResource(
      this,
      this.getResourceId("bedrock-create-supervisor-agent"),
      {
        functionName: this.getResourceId("bedrock-create-supervisor-agent"),
        resourceType: "Custom::BedrockCreateAgent",
        installLatestAwsSdk: true,
        timeout: cdk.Duration.minutes(5),
        onCreate: {
          service: "@aws-sdk/client-bedrock-agent",
          action: "CreateAgentCommand",
          parameters: {
            agentName: this.getResourceId("bedrock-supervisor-agent"),
            agentResourceRoleArn: agentRole.roleArn,
            description: "Supervisor Agent",
            foundationModel: "anthropic.claude-3-5-sonnet-20240620-v1:0",
            instruction: supervisorAgentInstruction,
            idleSessionTTLInSeconds: 1800,
            agentCollaboration: "SUPERVISOR",
            orchestrationType: "DEFAULT",
          },
          physicalResourceId: cdk.custom_resources.PhysicalResourceId.of(
            this.getResourceId("bedrock-create-supervisor-agent"),
          ),
        },
        onUpdate: {
          service: "@aws-sdk/client-bedrock-agent",
          action: "UpdateAgentCommand",
          parameters: {
            agentId: cdk.custom_resources.PhysicalResourceId.fromResponse("agent.agentId"),
            agentName: this.getResourceId("bedrock-supervisor-agent"),
            agentResourceRoleArn: agentRole.roleArn,
            description: "Supervisor Agent",
            foundationModel: "anthropic.claude-3-5-sonnet-20240620-v1:0",
            instruction: supervisorAgentInstruction,
            idleSessionTTLInSeconds: 1800,
          },
          physicalResourceId: cdk.custom_resources.PhysicalResourceId.of(
            this.getResourceId("bedrock-create-supervisor-agent"),
          ),
        },
        onDelete: {
          service: "@aws-sdk/client-bedrock-agent",
          action: "DeleteAgentCommand",
          parameters: {
            agentId: cdk.custom_resources.PhysicalResourceId.fromResponse("agent.agentId"),
            skipResourceInUseCheck: true,
          },
        },
        role: customResourceRole,
      },
    );
    createSupervisorAgent.node.addDependency(customResourceRole.node.tryFindChild("DefaultPolicy") as iam.CfnPolicy);

    // Skip remaining resources if supervisor agent creation failed
    if (!createSupervisorAgent.getResponseField("agent.agentId")) {
      console.warn(`Failed to create supervisor agent in ${this.stackName}, skipping dependent resources`);
      this.supervisorAgentId = "";
      this.supervisorAgentAliasId = "";
      return;
    }

    // Enable Code Interpreter for Supervisor Agent via CR, as this is not supported by CFN yet
    const enableCodeInterpreter = new cdk.custom_resources.AwsCustomResource(
      this,
      this.getResourceId("bedrock-supervisor-code-interpreter"),
      {
        resourceType: "Custom::BedrockSupervisorCodeInterpreter",
        onCreate: {
          service: "@aws-sdk/client-bedrock-agent",
          action: "CreateAgentActionGroupCommand",
          parameters: {
            actionGroupName: this.getResourceId("bedrock-supervisor-code-interpreter"),
            agentId: createSupervisorAgent.getResponseField("agent.agentId"),
            actionGroupState: "ENABLED",
            agentVersion: "DRAFT",
            parentActionGroupSignature: "AMAZON.CodeInterpreter",
          },
          physicalResourceId: cdk.custom_resources.PhysicalResourceId.of(
            this.getResourceId("bedrock-supervisor-code-interpreter"),
          ),
        },
        role: customResourceRole,
      },
    );
    enableCodeInterpreter.node.addDependency(customResourceRole.node.tryFindChild("DefaultPolicy") as iam.CfnPolicy);
    enableCodeInterpreter.node.addDependency(createSupervisorAgent);

    // Associate Trial Agent to Supervisor Agent via CR, as this is not supported by CFN yet
    const associateTrialAgent = new cdk.custom_resources.AwsCustomResource(
      this,
      this.getResourceId("bedrock-associate-trial-agent"),
      {
        functionName: this.getResourceId("bedrock-associate-trial-agent"),
        resourceType: "Custom::BedrockAssociateAgent",
        installLatestAwsSdk: true,
        timeout: cdk.Duration.minutes(5),
        onCreate: {
          service: "@aws-sdk/client-bedrock-agent",
          action: "AssociateAgentCollaboratorCommand",
          parameters: {
            agentId: createSupervisorAgent.getResponseField("agent.agentId"),
            agentVersion: "DRAFT",
            agentDescriptor: { aliasArn: clinicalTrialAgent.aliasArn },
            collaboratorName: clinicalTrialAgent.name,
            collaborationInstruction: "Use this agent to get information about clinical trials.",
            relayConversationHistory: "TO_COLLABORATOR",
          },
          physicalResourceId: cdk.custom_resources.PhysicalResourceId.of(
            this.getResourceId("bedrock-associate-trial-agent"),
          ),
        },
        role: customResourceRole,
      },
    );
    associateTrialAgent.node.addDependency(customResourceRole.node.tryFindChild("DefaultPolicy") as iam.CfnPolicy);
    associateTrialAgent.node.addDependency(createSupervisorAgent);
    associateTrialAgent.node.addDependency(clinicalTrialAgent);

    const associateProtocolAgent = new cdk.custom_resources.AwsCustomResource(
      this,
      this.getResourceId("bedrock-associate-protocol-agent"),
      {
        functionName: this.getResourceId("bedrock-associate-protocol-agent"),
        resourceType: "Custom::BedrockAssociateAgent",
        installLatestAwsSdk: true,
        timeout: cdk.Duration.minutes(5),
        onCreate: {
          service: "@aws-sdk/client-bedrock-agent",
          action: "AssociateAgentCollaboratorCommand",
          parameters: {
            agentId: createSupervisorAgent.getResponseField("agent.agentId"),
            agentVersion: "DRAFT",
            agentDescriptor: { aliasArn: studyProtocolAgent.aliasArn },
            collaboratorName: studyProtocolAgent.name,
            collaborationInstruction: "Use this agent to get information about medical study protocols.",
            relayConversationHistory: "TO_COLLABORATOR",
          },
          physicalResourceId: cdk.custom_resources.PhysicalResourceId.of(
            this.getResourceId("bedrock-associate-protocol-agent"),
          ),
        },
        role: customResourceRole,
      },
    );
    associateProtocolAgent.node.addDependency(customResourceRole.node.tryFindChild("DefaultPolicy") as iam.CfnPolicy);
    associateProtocolAgent.node.addDependency(createSupervisorAgent);
    associateProtocolAgent.node.addDependency(studyProtocolAgent);

    const prepareSupervisorAgent = new cdk.custom_resources.AwsCustomResource(
      this,
      this.getResourceId("bedrock-prepare-supervisor-agent"),
      {
        resourceType: "Custom::BedrockPrepareSupervisorAgent",
        onCreate: {
          service: "@aws-sdk/client-bedrock-agent",
          action: "PrepareAgentCommand",
          parameters: {
            agentId: createSupervisorAgent.getResponseField("agent.agentId"),
          },
          physicalResourceId: cdk.custom_resources.PhysicalResourceId.of(
            this.getResourceId("bedrock-prepare-supervisor-agent"),
          ),
        },
        onUpdate: {
          service: "@aws-sdk/client-bedrock-agent",
          action: "PrepareAgentCommand",
          parameters: {
            agentId: createSupervisorAgent.getResponseField("agent.agentId"),
          },
          physicalResourceId: cdk.custom_resources.PhysicalResourceId.of(
            this.getResourceId("bedrock-prepare-supervisor-agent"),
          ),
        },
        onDelete: {
          service: "@aws-sdk/client-bedrock-agent",
          action: "DeleteAgentCommand",
          parameters: {
            agentId: createSupervisorAgent.getResponseField("agent.agentId"),
            skipResourceInUseCheck: true,
          },
        },
        role: customResourceRole,
      },
    );
    prepareSupervisorAgent.node.addDependency(customResourceRole.node.tryFindChild("DefaultPolicy") as iam.CfnPolicy);
    prepareSupervisorAgent.node.addDependency(enableCodeInterpreter);
    prepareSupervisorAgent.node.addDependency(associateTrialAgent);
    prepareSupervisorAgent.node.addDependency(associateProtocolAgent);

    const agentAlias = new cdk.aws_bedrock.CfnAgentAlias(this, this.getResourceId("bedrock-supervisor-agent-alias"), {
      agentId: createSupervisorAgent.getResponseField("agent.agentId"),
      agentAliasName: this.getResourceId("bedrock-supervisor-agent-alias"),
      description: "Alias for the Supervisor Agent",
    });
    agentAlias.node.addDependency(prepareSupervisorAgent);

    new cdk.CfnOutput(this, this.getResourceId("bedrock-supervisor-agent-id"), {
      exportName: this.getResourceId("bedrock-supervisor-agent-id"),
      value: createSupervisorAgent.getResponseField("agent.agentId"),
    });
    new cdk.CfnOutput(this, this.getResourceId("bedrock-supervisor-agent-alias-id"), {
      exportName: this.getResourceId("bedrock-supervisor-agent-alias-id"),
      value: agentAlias.attrAgentAliasId,
    });

    this.supervisorAgentId = createSupervisorAgent.getResponseField("agent.agentId");
    this.supervisorAgentAliasId = agentAlias.attrAgentAliasId;
  }
}
