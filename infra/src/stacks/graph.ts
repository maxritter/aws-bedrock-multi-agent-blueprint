import { Construct } from "constructs";
import { CommonStack, CommonStackProps } from "../common/stack";
import { bedrock, neptune } from "@cdklabs/generative-ai-cdk-constructs";

export class GraphStack extends CommonStack {
  public readonly graphStore: neptune.NeptuneGraph;

  constructor(scope: Construct, id: string, props: CommonStackProps) {
    super(scope, id, props);

    this.graphStore = new neptune.NeptuneGraph(this, this.getResourceId("graph-store"), {
      graphName: this.getResourceId("graph-store"),
      vectorSearchDimension: bedrock.BedrockFoundationModel.TITAN_EMBED_TEXT_V2_512.vectorDimensions,
      replicaCount: 0, //No replicas needed for a single-region graph
      provisionedMemoryNCUs: 16, //Minimum allowed by Neptune
      publicConnectivity: false,
      deletionProtection: false,
    });
  }
}
