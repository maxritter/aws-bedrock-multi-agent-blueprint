import { amazonaurora } from "@cdklabs/generative-ai-cdk-constructs";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import { Construct } from "constructs";
import { CommonStack, CommonStackProps } from "../common/stack";

export class VectorStack extends CommonStack {
  public readonly vectorStore: amazonaurora.AmazonAuroraVectorStore;

  constructor(scope: Construct, id: string, props: CommonStackProps) {
    super(scope, id, props);

    const vpc = new ec2.Vpc(this, this.getResourceId("vector-vpc"), {
      vpcName: this.getResourceId("vector-vpc"),
      availabilityZones: this.getAvailabilityZones(),
      natGateways: 0,
      subnetConfiguration: [
        {
          name: this.getResourceId("vector-private"),
          subnetType: ec2.SubnetType.PRIVATE_ISOLATED,
          cidrMask: 28,
        },
      ],
    });

    this.vectorStore = new amazonaurora.AmazonAuroraVectorStore(this, this.getResourceId("vector-store"), {
      clusterId: this.getResourceId("vector-store"),
      embeddingsModelVectorDimension: 512,
      vpc: vpc,
      databaseName: "vectorDB",
      schemaName: "bedrock_integration",
      tableName: "bedrock_kb",
      vectorField: "embedding",
      textField: "chunks",
      metadataField: "metadata",
      primaryKeyField: "id",
    });
  }
}
