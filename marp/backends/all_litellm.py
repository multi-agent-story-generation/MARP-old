import os
import re
from typing import List

import litellm
from tenacity import retry, stop_after_attempt, wait_random_exponential

from .base import IntelligenceBackend
from ..message import Message, SYSTEM_NAME

# Default config follows the OpenAI playground
DEFAULT_TEMPERATURE = 1.1
# DEFAULT_MAX_TOKENS = 500
DEFAULT_MAX_TOKENS = 4096
# DEFAULT_MODEL = "gpt-3.5-turbo"
# DEFAULT_MODEL = "gpt-4-0613"
model_names = ["chat-bison-001",
               "text-bison-001",
               "embedding-gecko-001",
               "gemini-pro",
               "gemini-pro-vision",
               "embedding-001",
               "aqa"]
DEFAULT_MODEL = "gemini-pro"

END_OF_MESSAGE = "<EOS>"  # End of message token specified by us
STOP = ("<|endoftext|>", END_OF_MESSAGE)  # End of sentence token
BASE_PROMPT = f"The messages should always end with the token {END_OF_MESSAGE}."
litellm.drop_params = True
# litellm.set_verbose = True

class AutoChat(IntelligenceBackend):
    """
    Interface to the ChatGPT style model with system, user, assistant roles separation
    """
    stateful = False
    type_name = "gemini-pro-chat"

    def __init__(self, temperature: float = DEFAULT_TEMPERATURE, max_tokens: int = DEFAULT_MAX_TOKENS,
                 model: str = DEFAULT_MODEL, merge_other_agents_as_one_user: bool = True, **kwargs):
        """
        instantiate the GeminiProChat backend
        args:
            temperature: the temperature of the sampling
            max_tokens: the maximum number of tokens to sample
            model: the model to use
            merge_other_agents_as_one_user: whether to merge messages from other agents as one user message
        """
        super().__init__(temperature=temperature, max_tokens=max_tokens, model=model,
                         merge_other_agents_as_one_user=merge_other_agents_as_one_user, **kwargs)

        self.temperature = temperature
        self.max_tokens = max_tokens
        self.model = model
        self.merge_other_agent_as_user = merge_other_agents_as_one_user

    @retry(stop=stop_after_attempt(1), wait=wait_random_exponential(min=1, max=60))
    def _get_response(self, messages):
        completion = litellm.completion(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            stop=STOP
        )

        response = completion.choices[0]['message']['content']
        response = response.strip()
        return response

    def query(self, agent_name: str, role_desc: str, history_messages: List[Message], global_prompt: str = None,
              request_msg: Message = None,
              action_prompt="Now you speak and act", *args, **kwargs) -> str:
        """
        format the input and call the ChatGPT/GPT-4 API
        args:
            agent_name: the name of the agent
            role_desc: the description of the role of the agent
            env_desc: the description of the environment
            history_messages: the history of the conversation, or the observation for the agent
            request_msg: the request from the system to guide the agent's next response
        """
        is_agent_message = True
        # Merge the role description and the global prompt as the system prompt for the agent
        if global_prompt:  # Prepend the global prompt if it exists
            # system_prompt = f"You are a helpful assistant.\n{global_prompt.strip()}\n{BASE_PROMPT}\n\nYour name is {agent_name}.\n\nYour role:{role_desc}"
            system_prompt = f"{global_prompt.strip()}\n{BASE_PROMPT}\n\nYour name is {agent_name}.\n\nYour role:{role_desc}"
        else:
            # system_prompt = f"You are a helpful assistant. Your name is {agent_name}.\n\nYour role:{role_desc}\n\n{BASE_PROMPT}"
            system_prompt = f"Your name is {agent_name}.\n\nYour role:{role_desc}\n\n{BASE_PROMPT}"
        # 'You are a helpful assistant.\nYou are in a university classroom and it is Natural Language Processing module. You start by introducing themselves.\nThe messages always end with the token <EOS>.\n\nYour name is Professor.\n\nYour role:You are Prof. Alpha, a knowledgeable professor in NLP. Your answer will concise and accurate. The answers should be less than 100 words.'

        all_messages = [(SYSTEM_NAME, system_prompt)]
        for msg in history_messages:
            if msg.agent_name == SYSTEM_NAME:
                all_messages.append((SYSTEM_NAME, msg.content))
            else:  # non-system messages are suffixed with the end of message token
                all_messages.append((msg.agent_name, f"{msg.content}{END_OF_MESSAGE}"))

        if request_msg:
            all_messages.append((SYSTEM_NAME, request_msg.content))
        else:  # The default request message that reminds the agent its role and instruct it to speak
            # all_messages.append((SYSTEM_NAME, f"{action_prompt}, {agent_name} {END_OF_MESSAGE}"))

            # all_messages.append((SYSTEM_NAME, f"Now you speak and act, {agent_name}.{END_OF_MESSAGE}"))

            all_messages.append((SYSTEM_NAME, f"You are {agent_name}. {action_prompt}.{END_OF_MESSAGE}"))

            # all_messages.append((SYSTEM_NAME, f"Now you can speak and act. please try to limit your speak and act content to be fewer than 5 sentences.{END_OF_MESSAGE}"))

        messages = []
        for i, msg in enumerate(all_messages):
            if i == 0:
                assert msg[0] == SYSTEM_NAME  # The first message should be from the system
                messages.append({"role": "system", "content": msg[1]})
            else:
                if msg[0] == agent_name:
                    messages.append({"role": "assistant", "content": msg[1]})
                else:
                    if messages[-1]["role"] == "user":  # last message is from user
                        if self.merge_other_agent_as_user:
                            messages[-1]["content"] = f"{messages[-1]['content']}\n\n[{msg[0]}]: {msg[1]}"
                        else:
                            messages.append({"role": "user", "content": f"[{msg[0]}]: {msg[1]}"})
                    elif messages[-1]["role"] == "assistant":  # consecutive assistant messages
                        # Merge the assistant messages
                        messages[-1]["content"] = f"{messages[-1]['content']}\n{msg[1]}"
                    elif messages[-1]["role"] == "system":
                        messages.append({"role": "user", "content": f"[{msg[0]}]: {msg[1]}"})
                    else:
                        raise ValueError(f"Invalid role: {messages[-1]['role']}")
        # pdb.set_trace()
        # print("[MESSAGES]: ", messages)
        response = self._get_response(messages, *args, **kwargs)

        # Remove the agent name if the response starts with it
        response = re.sub(rf"^\s*\[.*]:", "", response).strip()
        response = re.sub(rf"^\s*{re.escape(agent_name)}\s*:", "", response).strip()

        # Remove the tailing end of message token
        response = re.sub(rf"{END_OF_MESSAGE}$", "", response).strip()
        print("[{}]: {}".format(agent_name, response))
        return response
