import urllib.error

from dochan.fallback.filter_server import FilterServerClient, FilterServerConfig


class _Response:
    def __init__(self, *, status=200, data=b""):
        self.status = status
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self, size=-1):
        return self.data if size < 0 else self.data[:size]


def test_health_failure_is_retried_instead_of_cached_forever(monkeypatch):
    responses = iter([urllib.error.URLError("offline"), _Response(status=200)])
    calls = []

    def urlopen(request, timeout):
        calls.append((request, timeout))
        response = next(responses)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    client = FilterServerClient()

    assert client.is_available() is False
    assert client.is_available() is True
    assert len(calls) == 2


def test_successful_health_check_uses_short_lived_cache(monkeypatch):
    calls = []

    def urlopen(request, timeout):
        calls.append((request, timeout))
        return _Response(status=200)

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    client = FilterServerClient(FilterServerConfig(health_cache_seconds=60))

    assert client.is_available() is True
    assert client.is_available() is True
    assert len(calls) == 1


def test_convert_rejects_oversized_upload_before_posting(monkeypatch, tmp_path):
    calls = []

    def urlopen(request, timeout):
        calls.append(request.full_url)
        return _Response(status=200)

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    source = tmp_path / "large.hwp"
    source.write_bytes(b"1234")
    client = FilterServerClient(FilterServerConfig(max_upload_bytes=3))

    assert client.convert_to_html(str(source)) is None
    assert calls == ["http://localhost:8080/health"]


def test_convert_sanitizes_multipart_filename_and_bounds_response(monkeypatch, tmp_path):
    requests = []

    def urlopen(request, timeout):
        requests.append(request)
        if request.full_url.endswith("/health"):
            return _Response(status=200)
        return _Response(data=b"012345")

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    source = tmp_path / 'bad"name.hwp'
    source.write_bytes(b"document")
    client = FilterServerClient(FilterServerConfig(max_response_bytes=5))

    assert client.convert_to_html(str(source)) is None
    posted_body = requests[-1].data
    assert b'filename="bad_name.hwp"' in posted_body
    assert b'filename="bad"name.hwp"' not in posted_body


def test_filter_server_rejects_non_http_base_url(monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not open")),
    )
    client = FilterServerClient(FilterServerConfig(base_url="file:///etc"))

    assert client.is_available() is False
