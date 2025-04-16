const { awscdk } = require("projen");
const cdkVersion = "2.189.0";
const project = new awscdk.AwsCdkTypeScriptApp({
  cdkVersion,
  name: "aws-bedrock-multi-agent-blueprint",
  defaultReleaseBranch: "master",
  github: false,
  deps: [
    "@cdklabs/generative-ai-cdk-constructs@0.1.302",
    "@aws-sdk/client-bedrock-agent@3.787.0",
    "constructs@10.3.0",
    "@aws-cdk/aws-lambda-python-alpha@2.181.1-alpha.0",
    "cdk-ecr-deployment@3.0.70",
    "aws-lambda@1.0.7",
    "@types/aws-lambda@8.10.146",
  ],
  eslintOptions: {
    prettier: true,
  },
  prettier: true,
  prettierOptions: {
    overrides: [{ files: "*", options: { printWidth: 120 } }],
  },
  context: {
    "@aws-cdk/customresources:installLatestAwsSdkDefault": false,
  },
  gitignore: ["outputs.json"],
});
project.addDevDeps("eslint-plugin-prettier@^5.2.1");
project.synth();
