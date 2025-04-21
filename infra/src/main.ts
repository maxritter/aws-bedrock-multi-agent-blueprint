import * as cdk from "aws-cdk-lib";
import { CommonStack, CommonStackProps } from "./common/stack";
import { GraphStack } from "./stacks/graph";
import { BedrockStack } from "./stacks/bedrock";
import { AuthStack } from "./stacks/auth";
import { AppStack } from "./stacks/app";

const app = new cdk.App();

const account = process.env.CDK_DEPLOY_ACCOUNT || process.env.CDK_DEFAULT_ACCOUNT;
const props: CommonStackProps = {
  env: {
    account: account,
    region: "us-east-1",
  },
  appName: "multi-agent-blueprint",
};

const graphStackId = CommonStack.generateResourceId("graph-stack", props);
const graphStack = new GraphStack(app, graphStackId, {
  ...props,
  stackName: graphStackId,
});

const bedrockStackId = CommonStack.generateResourceId("bedrock-stack", props);
const bedrockStack = new BedrockStack(app, bedrockStackId, {
  ...props,
  stackName: bedrockStackId,
  graphStore: graphStack.graphStore,
});
bedrockStack.addDependency(graphStack);

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
appStack.addDependency(bedrockStack);
appStack.addDependency(graphStack);
