from data_pipeline.event_discovery import discover


class Response:
    content = b'<html>'
    text = '''<a href="/events/one">One</a><script type="application/ld+json">
    {"@type":"Event","name":"Coffee","startDate":"2026-09-20T12:00:00-04:00",
    "endDate":"2026-09-20T13:00:00-04:00",
    "location":{"address":{"addressLocality":"Queens"}}}</script>'''


class Session:
    def __init__(self): self.urls = []
    def get(self, url): self.urls.append(url); return Response()


def test_discovery_fetches_same_host_and_keeps_external_links_as_leads():
    session = Session()
    result = discover(session, ['https://example.org/events'],
                      source={'city_terms': ['queens']},
                      window={'start': '2026-09-01', 'end_exclusive': '2026-10-01',
                              'timezone': 'America/New_York'}, max_pages=2)
    assert result['pages'] == 2
    assert len(result['records']) == 2
    assert session.urls[0] == 'https://example.org/events'


def test_discovery_does_not_fetch_external_links():
    class ExternalSession(Session):
        def get(self, url):
            self.urls.append(url)
            response = Response()
            response.text += '<a href="https://other.example/event">ticket</a>'
            return response
    session = ExternalSession()
    result = discover(session, ['https://example.org/events'], source={'city_terms': ['queens']},
                      window={'start': '2026-09-01', 'end_exclusive': '2026-10-01',
                              'timezone': 'America/New_York'}, max_pages=1)
    assert session.urls == ['https://example.org/events']
    assert 'https://other.example/event' in result['external_leads']
