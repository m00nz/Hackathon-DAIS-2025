# Databricks notebook source
# MAGIC %pip install -U -qqqq mlflow langchain langgraph==0.3.4 databricks-langchain pydantic databricks-agents unitycatalog-langchain[databricks] uv
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

from typing import Any, Generator, Optional, Sequence, Union

import pandas as pd
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
#from langchain_databricks import ChatDatabricks
from databricks.sdk import WorkspaceClient
import os


import mlflow
from databricks_langchain import (
    ChatDatabricks,
    VectorSearchRetrieverTool,
    DatabricksFunctionClient,
    UCFunctionToolkit,
    set_uc_function_client,
)
from langchain_core.language_models import LanguageModelLike
from langchain_core.runnables import RunnableConfig, RunnableLambda
from langchain_core.tools import BaseTool
from langgraph.graph import END, StateGraph
from langgraph.graph.graph import CompiledGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt.tool_node import ToolNode
from mlflow.langchain.chat_agent_langgraph import ChatAgentState, ChatAgentToolNode
from mlflow.pyfunc import ChatAgent
from mlflow.types.agent import (
    ChatAgentChunk,
    ChatAgentMessage,
    ChatAgentResponse,
    ChatContext,
)
mlflow.set_registry_uri("databricks-uc")
mlflow.langchain.autolog()

client = DatabricksFunctionClient()
set_uc_function_client(client)

# COMMAND ----------


# Define your LLM endpoint and system prompt
LLM_ENDPOINT_NAME = "databricks-claude-sonnet-4"
llm = ChatDatabricks(endpoint=LLM_ENDPOINT_NAME)
system_prompt = """"""


# Tools
tools = []
uc_tool_names = [
    {
        "type": "function",
        "function": {
            "name": "get_wellness_centers",
            "description": "Retrieves nearby health and wellness services.",
            "parameters": { },
        },
    }
]
uc_toolkit = UCFunctionToolkit(function_names=["polar_dais.polar.get_wellness_centers"])
tools.extend(uc_toolkit.tools)


## Define agent logic
def create_tool_calling_agent(
    model: LanguageModelLike,
    tools: Union[Sequence[BaseTool], ToolNode],
    system_prompt: Optional[str] = None,
) -> CompiledGraph:
    model = model.bind_tools(tools)

    # Define the function that determines which node to go to
    def should_continue(state: ChatAgentState):
        messages = state["messages"]
        last_message = messages[-1]
        # If there are function calls, continue. else, end
        if last_message.get("tool_calls"):
            return "continue"
        else:
            return "end"

    if system_prompt:
        preprocessor = RunnableLambda(
            lambda state: [{"role": "system", "content": system_prompt}]
            + state["messages"]
        )
    else:
        preprocessor = RunnableLambda(lambda state: state["messages"])
    model_runnable = preprocessor | model

    def call_model(
        state: ChatAgentState,
        config: RunnableConfig,
    ):
        response = model_runnable.invoke(state, config)

        return {"messages": [response]}

    workflow = StateGraph(ChatAgentState)

    workflow.add_node("agent", RunnableLambda(call_model))
    workflow.add_node("tools", ChatAgentToolNode(tools))

    workflow.set_entry_point("agent")
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "continue": "tools",
            "end": END,
        },
    )
    workflow.add_edge("tools", "agent")

    return workflow.compile()


class LangGraphChatAgent(ChatAgent):
    def __init__(self, agent: CompiledStateGraph):
        self.agent = agent

    def predict(
        self,
        messages: list[ChatAgentMessage],
        context: Optional[ChatContext] = None,
        custom_inputs: Optional[dict[str, Any]] = None,
    ) -> ChatAgentResponse:
        request = {"messages": self._convert_messages_to_dict(messages)}

        messages = []
        for event in self.agent.stream(request, stream_mode="updates"):
            for node_data in event.values():
                messages.extend(
                    ChatAgentMessage(**msg) for msg in node_data.get("messages", [])
                )
        return ChatAgentResponse(messages=messages)

    def predict_stream(
        self,
        messages: list[ChatAgentMessage],
        context: Optional[ChatContext] = None,
        custom_inputs: Optional[dict[str, Any]] = None,
    ) -> Generator[ChatAgentChunk, None, None]:
        request = {"messages": self._convert_messages_to_dict(messages)}
        for event in self.agent.stream(request, stream_mode="updates"):
            for node_data in event.values():
                yield from (
                    ChatAgentChunk(**{"delta": msg}) for msg in node_data["messages"]
                )


# Create the agent object, and specify it as the agent object to use when
# loading the agent back for inference via mlflow.models.set_model()



# COMMAND ----------

# import pandas as pd
# from mlflow.models import infer_signature
# mlflow.set_registry_uri("databricks-uc")
# # Example: Input and output data
# input_data = pd.DataFrame({"text": ["What is AI?", "Explain LangChain"]})
# output_data = pd.DataFrame({"response": ["AI is...", "LangChain is..."]})
# # Infer the signature
# signature = infer_signature(input_data, output_data)

mlflow.set_registry_uri("databricks-uc")
mlflow.langchain.autolog()

with mlflow.start_run():
    mlflow.pyfunc.log_model(
        artifact_path="langchain_model",
        python_model="chatbot_agent.py"
    )

autolog_run = mlflow.last_active_run()
model_uri = "runs:/{}/model".format(autolog_run.info.run_id)
mlflow.register_model(model_uri, "polar_dais.polar.wellness_chatbot")

# COMMAND ----------

from mlflow.models import infer_signature
params = {"temperature": 0.5, "suppress_tokens": [101, 102]}

agent = create_tool_calling_agent(llm, tools, system_prompt)
AGENT = LangGraphChatAgent(agent)
mlflow.models.set_model(AGENT)
mlflow.end_run()
model ="polar_dais.polar.wellness_chatbot"
with mlflow.start_run() as run:
    mlflow.sklearn.log_model(model, artifact_path="model", input_example={'question': "what is ml ?"}, signature=infer_signature(params))
    run_id = run.info.run_id
model_uri = f"runs:/{run_id}/model"


model_uri = f"runs:/{run_id}/model"

registered_model = mlflow.register_model(model_uri=model_uri, name=model)

# COMMAND ----------

agent = create_tool_calling_agent(llm, tools, system_prompt)
AGENT = LangGraphChatAgent(agent)
mlflow.models.set_model(AGENT)
mlflow.end_run()
import pandas as pd
from mlflow.models import infer_signature
mlflow.set_registry_uri("databricks-uc")

model ="polar_dais.polar.wellness_chatbot"

input_example = pd.DataFrame(, columns=['sepal_length', 'sepal_width', 'petal_length', 'petal_width'])
signature = infer_signature(input_example, model.predict(input_example))
with mlflow.start_run() as run:
    mlflow.sklearn.log_model(model, artifact_path="model", input_example={'Question': "what is ml ?"}, signature=mlflow.models.infer_signature())
    run_id = run.info.run_id
model_uri = f"runs:/{run_id}/model"


model_uri = f"runs:/{run_id}/model"

registered_model = mlflow.register_model(model_uri=model_uri, name=model)

# COMMAND ----------

from mlflow.models import infer_signature
from typing import Any, Generator, Optional, Sequence, Union

import pandas as pd
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
#from langchain_databricks import ChatDatabricks
from databricks.sdk import WorkspaceClient
import os


import mlflow
from databricks_langchain import (
    ChatDatabricks,
    VectorSearchRetrieverTool,
    DatabricksFunctionClient,
    UCFunctionToolkit,
    set_uc_function_client,
)
from langchain_core.language_models import LanguageModelLike
from langchain_core.runnables import RunnableConfig, RunnableLambda
from langchain_core.tools import BaseTool
from langgraph.graph import END, StateGraph
from langgraph.graph.graph import CompiledGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt.tool_node import ToolNode
from mlflow.langchain.chat_agent_langgraph import ChatAgentState, ChatAgentToolNode
from mlflow.pyfunc import ChatAgent
from mlflow.types.agent import (
    ChatAgentChunk,
    ChatAgentMessage,
    ChatAgentResponse,
    ChatContext,
)
mlflow.set_registry_uri("databricks-uc")
mlflow.langchain.autolog()

client = DatabricksFunctionClient()
set_uc_function_client(client)

# Define your LLM endpoint and system prompt
LLM_ENDPOINT_NAME = "databricks-meta-llama-3-1-8b-instruct" #databricks-meta-llama-3-3-70b-instruct" #"databricks-claude-sonnet-4"
llm = ChatDatabricks(endpoint=LLM_ENDPOINT_NAME)
system_prompt = """"""


# Tools
tools = []
uc_tool_names = [
    {
        "type": "function",
        "function": {
            "name": "get_wellness_centers",
            "description": "Retrieves nearby health and wellness services.",
            "parameters": { },
        },
    }
]
uc_toolkit = UCFunctionToolkit(function_names=["polar_dais.polar.get_wellness_centers"])
tools.extend(uc_toolkit.tools)


## Define agent logic
def create_tool_calling_agent(
    model: LanguageModelLike,
    tools: Union[Sequence[BaseTool], ToolNode],
    system_prompt: Optional[str] = None,
) -> CompiledGraph:
    model = model.bind_tools(tools)

    # Define the function that determines which node to go to
    def should_continue(state: ChatAgentState):
        messages = state["messages"]
        last_message = messages[-1]
        # If there are function calls, continue. else, end
        if last_message.get("tool_calls"):
            return "continue"
        else:
            return "end"

    if system_prompt:
        preprocessor = RunnableLambda(
            lambda state: [{"role": "system", "content": system_prompt}]
            + state["messages"]
        )
    else:
        preprocessor = RunnableLambda(lambda state: state["messages"])
    model_runnable = preprocessor | model

    def call_model(
        state: ChatAgentState,
        config: RunnableConfig,
    ):
        response = model_runnable.invoke(state, config)

        return {"messages": [response]}

    workflow = StateGraph(ChatAgentState)

    workflow.add_node("agent", RunnableLambda(call_model))
    workflow.add_node("tools", ChatAgentToolNode(tools))

    workflow.set_entry_point("agent")
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "continue": "tools",
            "end": END,
        },
    )
    workflow.add_edge("tools", "agent")

    return workflow.compile()


class LangGraphChatAgent(ChatAgent):
    def __init__(self, agent: CompiledStateGraph):
        self.agent = agent

    def predict(
        self,
        messages: list[ChatAgentMessage],
        context: Optional[ChatContext] = None,
        custom_inputs: Optional[dict[str, Any]] = None,
    ) -> ChatAgentResponse:
        request = {"messages": self._convert_messages_to_dict(messages)}

        messages = []
        for event in self.agent.stream(request, stream_mode="updates"):
            for node_data in event.values():
                messages.extend(
                    ChatAgentMessage(**msg) for msg in node_data.get("messages", [])
                )
        return ChatAgentResponse(messages=messages)

    def predict_stream(
        self,
        messages: list[ChatAgentMessage],
        context: Optional[ChatContext] = None,
        custom_inputs: Optional[dict[str, Any]] = None,
    ) -> Generator[ChatAgentChunk, None, None]:
        request = {"messages": self._convert_messages_to_dict(messages)}
        for event in self.agent.stream(request, stream_mode="updates"):
            for node_data in event.values():
                yield from (
                    ChatAgentChunk(**{"delta": msg}) for msg in node_data["messages"]
                )

agent = create_tool_calling_agent(llm, tools, system_prompt)
AGENT = LangGraphChatAgent(agent)
mlflow.models.set_model(AGENT)

infer_signature_data = {
  "signature": {
    "inputs": [{"name": "input", "type": "string"}],
    "outputs": [{"name": "output", "type": "string"}],
    "params": [{"name": "message", "type": "float", "default": "what is ml ?", "shape": None },
    {"name": "response", "type": "string", "default": "machine learning", "shape": None}    ]
    }
}

params = {"message": "what is ml ?", "response": "machine learning"}

signature = infer_signature(["input"], ["output"], params=params)

agent = create_tool_calling_agent(llm, tools, system_prompt)
AGENT = LangGraphChatAgent(agent)
mlflow.models.set_model(AGENT)
mlflow.end_run()
model ="polar_dais.polar.wellness_chatbot_eol"
with mlflow.start_run() as run:
    mlflow.sklearn.log_model(model, artifact_path="model", input_example={"message": "what is ml ?","response":"machine learning"}, signature=signature)
    run_id = run.info.run_id

model_uri = f"runs:/{run_id}/model"
registered_model = mlflow.register_model(model_uri=model_uri, name=model)
