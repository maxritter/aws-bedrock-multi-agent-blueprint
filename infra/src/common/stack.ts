import { readFileSync } from "fs";
import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";

export interface CommonStackProps extends cdk.StackProps {
  appName: string;
}

export abstract class CommonStack extends cdk.Stack {
  private props: CommonStackProps;

  constructor(scope: Construct, id: string, props: CommonStackProps) {
    super(scope, id, props);
    this.props = props;
  }

  addTags(stackName: string, stackCategory: string, tagOptions?: cdk.TagProps) {
    cdk.Tags.of(this).add("stack", stackName, tagOptions);
    cdk.Tags.of(this).add("category", stackCategory, tagOptions);
    cdk.Tags.of(this).add("generatedBy", "cdk", tagOptions);
  }

  getResourceId(resourceName: string): string {
    return CommonStack.generateResourceId(resourceName, this.props);
  }

  getAppName(): string {
    return this.props.appName;
  }

  getRegion(): string {
    if (this.props && this.props.env) {
      return this.props.env.region || "us-east-1";
    }
    return "us-east-1";
  }

  getAvailabilityZones(): string[] {
    return ["us-east-1a", "us-east-1b"];
  }
}

export namespace CommonStack {
  export namespace Path {
    export const Root = "..";

    export enum Source {
      App = "src/app",
      ClinicalTrials = "src/tools/clinicaltrials",
      Protocols = "data/protocols",
      RAGDataSync = "src/resources/datasync.ts",
      Prompts = "src/prompts",
    }
  }

  export function generateResourceId(resourceName: string, props: CommonStackProps) {
    return `${props.appName}-${resourceName}`;
  }

  export function parseRequirementsFile(basePath: string, fileName: string = "requirements.txt"): string[] {
    return readFileSync(`${basePath}/${fileName}`)
      .toString()
      .split("\n")
      .filter((line) => line.length > 0 && !line.startsWith("#"));
  }
}
