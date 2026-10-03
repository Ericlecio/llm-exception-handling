import argparse
import logging
import os
import sys
import time
from typing import List, Dict

import pandas as pd
from anthropic import Anthropic, RateLimitError as AnthropicRateLimitError
from openai import OpenAI, RateLimitError as OpenAIRateLimitError
from google import genai
from google.genai import errors as GenAIErrors
from dotenv import load_dotenv

# Configure basic logging - will be updated based on verbose flag
logger = logging.getLogger(__name__)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
logger.addHandler(handler)
logger.setLevel(logging.WARNING)  # Default to WARNING, can be changed to INFO with -v

# Initialize Anthropic, OpenAI, and Gemini clients
load_dotenv()
_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", "dummy_key"))
_openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", "dummy_key"))

_gemini_keys = []
for i in range(1, 10): # Busca no .env por GEMINI_KEY_1 até GEMINI_KEY_9
    key = os.getenv(f"GEMINI_KEY_{i}")
    if key:
        _gemini_keys.append(key)

# Fallback para manter compatibilidade com GEMINI_API_KEY antiga
if not _gemini_keys and os.getenv("GEMINI_API_KEY"):
    _gemini_keys.append(os.getenv("GEMINI_API_KEY"))

if not _gemini_keys:
    _gemini_keys = ["dummy_key"]

_gemini_clients = [genai.Client(api_key=k) for k in _gemini_keys]
_current_gemini_index = 0


# Custom exception for rate limits
class RateLimitExceeded(Exception):
    """Raised when API rate limit is reached"""
    pass


# Define constants for code examples to avoid duplication
EXAMPLE_FLOAT_CONVERSION = (
    "def can_convert_to_float(string):\n    float(string)\n    return True"
)
EXAMPLE_FILE_READ = "def read_file_binary(file_path: str) -> str:\n    with open(file_path, 'rb') as file:\n        return file.read().decode('utf-8')"
EXAMPLE_DIVISION = "def divide_numbers(a, b):\n    result = a / b\n    return result"
EXAMPLE_DICT_ACCESS = "def get_user_data(user_dict, key):\n    return user_dict[key]"
EXAMPLE_SIMPLE_FUNCTION = "def get_tokenizer(cls, pretrained_name=None, **kwargs):\n    kwargs.update(cls.special_tokens_map)\n    return cls.tokenizer_class.from_pretrained(pretrained_name, **kwargs)"
EXAMPLE_BACKEND_CALL = "def call(self, x):\n    return backend.nn.silu(x)"

DEFAULT_PROJECT = "combined"
DEFAULT_MODELS = ["claude-haiku-4-5", "gpt-4o-mini", "gemini-3-flash-preview"]


def prompt_default(function, binary_answers=True):
    return "\n".join(
        [
            "Does this Python snippet require exception handling?",
            "<code>",
            function,
            "</code>",
            "Answer with exactly yes or no in lowercase. No explanation.",
        ]
    )


def prompt_1_shot(function):
    example_code = EXAMPLE_DIVISION
    example_answer = "yes"
    return "\n".join(
        [
            "Example:",
            "<code>",
            example_code,
            "</code>",
            f"Answer: {example_answer}",
            "",
            "Does the next Python snippet require exception handling?",
            "<code>",
            function,
            "</code>",
            "Respond with exactly yes or no in lowercase. No explanation.",
        ]
    )


def prompt_few_shot(function, num_shots=2):
    examples = [
        (EXAMPLE_FILE_READ, "yes"),
        (EXAMPLE_FLOAT_CONVERSION, "yes"),
        (EXAMPLE_BACKEND_CALL, "no"),
    ]
    parts = ["Review the examples and mirror the answer style."]
    for code_text, example_answer in examples[:num_shots]:
        parts.extend(["<code>", code_text, "</code>", f"Answer: {example_answer}", ""])
    parts.extend(
        [
            "Does the next Python snippet require exception handling?",
            "<code>",
            function,
            "</code>",
            "Reply with exactly yes or no in lowercase. No explanation.",
        ]
    )
    return "\n".join(parts).strip()


def prompt_cot(function):
    return "\n".join(
        [
            "Assess whether the Python snippet needs exception handling.",
            "<code>",
            function,
            "</code>",
            "Think through possible failure points silently and respond with only yes or no in lowercase.",
        ]
    )


def prompt_task2_default(function):
    return "\n".join(
        [
            "Add the minimal required try/except block to this Python snippet.",
            "Keep all unaffected lines exactly as they appear.",
            "Return only the updated code wrapped in <code> tags.",
            "<code>",
            function,
            "</code>",
        ]
    )


def prompt_task2_1_shot(function):
    example_code = EXAMPLE_DIVISION
    example_output = "\n".join(
        [
            "def divide_numbers(a, b):",
            "    try:",
            "        result = a / b",
            "    except ZeroDivisionError:",
            "        print('Division by zero is not allowed')",
            "        return None",
            "    return result",
        ]
    )
    return "\n".join(
        [
            "Example transformation:",
            "<code>",
            example_code,
            "</code>",
            "Output:",
            "<code>",
            example_output,
            "</code>",
            "",
            "Apply the same update to the snippet below.",
            "Return only the modified code wrapped in <code> tags.",
            "<code>",
            function,
            "</code>",
        ]
    )


def prompt_task2_few_shot(function, num_shots=2):
    examples = [
        (
            EXAMPLE_FILE_READ,
            "\n".join(
                [
                    "def read_file_binary(file_path: str) -> str:",
                    "    try:",
                    "        with open(file_path, 'rb') as file:",
                    "            return file.read().decode('utf-8')",
                    "    except FileNotFoundError:",
                    "        print('File not found')",
                    "        return ''",
                ]
            ),
        ),
        (
            EXAMPLE_FLOAT_CONVERSION,
            "\n".join(
                [
                    "def can_convert_to_float(string):",
                    "    try:",
                    "        float(string)",
                    "        return True",
                    "    except ValueError:",
                    "        return False",
                ]
            ),
        ),
        (
            EXAMPLE_DICT_ACCESS,
            "\n".join(
                [
                    "def get_user_data(user_dict, key):",
                    "    try:",
                    "        return user_dict[key]",
                    "    except KeyError:",
                    "        return None",
                ]
            ),
        ),
    ]
    parts = ["Examples of minimal try/except insertion:"]
    for code_text, updated_code in examples[:num_shots]:
        parts.extend(
            [
                "<code>",
                code_text,
                "</code>",
                "Updated:",
                "<code>",
                updated_code,
                "</code>",
                "",
            ]
        )
    parts.extend(
        [
            "Now edit the snippet below in the same style.",
            "Return only the modified code wrapped in <code> tags.",
            "<code>",
            function,
            "</code>",
        ]
    )
    return "\n".join(parts).strip()


def prompt_task2_cot(function):
    return "\n".join(
        [
            "Identify where the Python snippet could fail and insert the minimal try/except block.",
            "<code>",
            function,
            "</code>",
            "Plan silently and reply with only the updated code wrapped in <code> tags.",
        ]
    )


def prompt_task3_default(function):
    return "\n".join(
        [
            "List the specific exception names that should be handled for this Python snippet.",
            "<code>",
            function,
            "</code>",
            "Return only the exception names, comma-separated if needed, with no extra text.",
        ]
    )


def prompt_task3_1_shot(function):
    example_code = EXAMPLE_DIVISION
    example_output = "ZeroDivisionError"
    return "\n".join(
        [
            "You are auditing Python code to identify the PRIMARY exception class worth handling.",
            "Study the worked example and copy the response style EXACTLY.",
            "Example:",
            "<code>",
            example_code,
            "</code>",
            "Reasoning: The divisor `b` might be zero, which raises ZeroDivisionError.",
            f"Answer: {example_output}",
            "",
            "Now analyse the next snippet. Identify the MOST CRITICAL built-in or library exception that the executed statements may raise.",
            "CRITICAL INSTRUCTIONS:",
            "1. Return ONLY ONE exception class name - nothing else.",
            "2. Do not include any code blocks, explanations, or reasoning.",
            "3. Do not include the word 'Answer:' or any labels.",
            "4. Return exactly what you see in the example answer format: just the exception name.",
            # "5. Skip generic names such as Exception unless the code explicitly raises them.",
            "5. Do not add punctuation, commas, or any other characters.",
            "<code>",
            function,
            "</code>",
            "Your response must be EXACTLY ONE WORD - the exception class name. Nothing more.",
        ]
    )


def prompt_task3_few_shot(function, num_shots=2):
    examples = [
        (EXAMPLE_FILE_READ, "FileNotFoundError"),
        (EXAMPLE_FLOAT_CONVERSION, "ValueError"),
        (EXAMPLE_DICT_ACCESS, "KeyError"),
    ]
    parts = ["Examples mapping snippets to exception names:"]
    for code_text, exception_name in examples[:num_shots]:
        parts.extend(
            [
                "<code>",
                code_text,
                "</code>",
                f"Answer: {exception_name}",
                "",
            ]
        )
    parts.extend(
        [
            "Provide the exception names for the snippet below.",
            "<code>",
            function,
            "</code>",
            "Return only the exception names, comma-separated if needed, with no extra text.",
        ]
    )
    return "\n".join(parts).strip()


def prompt_task3_cot(function):
    return "\n".join(
        [
            "Determine the exception names that should be handled for this Python snippet.",
            "<code>",
            function,
            "</code>",
            "Think through the failure modes silently and reply with only the exception names, comma-separated if needed, no extra text.",
        ]
    )


def prompt_task4_default(function):
    return "\n".join(
        [
            "Write only the exception handling block for the risky part of this Python snippet.",
            "Reuse the snippet's identifiers and message style to stay close to the reference solution.",
            "Return exactly one <code> block containing only the except clause with proper indentation.",
            "<code>",
            function,
            "</code>",
        ]
    )


def prompt_task4_1_shot(function):
    example_code = EXAMPLE_DIVISION
    example_output = "\n".join(
        [
            "except ZeroDivisionError:",
            "    print('Division by zero is not allowed')",
        ]
    )
    return "\n".join(
        [
            "Example:",
            "<code>",
            example_code,
            "</code>",
            "Handler:",
            "<code>",
            example_output,
            "</code>",
            "",
            "Write the handler for the snippet below.",
            "Only return exactly one <code> block containing only the except clause with proper indentation.",
            "<code>",
            function,
            "</code>",
        ]
    )


def prompt_task4_few_shot(function, num_shots=2):
    examples = [
        (
            EXAMPLE_FILE_READ,
            "\n".join(
                [
                    "except FileNotFoundError:",
                    "    print('File not found')",
                ]
            ),
        ),
        (
            EXAMPLE_FLOAT_CONVERSION,
            "\n".join(
                [
                    "except ValueError:",
                    "    return False",
                ]
            ),
        ),
        (
            EXAMPLE_DICT_ACCESS,
            "\n".join(
                [
                    "except KeyError:",
                    "    return None",
                ]
            ),
        ),
    ]
    parts = ["Examples of snippet to handler mapping:"]
    for code_text, handler in examples[:num_shots]:
        parts.extend(
            [
                "<code>",
                code_text,
                "</code>",
                "Handler:",
                "<code>",
                handler,
                "</code>",
                "",
            ]
        )
    parts.extend(
        [
            "Write the handler for the snippet below.",
            "Ensure the block mirrors the snippet's naming and keeps four-space indentation.",
            "Return exactly one <code> block containing only the except clause.",
            "<code>",
            function,
            "</code>",
        ]
    )
    return "\n".join(parts).strip()


def prompt_task4_cot(function):
    return "\n".join(
        [
            "Decide which exception block best matches this Python snippet.",
            "<code>",
            function,
            "</code>",
            "Plan silently so the handler aligns closely with the reference style, then reply with a single <code> block containing only the except clause and four-space indentation.",
        ]
    )

def prompt_task4_qg_default(function):
    return "\n".join(
        [
            "Write only the exception handling block for the risky part of this Python snippet.",
            "Reuse the snippet's identifiers and message style to stay close to the reference solution.",
            "CRITICAL QUALITY RULES:",
            "1. Do not catch the generic 'Exception' or 'BaseException' classes (Avoid Pylint W0718: broad-exception-caught). Catch a specific exception.",
            "2. If you raise a new exception inside the except block, you MUST chain it to the original error using the 'from' keyword (Avoid Pylint W0707: raise-missing-from).",
            "Return exactly one <code> block containing only the except clause with proper indentation.",
            "<code>",
            function,
            "</code>",
        ]
    )

def prompt_task4_qg_cot(function):
    return "\n".join(
        [
            "Decide which exception block best matches this Python snippet.",
            "CRITICAL QUALITY RULES:",
            "1. Do not catch the generic 'Exception' or 'BaseException' classes (Avoid Pylint W0718). Catch a specific exception.",
            "2. If you raise a new exception inside the except block, you MUST chain it using the 'from' keyword (Avoid Pylint W0707).",
            "<code>",
            function,
            "</code>",
            "Plan silently ensuring the handler aligns with the reference style AND strictly follows the quality rules. Then reply with a single <code> block containing only the except clause and four-space indentation.",
        ]
    )


def collect_df(task, project: str = DEFAULT_PROJECT):
    df = pd.read_csv("data/balanced_sample.csv")
    df["project"] = project

    if task == "task1":  # 700
        pos_samples = df[df["n_try_except"] == 1]
        neg_samples = df[df["n_try_except"] == 0].sample(
            n=len(pos_samples), random_state=42
        )

        return (
            pd.concat([pos_samples, neg_samples], ignore_index=True)
            .sample(frac=1)
            .reset_index(drop=True)
        )
    else:
        return df[df["n_try_except"] == 1].reset_index(drop=True)


def _call_claude(prompt: str, model_name: str) -> Dict[str, any]:
    try:
        response = _client.messages.create(
            model=model_name,
            max_tokens=10050,
            messages=[{"role": "user", "content": prompt}],
        )
    except AnthropicRateLimitError as e:
        raise RateLimitExceeded(f"Claude API rate limited: {e}") from e

    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens

    return {
        "text": response.content[0].text,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }


def _call_openai(prompt: str, model_name: str) -> Dict[str, any]:
    try:
        response = _openai_client.chat.completions.create(
            model=model_name,
            max_tokens=10050,
            temperature=0.7,
            messages=[{"role": "user", "content": prompt}],
        )
    except OpenAIRateLimitError as e:
        raise RateLimitExceeded(f"OpenAI API rate limited: {e}") from e

    input_tokens = response.usage.prompt_tokens
    output_tokens = response.usage.completion_tokens

    return {
        "text": response.choices[0].message.content,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }


def _call_gemini(prompt: str, model_name: str) -> Dict[str, any]:
    """
    Call Gemini API using Key Rotation logic with Auto-Pruning for dead keys.
    """
    from google.genai import types as GenAITypes
    global _current_gemini_index, _gemini_clients

    if not model_name.startswith("models/"):
        model_name = f"models/{model_name}"

    if not _gemini_clients:
        raise RateLimitExceeded("ERRO FATAL: Nenhuma chave do Gemini válida restante.")

    tentativas = 0
    while tentativas < len(_gemini_clients):
        _current_gemini_index = _current_gemini_index % len(_gemini_clients)
        client = _gemini_clients[_current_gemini_index]

        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=GenAITypes.GenerateContentConfig(
                    temperature=0.7,
                ),
            )
            
            input_tokens = response.usage_metadata.prompt_token_count or 0
            output_tokens = response.usage_metadata.candidates_token_count or 0
            text = response.text if response.text is not None else ""
            
            return {
                "text": text,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            }

        except GenAIErrors.APIError as e:
            if e.code == 403:
                logger.error(f"[!] Chave revogada (403). A remover esta chave da lista...")
                _gemini_clients.pop(_current_gemini_index)
                if not _gemini_clients:
                    raise RateLimitExceeded("Todas as suas chaves foram bloqueadas definitivamente (403).")
                continue 
            
            elif e.code == 429:
                logger.warning(f"[!] Limite da chave atingido (429). Trocando de chave...")
                _current_gemini_index = (_current_gemini_index + 1) % len(_gemini_clients)
                tentativas += 1
                continue 
            
            raise

    raise RateLimitExceeded(f"Todas as {len(_gemini_clients)} chaves válidas esgotaram a sua cota simultaneamente (429).")


def call_llm(prompt: str, model_name: str) -> Dict[str, any]:
    if "claude" in model_name.lower():
        return _call_claude(prompt, model_name)
    elif "gpt" in model_name.lower():
        return _call_openai(prompt, model_name)
    elif "gemini" in model_name.lower():
        return _call_gemini(prompt, model_name)
    else:
        raise ValueError(f"Unknown model: {model_name}")


# Define prompt functions for tasks
TASKS = {
    "task1": {
        "style-default": prompt_default,
        "style-1-shot": prompt_1_shot,
        "style-few-shot": prompt_few_shot,
        "style-cot": prompt_cot,
    },
    "task2": {
        "style-default": prompt_task2_default,
        "style-1-shot": prompt_task2_1_shot,
        "style-few-shot": prompt_task2_few_shot,
        "style-cot": prompt_task2_cot,
    },
    "task3": {
        "style-default": prompt_task3_default,
        "style-1-shot": prompt_task3_1_shot,
        "style-few-shot": prompt_task3_few_shot,
        "style-cot": prompt_task3_cot,
    },
    "task4": {
        "style-default": prompt_task4_default,
        "style-1-shot": prompt_task4_1_shot,
        "style-few-shot": prompt_task4_few_shot,
        "style-cot": prompt_task4_cot,
        "style-qg-default": prompt_task4_qg_default,
        "style-qg-cot": prompt_task4_qg_cot,
    },
}


def sanitize_for_filename(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "-" for ch in value)


def save_results_to_csv(df, task, prompt_type, project, model_label):
    output_dir = os.path.join(os.getcwd(), "llm", "output")
    os.makedirs(output_dir, exist_ok=True)
    filename = f"{project}_{model_label}_{task}_{prompt_type}_results.csv"
    output_file = os.path.join(output_dir, filename)
    df.to_csv(output_file, index=False)
    logger.info(f"Results saved to {output_file}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run LLM exception mining experiments."
    )
    parser.add_argument(
        "--tasks",
        nargs="+",
        choices=list(TASKS.keys()),
        help="Subset of tasks to run (default: all tasks).",
    )
    parser.add_argument(
        "--task",
        choices=list(TASKS.keys()),
        help="Run only this single task (overrides --tasks).",
    )
    parser.add_argument(
        "--prompt-types",
        nargs="+",
        choices=sorted({prompt for prompts in TASKS.values() for prompt in prompts}),
        help="Subset of prompt styles to run (default: all styles).",
    )
    parser.add_argument(
        "--models",
        nargs="+",
        help="One or more Claude model names (default: claude-haiku-4-5).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Optional limit on the number of rows processed per task.",
    )
    parser.add_argument(
        "--project",
        default=DEFAULT_PROJECT,
        help="Project label used in the output filenames (default: combined).",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging (shows response status, JSON, and generation time).",
    )
    parser.add_argument(
        "--start-task",
        choices=list(TASKS.keys()),
        help="Start from this task and rotate through remaining tasks (default: task1).",
    )
    parser.add_argument(
        "--start-prompt",
        help="Start from this prompt style within the start-task (e.g., 'style-1-shot'). Only used with --start-task.",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    if args.verbose:
        logger.setLevel(logging.INFO)

    models_to_run: List[str] = args.models or DEFAULT_MODELS

    if args.task:
        tasks_to_run = [args.task]
    else:
        tasks_to_run = args.tasks or list(TASKS.keys())

    prompt_types_filter = set(args.prompt_types) if args.prompt_types else None

    if args.start_task:
        all_tasks = list(TASKS.keys())
        if args.start_task in all_tasks:
            start_idx = all_tasks.index(args.start_task)
            tasks_to_run = all_tasks[start_idx:] + all_tasks[:start_idx]
        else:
            logger.warning(f"Task {args.start_task} not found, using default order")

    start_prompt = None
    if args.start_task and args.start_prompt:
        if args.start_prompt in TASKS[args.start_task]:
            start_prompt = args.start_prompt
        else:
            logger.warning(
                f"Prompt {args.start_prompt} not found in {args.start_task}, starting from first prompt"
            )

    df_result = pd.DataFrame()

    try:
        for model in models_to_run:
            model_label = sanitize_for_filename(
                model.split("/")[-1] if "/" in model else model
            )
            print(f"\nProcessing with model: {model}")
            df_model = pd.DataFrame()

            for task in tasks_to_run:
                print(f"Processing {task}...")
                prompt_functions = TASKS[task]

                prompts_to_run = list(prompt_functions.items())
                if task == args.start_task and start_prompt:
                    prompt_keys = list(prompt_functions.keys())
                    if start_prompt in prompt_keys:
                        start_idx = prompt_keys.index(start_prompt)
                        rotated_keys = prompt_keys[start_idx:] + prompt_keys[:start_idx]
                        prompts_to_run = [(k, prompt_functions[k]) for k in rotated_keys]

                for prompt_type, prompt_func in prompts_to_run:
                    if prompt_types_filter and prompt_type not in prompt_types_filter:
                        continue

                    output = []
                    input_tokens_list = []
                    output_tokens_list = []
                    
                    df = collect_df(task, project=args.project)
                    if args.limit is not None:
                        df = df.head(args.limit)

                    existing_results = {}
                    output_dir = os.path.join(os.getcwd(), "llm", "output")
                    filename = f"{args.project}_{model_label}_{task}_{prompt_type}_results.csv"
                    output_file = os.path.join(output_dir, filename)
                    
                    if os.path.exists(output_file):
                        try:
                            df_existing = pd.read_csv(output_file)
                            for idx, row_ext in df_existing.iterrows():
                                ans = row_ext.get("llm_response")
                                out_tok = row_ext.get("output_tokens", 0)
                                if pd.notna(ans) and str(ans).strip() != "" and out_tok > 0:
                                    existing_results[idx] = {
                                        "text": str(ans),
                                        "input_tokens": row_ext.get("input_tokens", 0),
                                        "output_tokens": out_tok
                                    }
                            logger.info(f"Encontradas {len(existing_results)} linhas já processadas. Retomando...")
                        except Exception as e:
                            logger.warning(f"Não foi possível ler o CSV existente. Ignorando retomada: {e}")

                    for index, row in df.iterrows():
                        call_count = int(index) + 1
                        
                        if index in existing_results:
                            print(f"Pulando linha {call_count} de {len(df)} (Já processada com sucesso)")
                            res = existing_results[index]
                            output.append(res["text"])
                            input_tokens_list.append(res["input_tokens"])
                            output_tokens_list.append(res["output_tokens"])
                            continue

                        print(f"Calling {call_count} of {len(df)} rows for {prompt_type} prompt of {task}")
                        
                        if row["n_try_except"] == 1:
                            prompt = prompt_func(row["str_code_without_try_except"])
                        else:
                            prompt = prompt_func(row["func_body"])

                        start = time.time()
                        
                        sucesso = False
                        while not sucesso:
                            try:
                                response = call_llm(prompt=prompt, model_name=model)
                                sucesso = True 
                            except RateLimitExceeded as exc:
                                if "403" in str(exc) or "Nenhuma chave" in str(exc):
                                    logger.error("FIM DA LINHA: Todas as chaves foram suspensas pelo Google (403). Adicione chaves novas ao .env.")
                                    sys.exit(1)
                                    
                                logger.error(f"Todas as chaves esgotadas: {exc}")
                                logger.info("Pausando por 5 minutos (300s) para limpar a cota do Google...")
                                time.sleep(300)
                            except Exception as exc:
                                if "503" in str(exc) or "UNAVAILABLE" in str(exc):
                                    logger.error(f"Google sobrecarregado (503). Pausando 30s...")
                                    time.sleep(30)
                                else:
                                    logger.error(f"Erro ao processar linha {call_count}: {exc}")
                                    response = {"text": None, "input_tokens": 0, "output_tokens": 0}
                                    sucesso = True 
                        # ---------------------------------

                        response_text = response["text"]
                        input_tokens = response["input_tokens"]
                        output_tokens = response["output_tokens"]
                        elapsed_time = time.time() - start

                        if response_text is not None:
                            logger.info(f"Generated in {elapsed_time:.2f} seconds")
                            logger.info(f"Input tokens: {input_tokens}, Output tokens: {output_tokens}")
                            logger.info(f"Response: {response_text[:50]}...")
                        else:
                            logger.warning(f"Linha {call_count} falhou. Marcando como vazia para tentar futuramente.")

                        output.append(response_text)
                        input_tokens_list.append(input_tokens)
                        output_tokens_list.append(output_tokens)

                        faltam = len(df) - len(output)
                        temp_output = output + [None] * faltam
                        temp_in_tokens = input_tokens_list + [None] * faltam
                        temp_out_tokens = output_tokens_list + [None] * faltam
                        
                        df_style = df.copy()
                        df_style["task"] = task
                        df_style["prompt_type"] = prompt_type
                        df_style["llm_response"] = temp_output
                        df_style["input_tokens"] = temp_in_tokens
                        df_style["output_tokens"] = temp_out_tokens

                        save_results_to_csv(
                            df_style, task, prompt_type, args.project, model_label
                        )

                    # Após rodar as 379
                    df_model = pd.concat([df_model, df_style], ignore_index=True)
                    df_result = pd.concat([df_result, df_style], ignore_index=True)

            if not df_model.empty:
                model_output_file = os.path.join(
                    os.getcwd(), "llm", "output", f"{args.project}_{model_label}_results_all.csv",
                )
                df_model.to_csv(model_output_file, index=False)
                logger.info(f"Model results saved to {model_output_file}")

        if not df_result.empty:
            aggregate_label = sanitize_for_filename("-".join(models_to_run))
            final_output_file = os.path.join(
                os.getcwd(), "llm", "output", f"{args.project}_{aggregate_label}_results_all.csv",
            )
            df_result.to_csv(final_output_file, index=False)
            logger.info(f"Combined results saved to {final_output_file}")

        logger.info(f"✓ Execution completed successfully. Processed {len(df_result)} samples.")

    except KeyboardInterrupt:
        logger.warning("Execution interrupted by user")
        sys.exit(0)


if __name__ == "__main__":
    main()