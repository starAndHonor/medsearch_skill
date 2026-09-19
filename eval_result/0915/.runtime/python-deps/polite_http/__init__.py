# Copyright 2026 polite-http contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""polite-http — a courteous, dependency-free HTTP client.

Rate limiting, automatic retries, exponential backoff with jitter,
`Retry-After` support, and proactive `X-Throttling-Control` backpressure —
built entirely on the Python standard library.
"""

from polite_http.http_client import (
    DEFAULT_BACKOFF_BASE_SECS,
    DEFAULT_BACKOFF_MAX_SECS,
    DEFAULT_JITTER_SECS,
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT_SECS,
    RETRYABLE_STATUS_CODES,
    USER_AGENT_ENV_VAR,
    HttpClient,
    HttpError,
    HttpResponse,
)

__version__ = "0.1.3"

__all__ = [
    "HttpClient",
    "HttpError",
    "HttpResponse",
    "DEFAULT_BACKOFF_BASE_SECS",
    "DEFAULT_BACKOFF_MAX_SECS",
    "DEFAULT_JITTER_SECS",
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_TIMEOUT_SECS",
    "RETRYABLE_STATUS_CODES",
    "USER_AGENT_ENV_VAR",
    "__version__",
]
