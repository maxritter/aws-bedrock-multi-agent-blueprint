import * as cdk from "aws-cdk-lib";
import * as cognito from "aws-cdk-lib/aws-cognito";
import { Construct } from "constructs";
import { CommonStack, CommonStackProps } from "../common/stack";

export class AuthStack extends CommonStack {
  public readonly userPoolId: string;
  public readonly userPoolClientId: string;
  public readonly userPoolClientSecret: string;

  constructor(scope: Construct, id: string, props: CommonStackProps) {
    super(scope, id, props);

    const userPool = new cognito.UserPool(this, this.getResourceId("auth-user-pool"), {
      userPoolName: this.getResourceId("auth-user-pool"),
    });

    const userPoolClient = userPool.addClient(this.getResourceId("auth-user-pool-client"), {
      userPoolClientName: this.getResourceId("auth-user-pool-client"),
      generateSecret: true,
    });

    this.userPoolId = userPool.userPoolId;
    this.userPoolClientId = userPoolClient.userPoolClientId;
    this.userPoolClientSecret = userPoolClient.userPoolClientSecret.toString();

    new cdk.CfnOutput(this, this.getResourceId("auth-user-pool-id"), {
      exportName: this.getResourceId("auth-user-pool-id"),
      value: userPool.userPoolId,
    });

    new cdk.CfnOutput(this, this.getResourceId("auth-user-pool-client-id"), {
      exportName: this.getResourceId("auth-user-pool-client-id"),
      value: userPoolClient.userPoolClientId,
    });
  }
}
