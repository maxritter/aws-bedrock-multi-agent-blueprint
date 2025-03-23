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

    const knowledgeBase = new bedrock.VectorKnowledgeBase(this, this.getResourceId("bedrock-knowledge-base"), {
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
        parsingModel: bedrock.BedrockFoundationModel.ANTHROPIC_CLAUDE_3_7_SONNET_V1_0,
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

    const clinicalTrialsAction = new bedrock.AgentActionGroup({
      name: this.getResourceId("bedrock-action-clinical-trials"),
      description: "Use these functions to get information about relevant clinical trials.",
      executor: bedrock.ActionGroupExecutor.fromlambdaFunction(clinicalTrialsLambda),
      enabled: true,
      apiSchema: bedrock.ApiSchema.fromLocalAsset(
        `${CommonStack.Path.Root}/${CommonStack.Path.Source.ClinicalTrials}/schema.json`,
      ),
    });

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
      description: "Clinical Trial Agent",
      foundationModel: bedrock.BedrockFoundationModel.ANTHROPIC_CLAUDE_3_7_SONNET_V1_0,
      instruction: clinicalTrialAgentInstructions,
      actionGroups: [clinicalTrialsAction],
      existingRole: agentRole,
      userInputEnabled: true,
      idleSessionTTL: cdk.Duration.minutes(10),
      shouldPrepareAgent: true,
    });

    const clinicalTrialAgentAlias = new bedrock.AgentAlias(
      this,
      this.getResourceId("bedrock-clinical-trial-agent-alias"),
      {
        agent: clinicalTrialAgent,
        aliasName: this.getResourceId("bedrock-clinical-trial-agent-alias"),
        description: "Alias for the Clinical Trial Agent",
      },
    );

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
      description: "Study Protocol Agent",
      foundationModel: bedrock.BedrockFoundationModel.ANTHROPIC_CLAUDE_3_7_SONNET_V1_0,
      instruction: studyProtocolAgentInstructions,
      knowledgeBases: [knowledgeBase],
      existingRole: agentRole,
      userInputEnabled: true,
      idleSessionTTL: cdk.Duration.minutes(10),
      shouldPrepareAgent: true,
      promptOverrideConfiguration: bedrock.PromptOverrideConfiguration.fromSteps([
        {
          stepType: bedrock.AgentStepType.KNOWLEDGE_BASE_RESPONSE_GENERATION,
          stepEnabled: true,
          customPromptTemplate: studyProtocolKB,
          inferenceConfig: {
            temperature: 0.0,
            topP: 1,
            topK: 250,
            maximumLength: 4096,
            stopSequences: [],
          },
        },
        {
          stepType: bedrock.AgentStepType.ORCHESTRATION,
          stepEnabled: true,
          customPromptTemplate: studyProtocolOrchestration,
          inferenceConfig: {
            temperature: 0.0,
            topP: 1,
            topK: 250,
            maximumLength: 4096,
            stopSequences: ["</invoke>", "</answer>", "</error>"],
          },
        },
      ]),
    });

    const studyProtocolAgentAlias = new bedrock.AgentAlias(
      this,
      this.getResourceId("bedrock-study-protocol-agent-alias"),
      {
        agent: studyProtocolAgent,
        aliasName: this.getResourceId("bedrock-study-protocol-agent-alias"),
        description: "Alias for the Study Protocol Agent",
      },
    );

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

    const supervisorAgent = new bedrock.Agent(this, this.getResourceId("bedrock-supervisor-agent"), {
      name: this.getResourceId("bedrock-supervisor-agent"),
      description: "Supervisor Agent",
      foundationModel: bedrock.BedrockFoundationModel.ANTHROPIC_CLAUDE_3_7_SONNET_V1_0,
      instruction: supervisorAgentInstruction,
      idleSessionTTL: cdk.Duration.minutes(30),
      existingRole: agentRole,
      agentCollaboration: bedrock.AgentCollaboratorType.SUPERVISOR,
      agentCollaborators: [
        new bedrock.AgentCollaborator({
          agentAlias: clinicalTrialAgentAlias,
          collaborationInstruction: "Use this agent to get information about clinical trials.",
          collaboratorName: clinicalTrialAgent.name,
          relayConversationHistory: true,
        }),
        new bedrock.AgentCollaborator({
          agentAlias: studyProtocolAgentAlias,
          collaborationInstruction: "Use this agent to get information about medical study protocols.",
          collaboratorName: studyProtocolAgent.name,
          relayConversationHistory: true,
        }),
      ],
      codeInterpreterEnabled: true,
      shouldPrepareAgent: true,
    });
    const supervisorAgentAlias = new bedrock.AgentAlias(this, this.getResourceId("bedrock-supervisor-agent-alias"), {
      agent: supervisorAgent,
      aliasName: this.getResourceId("bedrock-supervisor-agent-alias"),
      description: "Alias for the Supervisor Agent",
    });

    new cdk.CfnOutput(this, this.getResourceId("bedrock-supervisor-agent-id"), {
      exportName: this.getResourceId("bedrock-supervisor-agent-id"),
      value: supervisorAgent.agentId,
    });
    new cdk.CfnOutput(this, this.getResourceId("bedrock-supervisor-agent-alias-id"), {
      exportName: this.getResourceId("bedrock-supervisor-agent-alias-id"),
      value: supervisorAgentAlias.aliasId,
    });

    this.supervisorAgentId = supervisorAgent.agentId;
    this.supervisorAgentAliasId = supervisorAgentAlias.aliasId;
  }
}
