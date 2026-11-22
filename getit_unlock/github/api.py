"""Small REST/GraphQL client. Ambiguous writes are never automatically replayed."""
import json
import math
import time
from threading import Lock
from datetime import timezone
from email.utils import parsedate_to_datetime
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .. import USER_AGENT


class GitHubError(RuntimeError):
    def __init__(self, message: str, status: int | None = None, *, retry_after: float | None = None):
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class WriteLimiter:
    """Pace all requests and share secondary cooldowns across clients in a run."""
    def __init__(self, interval=8.0, *, request_interval=1.0, clock=time.monotonic, sleep=time.sleep):
        if any(not math.isfinite(value) or value < 0 for value in (interval, request_interval)):
            raise ValueError("API pacing intervals must be finite and non-negative.")
        self.interval, self.clock, self.sleep = interval, clock, sleep
        self.request_interval = request_interval
        self.last = None
        self.last_request = None
        self.cooldown_until = 0.0
        self._lock = Lock()

    def defer(self, delay):
        """Retain a rejected request's cooldown even when retries are exhausted."""
        with self._lock:
            self.cooldown_until = max(self.cooldown_until, self.clock() + delay)

    def wait(self, *, read_only=False, max_wait=300, report=None):
        with self._lock:
            now = self.clock()
            cooldown = self.cooldown_until - now
            delay = max(0, cooldown)
            if self.last_request is not None:
                delay = max(delay, self.request_interval - (now - self.last_request))
            if not read_only and self.last is not None:
                delay = max(delay, self.interval - (now - self.last))
            if delay > max_wait:
                raise GitHubError(f"GitHub rate limited. Retry after at least {math.ceil(delay)} seconds; progress has been kept.",
                                  retry_after=delay)
            if delay > 0:
                if cooldown > 0 and report:
                    report(f"GitHub rate limit: waiting {math.ceil(delay)} seconds")
                self.sleep(delay)
            self.last_request = self.clock()
            if not read_only:
                self.last = self.last_request


class GitHubClient:
    BASE = "https://api.github.com"

    def __init__(self, token, *, limiter=None, opener=None, sleep=time.sleep,
                 timeout=30, retries=2, max_wait=300, clock=time.time, report=None):
        self._token = token
        self.limiter = limiter or WriteLimiter(sleep=sleep)
        self.opener = opener or build_opener(NoRedirect())
        self.sleep, self.timeout, self.retries, self.max_wait = sleep, timeout, retries, max_wait
        self.clock = clock
        self.report = report or (lambda message: None)
        self.quota_resets = {}

    def _clean(self, text):
        return str(text).replace(self._token, "[REDACTED]") if self._token else str(text)

    @staticmethod
    def _headers(headers):
        return {key.lower(): value for key, value in headers.items()}

    def _retry_delay(self, headers, attempt, *, limited=False):
        headers = self._headers(headers)
        delays = []
        retry = headers.get("retry-after")
        if retry:
            try:
                delay = float(retry)
                if math.isfinite(delay):
                    delays.append(max(0, delay))
            except ValueError:
                try:
                    date = parsedate_to_datetime(retry)
                    if date.tzinfo is None:
                        date = date.replace(tzinfo=timezone.utc)
                    delays.append(max(0, date.timestamp() - self.clock()))
                except (TypeError, ValueError):
                    pass
        if headers.get("x-ratelimit-remaining") == "0":
            try:
                reset = float(headers["x-ratelimit-reset"])
                if math.isfinite(reset):
                    delays.append(max(1, reset - self.clock() + 1))
            except (ValueError, KeyError):
                pass
        if delays:
            return max(delays) * (2 ** attempt if limited else 1)
        if limited:
            return 60 * 2 ** attempt
        return 2 ** (attempt + 1)

    def _remember_quota(self, headers, resource):
        headers = self._headers(headers)
        resource = headers.get("x-ratelimit-resource", resource)
        if headers.get("x-ratelimit-remaining") == "0":
            try:
                reset = float(headers["x-ratelimit-reset"])
                if math.isfinite(reset):
                    self.quota_resets[resource] = reset
            except (KeyError, ValueError):
                pass
        elif "x-ratelimit-remaining" in headers:
            self.quota_resets.pop(resource, None)

    def _pause_for_limit(self, delay):
        if delay > self.max_wait:
            raise GitHubError(f"GitHub rate limited. Retry after at least {math.ceil(delay)} seconds; progress has been kept.", retry_after=delay)
        self.report(f"GitHub rate limit: waiting {math.ceil(delay)} seconds")
        self.sleep(delay)

    def _respect_quota(self, resource):
        reset = self.quota_resets.get(resource)
        if reset is not None:
            delay = reset - self.clock() + 1
            if delay > 0:
                self._pause_for_limit(delay)
            self.quota_resets.pop(resource, None)

    def request(self, method, path, payload=None, *, read_only=False):
        if not path.startswith("/") or path.startswith("//"):
            raise ValueError("API paths must be relative to api.github.com.")
        read_only = read_only or method == "GET"
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        resource = "graphql" if path == "/graphql" else "core"
        for attempt in range(self.retries + 1):
            self._respect_quota(resource)
            self.limiter.wait(read_only=read_only, max_wait=self.max_wait, report=self.report)
            request = Request(self.BASE + path, data=data, method=method, headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": USER_AGENT,
            })
            try:
                with self.opener.open(request, timeout=self.timeout) as response:
                    headers = self._headers(getattr(response, "headers", {}))
                    raw = response.read()
                self._remember_quota(headers, resource)
                if not raw:
                    return {}
                try:
                    result = json.loads(raw)
                except (ValueError, UnicodeError) as exc:
                    raise GitHubError("GitHub returned invalid JSON; inspect remote state before retrying writes.") from exc
                if path == "/graphql" and isinstance(result, dict) and result.get("errors"):
                    errors = result["errors"]
                    limits = [error.get("type") == "RATE_LIMITED" or "rate limit" in error.get("message", "").lower() for error in errors]
                    partial_data = result.get("data") or {}
                    rejected = isinstance(partial_data, dict) and not any(value is not None for value in partial_data.values())
                    if any(limits):
                        delay = self._retry_delay(headers, attempt, limited=True)
                        if headers.get("x-ratelimit-remaining") != "0":
                            self.limiter.defer(delay)
                        if all(limits) and rejected and attempt < self.retries:
                            self._pause_for_limit(delay)
                            self.quota_resets.pop(resource, None)
                            continue
                        messages = "; ".join(error.get("message", "GraphQL error") for error in errors)
                        hint = " Inspect remote state before retrying writes." if not read_only and not rejected else ""
                        raise GitHubError(self._clean(f"GitHub GraphQL: {messages}. Rate limited; retry after at least {math.ceil(delay)} seconds.{hint}"),
                                          retry_after=delay)
                return result
            except HTTPError as exc:
                try:
                    error = json.loads(exc.read())
                    message = error.get("message", "Request rejected") if isinstance(error, dict) else "Request rejected"
                except (ValueError, UnicodeError):
                    message = exc.reason
                finally:
                    exc.close()
                headers = self._headers(exc.headers)
                self._remember_quota(headers, resource)
                limited = exc.code == 429 or (exc.code == 403 and (
                    headers.get("retry-after") is not None
                    or headers.get("x-ratelimit-remaining") == "0"
                    or "rate limit" in str(message).lower()))
                retryable = limited or (read_only and exc.code >= 500)
                delay = self._retry_delay(headers, attempt, limited=limited)
                if limited and headers.get("x-ratelimit-remaining") != "0":
                    self.limiter.defer(delay)
                if retryable and attempt < self.retries and delay <= self.max_wait:
                    if limited:
                        self._pause_for_limit(delay)
                        self.quota_resets.pop(resource, None)
                    else:
                        self.sleep(delay)
                    continue
                hint = ""
                if limited:
                    hint = f" Rate limited; retry after at least {delay:.0f} seconds."
                elif exc.code == 401:
                    hint = " Check your token and its expiration."
                elif exc.code in (403, 404):
                    hint = " Check repository access, token permissions, and repository settings."
                elif not read_only and exc.code >= 500:
                    hint = " Write outcome is uncertain; inspect remote state before retrying."
                raise GitHubError(self._clean(f"GitHub HTTP {exc.code}: {message}.{hint}"), exc.code,
                                  retry_after=delay if limited else None) from None
            except (URLError, TimeoutError, OSError, HTTPException) as exc:
                if read_only and attempt < self.retries:
                    self.sleep(2 ** (attempt + 1))
                    continue
                hint = "" if read_only else " Write outcome is uncertain; inspect remote state before retrying."
                raise GitHubError(self._clean(f"Could not reach GitHub: {exc}.{hint}")) from None
        raise AssertionError("Unreachable")

    def graphql(self, query, variables, *, mutation=False):
        response = self.request("POST", "/graphql", {"query": query, "variables": variables}, read_only=not mutation)
        if response.get("errors"):
            messages = "; ".join(item.get("message", "GraphQL error") for item in response["errors"])
            raise GitHubError(self._clean(f"GitHub GraphQL: {messages}"))
        if not response.get("data"):
            raise GitHubError("GitHub returned no GraphQL data.")
        return response["data"]
