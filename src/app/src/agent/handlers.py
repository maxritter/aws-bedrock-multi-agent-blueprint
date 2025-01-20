"""Handlers for processing agent traces and events."""

import json
import math
import os
import re
from typing import Any, Dict, List, Optional, Union, cast

import boto3
import streamlit as st
from mypy_boto3_bedrock_agent_runtime.type_defs import (
    CitationTypeDef,
    FilePartTypeDef,
    OutputFileTypeDef,
    ResponseStreamTypeDef,
    RetrievedReferenceTypeDef,
    TracePartTypeDef,
    TraceTypeDef,
)

from .types import AgentStats


def handle_citations(citations: List[CitationTypeDef], langfuse_span) -> None:
    """Handle and display knowledge base citations."""
    for citation in citations:
        retrieved_references = citation.get("retrievedReferences", [])
        if not retrieved_references:
            continue

        with st.expander("Knowledge Base", False):
            text = citation.get("generatedResponsePart", {}).get("textResponsePart", {}).get("text", "")
            if text:
                st.write(text)
                st.divider()
                display_citation_references(retrieved_references, langfuse_span)


def display_citation_references(references: List[RetrievedReferenceTypeDef], langfuse_span) -> None:
    """Display knowledge base citation references."""
    if not references:
        return

    valid_uris = []
    for ref in references:
        if uri := get_reference_uri(ref):
            valid_uris.append(uri)

    if valid_uris:
        st.write("References:")
        for uri in sorted(set(valid_uris)):
            st.write(f"- {uri}")
        langfuse_span.event(
            name="agent-citation-references",
            metadata={"uri_list": valid_uris},
        )


def get_reference_uri(reference: RetrievedReferenceTypeDef) -> Optional[str]:
    """Extract URI from a reference, handling different location types."""
    location = reference.get("location", {})
    if "s3Location" in location:
        return location["s3Location"].get("uri")
    return None


def handle_tool_invocation(action_input: Dict[str, Any], langfuse_span) -> None:
    """Handle and display tool invocation details."""
    tool_name = ""
    if "function" in action_input:
        tool_name = action_input["function"]
    elif "apiPath" in action_input:
        tool_name = action_input["apiPath"]

    with st.expander(f"Tool Invocation ({tool_name})", False):
        param_data = {
            "Parameter Name": [p["name"] for p in action_input["parameters"]],
            "Parameter Value": [p["value"] for p in action_input["parameters"]],
        }
        st.table(param_data)

        langfuse_span.event(
            name="agent-tool-invocation",
            metadata={"action_input": action_input},
        )


def handle_model_invocation_input(model_input: Dict[str, Any], langfuse_span) -> None:
    """Handle and model invocation input details."""
    langfuse_span.event(
        name="agent-model-input",
        metadata={"prompt_text": model_input.get("text")},
    )


def handle_model_invocation_output(model_output: Dict[str, Any], stats: AgentStats, langfuse_span) -> None:
    """Handle and model invocation output details."""
    if "usage" in model_output["metadata"]:
        update_stats_from_usage(model_output["metadata"]["usage"], stats)

    langfuse_span.event(
        name="agent-model-output",
        metadata={"raw_resp": model_output["rawResponse"]["content"]},
    )


def handle_agent_collaborator(collab_input: Dict[str, Any], langfuse_span) -> None:
    """Handle multi-agent collaborator invocation."""
    collaborator_name = collab_input.get("agentCollaboratorName")
    collaborator_input = collab_input.get("input", {}).get("text")
    with st.expander(f"Sub-Agent Input ({collaborator_name})", False):
        st.write(collaborator_input)
        langfuse_span.event(
            name="agent-agent-collaborator",
            metadata={"collab_input": collab_input, "collaborator_name": collaborator_name},
        )


def handle_knowledge_base_lookup(kb_input: Dict[str, Any], langfuse_span) -> None:
    """Handle knowledge base lookup invocation."""
    kb_id = kb_input.get("knowledgeBaseId")
    kb_query = kb_input.get("text")
    with st.expander(f"Knowledge Base Query ({kb_id})", False):
        st.write(kb_query)
        langfuse_span.event(
            name="agent-knowledge-base-lookup",
            metadata={"kb_id": kb_id, "kb_query": kb_query},
        )


def handle_invocation_input(invocation_input: Dict[str, Any], langfuse_span) -> None:
    """Handle different types of invocation inputs."""
    invocation_type = invocation_input.get("invocationType")
    if not isinstance(invocation_type, str):
        return

    handlers = {
        "AGENT_COLLABORATOR": lambda: handle_agent_collaborator(
            invocation_input.get("agentCollaboratorInvocationInput", {}),
            langfuse_span,
        ),
        "ACTION_GROUP": lambda: handle_tool_invocation(
            invocation_input.get("actionGroupInvocationInput", {}),
            langfuse_span,
        ),
        "KNOWLEDGE_BASE": lambda: handle_knowledge_base_lookup(
            invocation_input.get("knowledgeBaseLookupInput", {}),
            langfuse_span,
        ),
    }
    if handler := handlers.get(invocation_type):
        handler()


def handle_agent_collaborator_observation(output: Dict[str, Any], langfuse_span) -> None:
    """Handle agent collaborator observation output."""
    collaborator_name = output.get("agentCollaboratorName")
    collaborator_response = output.get("output", {}).get("text")
    with st.expander(f"Sub-Agent Response ({collaborator_name})", False):
        st.write(collaborator_response)
        langfuse_span.event(
            name="agent-agent-collaborator-response",
            metadata={"collaborator_name": collaborator_name, "collaborator_response": collaborator_response},
        )


def handle_action_group_observation(output: Dict[str, Any], langfuse_span) -> None:
    """Handle action group observation output."""
    with st.expander("Tool Response", False):
        text = output.get("actionGroupInvocationOutput", {}).get("text", "")
        try:
            json_data = json.loads(text)
            st.json(json_data)
        except json.JSONDecodeError:
            st.text(text)
        langfuse_span.event(
            name="agent-action-group-response",
            metadata={"output_text": text},
        )


def handle_knowledge_base_observation(kb_output: Dict[str, Any], langfuse_span) -> None:
    """Handle knowledge base observation output."""
    with st.expander("Knowledge Base Results", False):
        for ref in kb_output.get("retrievedReferences", []):
            st.write(f"Content: {ref.get('content', {}).get('text')}")
            st.write(f"Source: {ref.get('location', {}).get('s3Location', {}).get('uri')}")
            st.divider()
        langfuse_span.event(
            name="agent-knowledge-base-response",
            metadata={"kb_output": kb_output},
        )


def handle_reprompt_observation(response: Dict[str, Any], langfuse_span) -> None:
    """Handle reprompt observation output."""
    with st.expander("Reprompt", True):
        st.warning(f"Source: {response.get('source')}")
        st.write(f"Message: {response.get('text')}")
        langfuse_span.event(
            name="agent-reprompt-response",
            metadata={"response": response},
        )


def handle_observation(observation: Dict[str, Any], langfuse_span) -> None:
    """Handle different types of observations."""
    observation_type = observation.get("type")
    if not isinstance(observation_type, str):
        return

    handlers = {
        "AGENT_COLLABORATOR": lambda: handle_agent_collaborator_observation(
            observation.get("agentCollaboratorInvocationOutput", {}),
            langfuse_span,
        ),
        "ACTION_GROUP": lambda: handle_action_group_observation(
            observation,
            langfuse_span,
        ),
        "KNOWLEDGE_BASE": lambda: handle_knowledge_base_observation(
            observation.get("knowledgeBaseLookupOutput", {}),
            langfuse_span,
        ),
        "REPROMPT": lambda: handle_reprompt_observation(
            observation.get("repromptResponse", {}),
            langfuse_span,
        ),
    }
    if handler := handlers.get(observation_type):
        handler()


def handle_reasoning_step(
    rationale_text: str,
    stats: AgentStats,
    langfuse_span,
    agent_name: Optional[str] = "",
    chain_length: int = 0,
) -> None:
    """Handle and display reasoning steps."""
    if chain_length <= 1:
        stats.step_counter = math.floor(stats.step_counter + 1)
        step_title = f"Supervisor Reasoning (Step {round(stats.step_counter, 2)})"
    else:
        stats.step_counter += 0.1
        step_title = f"Sub-Agent Reasoning (Step {round(stats.step_counter, 2)}, Agent {agent_name})"

    with st.expander(step_title, False):
        st.write(rationale_text)
        langfuse_span.event(
            name="agent-reasoning-step",
            metadata={
                "step_number": stats.step_counter,
                "agent_name": agent_name,
                "rationale_text": rationale_text,
            },
        )


def update_stats_from_usage(usage: Dict[str, int], stats: AgentStats) -> None:
    """Update statistics from usage data."""
    stats.input_tokens += usage["inputTokens"]
    stats.output_tokens += usage["outputTokens"]


def handle_preprocessing_trace(trace: Dict[str, Any], stats: AgentStats, langfuse_span) -> None:
    """Handle and display preprocessing trace information."""
    if "modelInvocationInput" in trace:
        handle_model_invocation_input(trace["modelInvocationInput"], langfuse_span)
    with st.expander("Preprocessing Step", False):
        output = trace["modelInvocationOutput"]
        if "parsedResponse" in output:
            st.write("*Parsed Response*")
            st.write(f"Valid Input: {output['parsedResponse']['isValid']}")
            st.write(f"Rationale: {output['parsedResponse']['rationale']}")
            langfuse_span.event(
                name="agent-preprocessing-preprocessing-step",
                metadata={"output": output},
            )

        if "metadata" in output and "usage" in output["metadata"]:
            update_stats_from_usage(output["metadata"]["usage"], stats)


def handle_orchestration_trace(
    trace: Dict[str, Any],
    event_trace_dict: Dict[str, Any],
    agent_name: Optional[str],
    stats: AgentStats,
    langfuse_span,
) -> None:
    """Handle and display orchestration trace information."""
    if "modelInvocationInput" in trace:
        handle_model_invocation_input(trace["modelInvocationInput"], langfuse_span)

    if "modelInvocationOutput" in trace:
        handle_model_invocation_output(trace["modelInvocationOutput"], stats, langfuse_span)

    if "rationale" in trace:
        chain_length = len(event_trace_dict.get("callerChain", []))
        handle_reasoning_step(trace["rationale"]["text"], stats, langfuse_span, agent_name, chain_length)

    if "invocationInput" in trace:
        input_data = trace["invocationInput"]
        handle_invocation_input(input_data, langfuse_span)

        if "codeInterpreterInvocationInput" in input_data:
            handle_code_interpreter(input_data["codeInterpreterInvocationInput"], langfuse_span)

    if "observation" in trace:
        observation = trace["observation"]
        handle_observation(observation, langfuse_span)


def handle_postprocessing_trace(trace: Dict[str, Any], stats: AgentStats, langfuse_span) -> None:
    """Handle and display postprocessing trace information."""
    if "modelInvocationInput" in trace:
        handle_model_invocation_input(trace["modelInvocationInput"], langfuse_span)
    with st.expander("Postprocessing Step", False):
        if "modelInvocationOutput" in trace:
            output = trace["modelInvocationOutput"]
            if "parsedResponse" in output:
                st.write("*Final Response*")
                st.write(output["parsedResponse"]["text"])
                langfuse_span.event(
                    name="agent-postprocessing-postprocessing-step",
                    metadata={"output": output},
                )

            if "metadata" in output and "usage" in output["metadata"]:
                update_stats_from_usage(output["metadata"]["usage"], stats)


def handle_failure_trace(trace: Dict[str, Any], langfuse_span) -> None:
    """Handle and display failure trace information."""
    with st.expander("Failure", True):
        st.error(f"Failure Reason: {trace.get('failureReason', 'Unknown')}")
        langfuse_span.event(
            name="agent-failure-trace",
            level="ERROR",
            metadata={"trace": trace},
        )


def handle_policy_assessments(assessment: Dict[str, Any], langfuse_span) -> None:
    """Handle and display policy assessments."""
    if "topicPolicy" in assessment:
        st.write("Topic Policy:")
        for topic in assessment["topicPolicy"].get("topics", []):
            st.write(f"- {topic['name']} ({topic['type']}): {topic['action']}")

    if "contentPolicy" in assessment:
        st.write("Content Policy:")
        for filter in assessment["contentPolicy"].get("filters", []):
            st.write(f"- {filter['type']} ({filter['confidence']}): {filter['action']}")

    if "wordPolicy" in assessment:
        st.write("Word Policy:")
        for word in assessment["wordPolicy"].get("customWords", []):
            st.write(f"- {word['match']}: {word['action']}")
        for word_list in assessment["wordPolicy"].get("managedWordLists", []):
            st.write(f"- {word_list['type']} ({word_list['match']}): {word_list['action']}")

    if "sensitiveInformationPolicy" in assessment:
        st.write("Sensitive Information Policy:")
        for entity in assessment["sensitiveInformationPolicy"].get("piiEntities", []):
            st.write(f"- {entity['type']} ({entity['match']}): {entity['action']}")
        for regex in assessment["sensitiveInformationPolicy"].get("regexes", []):
            st.write(f"- {regex['name']}: {regex['action']}")

    langfuse_span.event(
        name="agent-policy-assessments",
        metadata={"assessment": assessment},
    )


def handle_guardrail_trace(trace: Dict[str, Any], langfuse_span) -> None:
    """Handle and display guardrail trace information."""
    with st.expander("Guardrail Assessment", False):
        action = trace.get("action", "NONE")
        st.write(f"Action: {action}")

        for assessment_type in ["inputAssessments", "outputAssessments"]:
            assessments = trace.get(assessment_type, [])
            if assessments:
                st.write(f"\n*{assessment_type}*")
                for assessment in assessments:
                    handle_policy_assessments(assessment, langfuse_span)


def handle_routing_classifier_output(routing_output: Dict[str, Any], langfuse_span) -> None:
    """Handle and display routing classifier output."""
    with st.expander("Routing Decision", False):
        st.write(f"Raw Response: {routing_output.get('rawResponse')}")
        st.write("*Routing Metadata*")
        metadata = routing_output.get("metadata", {})
        st.write(f"Input Tokens: {metadata.get('inputTokens')}")
        st.write(f"Output Tokens: {metadata.get('outputTokens')}")
        if parsed_response := routing_output.get("routerClassifierParsedResponse"):
            st.write("\n*Parsed Routing Response*")
            st.write(parsed_response)
        langfuse_span.event(
            name="agent-routing-classifier-output",
            metadata={"routing_output": routing_output},
        )


def get_images(files_event: FilePartTypeDef) -> List[OutputFileTypeDef]:
    """Extract image files from the files event."""
    files_list = files_event.get("files", [])
    if not files_list:
        return []

    return [f for f in files_list if f.get("type", "").startswith("image/")]


def display_images(image_files: List[OutputFileTypeDef]) -> List[Dict[str, Any]]:
    """Process and store image files for display.

    Returns a list of image data dictionaries that can be stored in session state.
    """
    if not image_files:
        return []

    processed_images = []
    unique_images: Dict[str, OutputFileTypeDef] = {}
    for file in image_files:
        if filename := file.get("name"):
            unique_images[filename] = file

    for file in unique_images.values():
        image_bytes = file.get("bytes")
        if isinstance(image_bytes, bytes):
            try:
                processed_images.append({"name": file.get("name", ""), "bytes": image_bytes})
            except Exception as e:
                st.error(f"Failed to process image {file.get('name', '')}: {str(e)}")

    return processed_images


def get_html_files(files_event: FilePartTypeDef) -> List[OutputFileTypeDef]:
    """Extract HTML files from the files event."""
    files_list = files_event.get("files", [])
    if not files_list:
        return []

    return [f for f in files_list if f.get("type", "") == "text/html"]


def display_html_files(html_files: List[OutputFileTypeDef]) -> List[Dict[str, Any]]:
    """Process and store HTML files for display.

    Returns a list of HTML data dictionaries that can be stored in session state.
    """
    if not html_files:
        return []

    processed_html = []
    unique_html: Dict[str, OutputFileTypeDef] = {}
    for file in html_files:
        if filename := file.get("name"):
            unique_html[filename] = file

    for file in unique_html.values():
        html_bytes = file.get("bytes")
        if isinstance(html_bytes, bytes):
            try:
                html_content = html_bytes.decode("utf-8")
                processed_html.append({"name": file.get("name", ""), "content": html_content})
            except Exception as e:
                st.error(f"Failed to process HTML {file.get('name', '')}: {str(e)}")

    return processed_html


def make_fully_cited_answer(orig_answer: str, event: ResponseStreamTypeDef) -> str:
    """Process the answer to include citations."""
    citations = event.get("chunk", {}).get("attribution", {}).get("citations", [])
    if not citations:
        return orig_answer

    patterns = [
        r"\n\n<sources>\n\d+\n</sources>\n\n",
        "<sources><REDACTED></sources>",
        "<sources></sources>",
    ]
    cleaned_text = orig_answer
    for pattern in patterns:
        cleaned_text = re.sub(pattern, "", cleaned_text)

    fully_cited_answer = ""
    curr_citation_idx = 0
    for citation in citations:
        start = citation["generatedResponsePart"]["textResponsePart"]["span"]["start"] - (curr_citation_idx + 1)
        end = citation["generatedResponsePart"]["textResponsePart"]["span"]["end"] - (curr_citation_idx + 2) + 4

        refs = citation.get("retrievedReferences", [])
        ref_url = refs[0].get("location", {}).get("s3Location", {}).get("uri", "") if refs else ""

        if not ref_url:
            return cleaned_text

        cited_text = cleaned_text[start:end] + " [" + ref_url + "] "

        if curr_citation_idx == 0:
            answer_prefix = cleaned_text[:start]
            fully_cited_answer = answer_prefix + cited_text
        else:
            fully_cited_answer += cited_text

        curr_citation_idx += 1

    return fully_cited_answer


def handle_routing_classifier_trace(trace: Dict[str, Any], stats: AgentStats, langfuse_span) -> None:
    """Handle and display routing classifier trace information."""
    with st.expander("Routing Classification", False):
        if "modelInvocationInput" in trace:
            st.write("Classifying request for potential direct routing")

        if "modelInvocationOutput" in trace:
            output = trace["modelInvocationOutput"]
            if "metadata" in output and "usage" in output["metadata"]:
                update_stats_from_usage(output["metadata"]["usage"], stats)

            if "rawResponse" in output:
                try:
                    raw_resp = json.loads(output["rawResponse"]["content"])
                    classification = raw_resp.get("content", [{}])[0].get("text", "")
                    classification = classification.replace("<a>", "").replace("</a>", "")
                    st.write(f"Classification Result: {classification}")
                    langfuse_span.event(
                        name="agent-routing-classifier-output",
                        metadata={"classification": classification},
                    )
                except (json.JSONDecodeError, KeyError, IndexError):
                    st.write("Could not parse routing classification response")


def handle_code_interpreter(input_data: Dict[str, Any], langfuse_span) -> None:
    """Handle code interpreter invocation input."""
    with st.expander("Code Interpreter", False):
        if code := input_data.get("code"):
            langfuse_span.event(
                name="agent-code-interpreter",
                metadata={"code": code},
            )
            st.code(code, language="python")


def process_trace_event(
    trace_obj: Union[TraceTypeDef, Dict[str, Any]],
    stats: AgentStats,
    event_trace: Union[TracePartTypeDef, Dict[str, Any]],
    langfuse_span,
) -> None:
    """Process and handle trace events."""
    trace_dict = cast(Dict[str, Any], trace_obj)
    event_trace_dict = cast(Dict[str, Any], event_trace)

    agent_name = "Supervisor"
    if "callerChain" in event_trace_dict:
        chain = event_trace_dict["callerChain"]
        if len(chain) > 1:
            sub_agent_alias_arn = chain[1]["agentAliasArn"]
            sub_agent_id = sub_agent_alias_arn.split("/")[1] if sub_agent_alias_arn else None
            if sub_agent_id:
                try:
                    agent_name = (
                        boto3.client("bedrock-agent", region_name=os.getenv("BEDROCK_REGION", "eu-central-1"))
                        .get_agent(agentId=sub_agent_id)
                        .get("agent")
                        .get("agentName")
                    )
                except Exception as ex:
                    st.error(f"Failed to get agent name for sub-agent {sub_agent_id}: {str(ex)}")

    if "routingClassifierTrace" in trace_dict:
        handle_routing_classifier_trace(trace_dict["routingClassifierTrace"], stats, langfuse_span)

    if "failureTrace" in trace_dict:
        handle_failure_trace(trace_dict["failureTrace"], langfuse_span)

    if "guardrailTrace" in trace_dict:
        handle_guardrail_trace(trace_dict["guardrailTrace"], langfuse_span)

    if "preProcessingTrace" in trace_dict:
        handle_preprocessing_trace(trace_dict["preProcessingTrace"], stats, langfuse_span)

    elif "orchestrationTrace" in trace_dict:
        handle_orchestration_trace(
            trace_dict["orchestrationTrace"],
            event_trace_dict,
            agent_name,
            stats,
            langfuse_span,
        )

    elif "postProcessingTrace" in trace_dict:
        handle_postprocessing_trace(trace_dict["postProcessingTrace"], stats, langfuse_span)
