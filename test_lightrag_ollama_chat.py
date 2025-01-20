"""
LightRAG Ollama Compatibility Interface Test Script

This script tests the LightRAG's Ollama compatibility interface, including:
1. Basic functionality tests (streaming and non-streaming responses)
2. Query mode tests (local, global, naive, hybrid)
3. Error handling tests (including streaming and non-streaming scenarios)

All responses use the JSON Lines format, complying with the Ollama API specification.
"""

import requests
import json
import argparse
import time
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path


class OutputControl:
    """Output control class, manages the verbosity of test output"""

    _verbose: bool = False

    @classmethod
    def set_verbose(cls, verbose: bool) -> None:
        cls._verbose = verbose

    @classmethod
    def is_verbose(cls) -> bool:
        return cls._verbose


@dataclass
class TestResult:
    """Test result data class"""

    name: str
    success: bool
    duration: float
    error: Optional[str] = None
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


class TestStats:
    """Test statistics"""

    def __init__(self):
        self.results: List[TestResult] = []
        self.start_time = datetime.now()

    def add_result(self, result: TestResult):
        self.results.append(result)

    def export_results(self, path: str = "test_results.json"):
        """Export test results to a JSON file
        Args:
            path: Output file path
        """
        results_data = {
            "start_time": self.start_time.isoformat(),
            "end_time": datetime.now().isoformat(),
            "results": [asdict(r) for r in self.results],
            "summary": {
                "total": len(self.results),
                "passed": sum(1 for r in self.results if r.success),
                "failed": sum(1 for r in self.results if not r.success),
                "total_duration": sum(r.duration for r in self.results),
            },
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(results_data, f, ensure_ascii=False, indent=2)
        print(f"\nTest results saved to: {path}")

    def print_summary(self):
        total = len(self.results)
        passed = sum(1 for r in self.results if r.success)
        failed = total - passed
        duration = sum(r.duration for r in self.results)

        print("\n=== Test Summary ===")
        print(f"Start time: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Total duration: {duration:.2f} seconds")
        print(f"Total tests: {total}")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")

        if failed > 0:
            print("\nFailed tests:")
            for result in self.results:
                if not result.success:
                    print(f"- {result.name}: {result.error}")


DEFAULT_CONFIG = {
    "server": {
        "host": "localhost",
        "port": 9621,
        "model": "lightrag:latest",
        "timeout": 30,
        "max_retries": 3,
        "retry_delay": 1,
    },
    "test_cases": {"basic": {"query": "唐僧有几个徒弟"}},
}


def make_request(
    url: str, data: Dict[str, Any], stream: bool = False
) -> requests.Response:
    """Send an HTTP request with retry mechanism
    Args:
        url: Request URL
        data: Request data
        stream: Whether to use streaming response
    Returns:
        requests.Response: Response object

    Raises:
        requests.exceptions.RequestException: Request failed after all retries
    """
    server_config = CONFIG["server"]
    max_retries = server_config["max_retries"]
    retry_delay = server_config["retry_delay"]
    timeout = server_config["timeout"]

    for attempt in range(max_retries):
        try:
            response = requests.post(url, json=data, stream=stream, timeout=timeout)
            return response
        except requests.exceptions.RequestException as e:
            if attempt == max_retries - 1:  # Last retry
                raise
            print(f"\nRequest failed, retrying in {retry_delay} seconds: {str(e)}")
            time.sleep(retry_delay)


def load_config() -> Dict[str, Any]:
    """Load configuration file

    First try to load from config.json in the current directory,
    if it doesn't exist, use the default configuration
    Returns:
        Configuration dictionary
    """
    config_path = Path("config.json")
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return DEFAULT_CONFIG


def print_json_response(data: Dict[str, Any], title: str = "", indent: int = 2) -> None:
    """Format and print JSON response data
    Args:
        data: Data dictionary to print
        title: Title to print
        indent: Number of spaces for JSON indentation
    """
    if OutputControl.is_verbose():
        if title:
            print(f"\n=== {title} ===")
        print(json.dumps(data, ensure_ascii=False, indent=indent))


# Global configuration
CONFIG = load_config()


def get_base_url() -> str:
    """Return the base URL"""
    server = CONFIG["server"]
    return f"http://{server['host']}:{server['port']}/api/chat"


def create_request_data(
    content: str, stream: bool = False, model: str = None
) -> Dict[str, Any]:
    """Create basic request data
    Args:
        content: User message content
        stream: Whether to use streaming response
        model: Model name
    Returns:
        Dictionary containing complete request data
    """
    return {
        "model": model or CONFIG["server"]["model"],
        "messages": [{"role": "user", "content": content}],
        "stream": stream,
    }


# Global test statistics
STATS = TestStats()


def run_test(func: Callable, name: str) -> None:
    """Run a test and record the results
    Args:
        func: Test function
        name: Test name
    """
    start_time = time.time()
    try:
        func()
        duration = time.time() - start_time
        STATS.add_result(TestResult(name, True, duration))
    except Exception as e:
        duration = time.time() - start_time
        STATS.add_result(TestResult(name, False, duration, str(e)))
        raise


def test_non_stream_chat():
    """Test non-streaming call to /api/chat endpoint"""
    url = get_base_url()
    data = create_request_data(CONFIG["test_cases"]["basic"]["query"], stream=False)

    # Send request
    response = make_request(url, data)

    # Print response
    if OutputControl.is_verbose():
        print("\n=== Non-streaming call response ===")
    response_json = response.json()

    # Print response content
    print_json_response(
        {"model": response_json["model"], "message": response_json["message"]},
        "Response content",
    )


def test_stream_chat():
    """Test streaming call to /api/chat endpoint

    Use JSON Lines format to process streaming responses, each line is a complete JSON object.
    Response format:
    {
        "model": "lightrag:latest",
        "created_at": "2024-01-15T00:00:00Z",
        "message": {
            "role": "assistant",
            "content": "Partial response content",
            "images": null
        },
        "done": false
    }

    The last message will contain performance statistics, with done set to true.
    """
    url = get_base_url()
    data = create_request_data(CONFIG["test_cases"]["basic"]["query"], stream=True)

    # Send request and get streaming response
    response = make_request(url, data, stream=True)

    if OutputControl.is_verbose():
        print("\n=== Streaming call response ===")
    output_buffer = []
    try:
        for line in response.iter_lines():
            if line:  # Skip empty lines
                try:
                    # Decode and parse JSON
                    data = json.loads(line.decode("utf-8"))
                    if data.get("done", True):  # If it's the completion marker
                        if (
                            "total_duration" in data
                        ):  # Final performance statistics message
                            # print_json_response(data, "Performance statistics")
                            break
                    else:  # Normal content message
                        message = data.get("message", {})
                        content = message.get("content", "")
                        if content:  # Only collect non-empty content
                            output_buffer.append(content)
                            print(
                                content, end="", flush=True
                            )  # Print content in real-time
                except json.JSONDecodeError:
                    print("Error decoding JSON from response line")
    finally:
        response.close()  # Ensure the response connection is closed

    # Print a newline
    print()


def test_query_modes():
    """Test different query mode prefixes

    Supported query modes:
    - /local: Local retrieval mode, searches only in highly relevant documents
    - /global: Global retrieval mode, searches across all documents
    - /naive: Naive mode, does not use any optimization strategies
    - /hybrid: Hybrid mode (default), combines multiple strategies
    - /mix: Mix mode

    Each mode will return responses in the same format, but with different retrieval strategies.
    """
    url = get_base_url()
    modes = ["local", "global", "naive", "hybrid", "mix"]

    for mode in modes:
        if OutputControl.is_verbose():
            print(f"\n=== Testing /{mode} mode ===")
        data = create_request_data(
            f"/{mode} {CONFIG['test_cases']['basic']['query']}", stream=False
        )

        # Send request
        response = make_request(url, data)
        response_json = response.json()

        # Print response content
        print_json_response(
            {"model": response_json["model"], "message": response_json["message"]}
        )


def create_error_test_data(error_type: str) -> Dict[str, Any]:
    """Create request data for error testing
    Args:
        error_type: Error type, supported:
            - empty_messages: Empty message list
            - invalid_role: Invalid role field
            - missing_content: Missing content field

    Returns:
        Request dictionary containing error data
    """
    error_data = {
        "empty_messages": {"model": "lightrag:latest", "messages": [], "stream": True},
        "invalid_role": {
            "model": "lightrag:latest",
            "messages": [{"invalid_role": "user", "content": "Test message"}],
            "stream": True,
        },
        "missing_content": {
            "model": "lightrag:latest",
            "messages": [{"role": "user"}],
            "stream": True,
        },
    }
    return error_data.get(error_type, error_data["empty_messages"])


def test_stream_error_handling():
    """Test error handling for streaming responses

    Test scenarios:
    1. Empty message list
    2. Message format error (missing required fields)

    Error responses should be returned immediately without establishing a streaming connection.
    The status code should be 4xx, and detailed error information should be returned.
    """
    url = get_base_url()

    if OutputControl.is_verbose():
        print("\n=== Testing streaming response error handling ===")

    # Test empty message list
    if OutputControl.is_verbose():
        print("\n--- Testing empty message list (streaming) ---")
    data = create_error_test_data("empty_messages")
    response = make_request(url, data, stream=True)
    print(f"Status code: {response.status_code}")
    if response.status_code != 200:
        print_json_response(response.json(), "Error message")
    response.close()

    # Test invalid role field
    if OutputControl.is_verbose():
        print("\n--- Testing invalid role field (streaming) ---")
    data = create_error_test_data("invalid_role")
    response = make_request(url, data, stream=True)
    print(f"Status code: {response.status_code}")
    if response.status_code != 200:
        print_json_response(response.json(), "Error message")
    response.close()

    # Test missing content field
    if OutputControl.is_verbose():
        print("\n--- Testing missing content field (streaming) ---")
    data = create_error_test_data("missing_content")
    response = make_request(url, data, stream=True)
    print(f"Status code: {response.status_code}")
    if response.status_code != 200:
        print_json_response(response.json(), "Error message")
    response.close()


def test_error_handling():
    """Test error handling for non-streaming responses

    Test scenarios:
    1. Empty message list
    2. Message format error (missing required fields)

    Error response format:
    {
        "detail": "Error description"
    }

    All errors should return appropriate HTTP status codes and clear error messages.
    """
    url = get_base_url()

    if OutputControl.is_verbose():
        print("\n=== Testing error handling ===")

    # Test empty message list
    if OutputControl.is_verbose():
        print("\n--- Testing empty message list ---")
    data = create_error_test_data("empty_messages")
    data["stream"] = False  # Change to non-streaming mode
    response = make_request(url, data)
    print(f"Status code: {response.status_code}")
    print_json_response(response.json(), "Error message")

    # Test invalid role field
    if OutputControl.is_verbose():
        print("\n--- Testing invalid role field ---")
    data = create_error_test_data("invalid_role")
    data["stream"] = False  # Change to non-streaming mode
    response = make_request(url, data)
    print(f"Status code: {response.status_code}")
    print_json_response(response.json(), "Error message")

    # Test missing content field
    if OutputControl.is_verbose():
        print("\n--- Testing missing content field ---")
    data = create_error_test_data("missing_content")
    data["stream"] = False  # Change to non-streaming mode
    response = make_request(url, data)
    print(f"Status code: {response.status_code}")
    print_json_response(response.json(), "Error message")


def get_test_cases() -> Dict[str, Callable]:
    """Get all available test cases
    Returns:
        A dictionary mapping test names to test functions
    """
    return {
        "non_stream": test_non_stream_chat,
        "stream": test_stream_chat,
        "modes": test_query_modes,
        "errors": test_error_handling,
        "stream_errors": test_stream_error_handling,
    }


def create_default_config():
    """Create a default configuration file"""
    config_path = Path("config.json")
    if not config_path.exists():
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
        print(f"Default configuration file created: {config_path}")


def parse_args() -> argparse.Namespace:
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="LightRAG Ollama Compatibility Interface Testing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Configuration file (config.json):
  {
    "server": {
      "host": "localhost",      # Server address
      "port": 9621,            # Server port
      "model": "lightrag:latest" # Default model name
    },
    "test_cases": {
      "basic": {
        "query": "Test query",      # Basic query text
        "stream_query": "Stream query" # Stream query text
      }
    }
  }
""",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Silent mode, only display test result summary",
    )
    parser.add_argument(
        "-a",
        "--ask",
        type=str,
        help="Specify query content, which will override the query settings in the configuration file",
    )
    parser.add_argument(
        "--init-config", action="store_true", help="Create default configuration file"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="",
        help="Test result output file path, default is not to output to a file",
    )
    parser.add_argument(
        "--tests",
        nargs="+",
        choices=list(get_test_cases().keys()) + ["all"],
        default=["all"],
        help="Test cases to run, options: %(choices)s. Use 'all' to run all tests",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    # Set output mode
    OutputControl.set_verbose(not args.quiet)

    # If query content is specified, update the configuration
    if args.ask:
        CONFIG["test_cases"]["basic"]["query"] = args.ask

    # If specified to create a configuration file
    if args.init_config:
        create_default_config()
        exit(0)

    test_cases = get_test_cases()

    try:
        if "all" in args.tests:
            # Run all tests
            if OutputControl.is_verbose():
                print("\n【Basic Functionality Tests】")
            run_test(test_non_stream_chat, "Non-streaming Call Test")
            run_test(test_stream_chat, "Streaming Call Test")

            if OutputControl.is_verbose():
                print("\n【Query Mode Tests】")
            run_test(test_query_modes, "Query Mode Test")

            if OutputControl.is_verbose():
                print("\n【Error Handling Tests】")
            run_test(test_error_handling, "Error Handling Test")
            run_test(test_stream_error_handling, "Streaming Error Handling Test")
        else:
            # Run specified tests
            for test_name in args.tests:
                if OutputControl.is_verbose():
                    print(f"\n【Running Test: {test_name}】")
                run_test(test_cases[test_name], test_name)
    except Exception as e:
        print(f"\nAn error occurred: {str(e)}")
    finally:
        # Print test statistics
        STATS.print_summary()
        # If an output file path is specified, export the results
        if args.output:
            STATS.export_results(args.output)