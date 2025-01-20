import * as cdk from "aws-cdk-lib";
import { CommonStack, CommonStackProps } from "./common/stack";
import { VectorStack } from "./stacks/vector";
import { BedrockStack } from "./stacks/bedrock";
import { AuthStack } from "./stacks/auth";
import { AppStack } from "./stacks/app";

const app = new cdk.App();

const account = process.env.CDK_DEPLOY_ACCOUNT || process.env.CDK_DEFAULT_ACCOUNT;
const props: CommonStackProps = {
  env: {
    account: account,
    region: "eu-central-1",
  },
  appName: "multi-agent-blueprint",
};

const vectorStackId = CommonStack.generateResourceId("vector-stack", props);
const vectorStack = new VectorStack(app, vectorStackId, {
  ...props,
  stackName: vectorStackId,
});

const bedrockStackId = CommonStack.generateResourceId("bedrock-stack", props);
const bedrockStack = new BedrockStack(app, bedrockStackId, {
  ...props,
  stackName: bedrockStackId,
  vectorStore: vectorStack.vectorStore,
});
bedrockStack.addDependency(vectorStack);

const authStackId = CommonStack.generateResourceId("auth-stack", props);
const authStack = new AuthStack(app, authStackId, { ...props, stackName: authStackId });

const appStackId = CommonStack.generateResourceId("app-stack", props);
const appStack = new AppStack(app, appStackId, {
  ...props,
  stackName: appStackId,
  ragBucket: bedrockStack.ragBucket,
  authUserPoolId: authStack.userPoolId,
  authUserPoolClientId: authStack.userPoolClientId,
  authUserPoolClientSecret: authStack.userPoolClientSecret,
  supervisorAgentId: bedrockStack.supervisorAgentId,
  supervisorAgentAliasId: bedrockStack.supervisorAgentAliasId,
});
appStack.addDependency(authStack);
appStack.addDependency(vectorStack);
appStack.addDependency(bedrockStack);
