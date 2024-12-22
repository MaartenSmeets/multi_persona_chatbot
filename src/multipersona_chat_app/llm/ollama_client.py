# File: /home/maarten/multi_persona_chatbot/src/multipersona_chat_app/llm/ollama_client.py

import requests
import logging
from typing import Optional, Type
from pydantic import BaseModel
import yaml
import json
import os

from db.cache_manager import CacheManager

logger = logging.getLogger(__name__)

class OllamaClient:
    def __init__(self, config_path: str, output_model: Optional[Type[BaseModel]] = None):
        self.config = self.load_config(config_path)
        self.output_model = output_model
        # Initialize cache
        cache_file = os.path.join("output", "llm_cache")
        self.cache_manager = CacheManager(cache_file)

    @staticmethod
    def load_config(config_path: str) -> dict:
        try:
            with open(config_path, 'r') as file:
                config = yaml.safe_load(file)
            logger.info(f"Configuration loaded successfully from {config_path}")
            return config
        except FileNotFoundError:
            logger.error(f"Configuration file not found at path: {config_path}")
            raise
        except yaml.YAMLError as e:
            logger.error(f"Error parsing YAML file: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error loading configuration: {e}")
            raise

    def generate(
        self,
        prompt: str,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        system: Optional[str] = None
    ) -> Optional[BaseModel or str]:
        model_name = self.config.get('model_name')

        # Check cache first
        cached_response = self.cache_manager.get_cached_response(prompt, model_name)
        if cached_response is not None:
            logger.info("Returning cached LLM response.")
            if self.output_model:
                try:
                    return self.output_model.parse_raw(cached_response)
                except:
                    logger.error("Error parsing cached response. Treating as invalid and returning None.")
                    return None
            else:
                return cached_response

        headers = {
            'Content-Type': 'application/json',
        }
        api_key = self.config.get('api_key')
        if api_key:
            headers['Authorization'] = f'Bearer {api_key}'

        payload = {
            'model': model_name,
            'prompt': prompt,
            "stream": True,
            'options': {
                'temperature': temperature if temperature is not None else self.config.get('temperature', 0.7)
            }
        }

        if system:
            payload['system'] = system

        if self.output_model:
            payload['format'] = self.output_model.model_json_schema()

        max_retries = self.config.get('max_retries', 3)

        log_headers = headers.copy()
        if 'Authorization' in log_headers:
            log_headers['Authorization'] = 'Bearer ***'

        logger.info("Sending request to Ollama API")
        logger.info(f"Request URL: {self.config.get('api_url')}")
        logger.info(f"Request Headers: {log_headers}")
        logger.info(f"Request Payload: {payload}")

        for attempt in range(1, max_retries + 1):
            try:
                with requests.post(
                    self.config.get('api_url'),
                    headers=headers,
                    json=payload,
                    stream=True,
                    timeout=self.config.get('timeout', 300)
                ) as response:
                    logger.info(f"Received response with status code: {response.status_code}")
                    logger.info(f"Response Headers: {response.headers}")
                    response.raise_for_status()

                    output = ""
                    for line in response.iter_lines(decode_unicode=True):
                        if not line:
                            continue
                        logger.debug(f"Raw response line: {line}")

                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            logger.warning("Received a line that could not be JSON-decoded, skipping...")
                            continue

                        if "error" in data:
                            logger.error(f"Error in response data: {data['error']}")
                            raise Exception(data["error"])

                        content = data.get("response", "")
                        output += content

                        if data.get("done", False):
                            # If we have an output model, parse it as structured data
                            if self.output_model:
                                try:
                                    parsed_output = self.output_model.parse_raw(output)
                                    # Log the structured output so we can see it in the logs:
                                    logger.info("Final parsed output (structured) stored in cache.")
                                    logger.info(f"Structured Output: {parsed_output.dict()}")
                                    self.cache_manager.store_response(prompt, model_name, output)
                                    return parsed_output
                                except Exception as e:
                                    logger.error(f"Error parsing model output: {e}")
                                    return None
                            else:
                                self.cache_manager.store_response(prompt, model_name, output)
                                logger.info("Final unstructured output stored in cache.")
                                return output

                    logger.error("No 'done' signal received before the stream ended.")
                    return None
            except requests.exceptions.RequestException as e:
                logger.warning(f"Attempt {attempt} failed: {e}")
                if attempt == max_retries:
                    logger.error(f"All {max_retries} attempts failed. Giving up.")
                    return None
                else:
                    logger.info(f"Retrying... (Attempt {attempt + 1} of {max_retries})")
            except Exception as e:
                logger.error(f"An error occurred: {e}")
                return None
