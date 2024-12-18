# ollama_client.py
import requests
import logging
from typing import Optional, Type
from pydantic import BaseModel
import yaml
import json  # Needed for parsing streaming JSON lines

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class OllamaClient:
    def __init__(self, config_path: str, output_model: Optional[Type[BaseModel]] = None):
        """
        Initialize the OllamaClient with a configuration file.
        """
        self.config = self.load_config(config_path)
        self.output_model = output_model

    @staticmethod
    def load_config(config_path: str) -> dict:
        """
        Load the YAML configuration file and return it as a dictionary.
        """
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
        temperature: Optional[float] = None
    ) -> Optional[BaseModel]:
        """
        Generate a response from the model based on the given prompt.
        Implements retry logic based on the configuration and supports streaming responses.
        """
        headers = {
            'Content-Type': 'application/json',
        }
        api_key = self.config.get('api_key')
        if api_key:
            headers['Authorization'] = f'Bearer {api_key}'

        payload = {
            'model': self.config.get('model_name'),
            'prompt': prompt,
            "stream": True,  # Ensuring we request a streaming response
            'options': {         
                'temperature': temperature if temperature is not None else self.config.get('temperature', 0.7)
            }
        }

        if self.output_model:
            # The specifics of how the model is formatted might vary.
            # If your API supports specifying a format, use that here.
            # Otherwise, consider removing or adjusting this line as needed.
            payload['format'] = self.output_model.model_json_schema()

        max_retries = self.config.get('max_retries', 3)

        # Prepare headers for logging by masking the Authorization header
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
                    stream=True
                ) as response:
                    # Log response status and headers
                    logger.info(f"Received response with status code: {response.status_code}")
                    logger.info(f"Response Headers: {response.headers}")

                    response.raise_for_status()

                    output = ""
                    for line in response.iter_lines(decode_unicode=True):
                        if not line:
                            continue
                        # Log the raw response line before parsing
                        logger.debug(f"Raw response line: {line}")

                        try:
                            data = json.loads(line)
                            #logger.info(f"Parsed response line: {data}")
                        except json.JSONDecodeError:
                            logger.warning("Received a line that could not be JSON-decoded, skipping...")
                            continue

                        # Check for errors in streaming data
                        if "error" in data:
                            logger.error(f"Error in response data: {data['error']}")
                            raise Exception(data["error"])

                        # Extract the 'response' field
                        content = data.get("response", "")
                        output += content

                        if data.get("done", False):
                            # Streaming is complete
                            # Parse into output_model if provided
                            if self.output_model:
                                try:
                                    # Validate that output contains valid JSON
                                    if not output.strip():
                                        raise ValueError("Output is empty, cannot parse.")
                                    
                                    parsed_output = self.output_model.parse_raw(output)
                                    logger.info(f"Final parsed output: {parsed_output}")
                                    return parsed_output
                                except Exception as e:
                                    logger.error(f"Error parsing model output: {e}")
                                    return None
                            logger.info(f"Final output: {output}")
                            return output

                    # If we exit the loop without hitting 'done', something might be wrong
                    logger.error("No 'done' signal received before the stream ended.")
                    return None
            except requests.exceptions.RequestException as e:
                logger.warning(f"Attempt {attempt} failed: {e}")
                if attempt == max_retries:
                    logger.error(f"All {max_retries} attempts failed. Giving up.")
                    raise
                else:
                    logger.info(f"Retrying... (Attempt {attempt + 1} of {max_retries})")
            except Exception as e:
                logger.error(f"An error occurred: {e}")
                raise
