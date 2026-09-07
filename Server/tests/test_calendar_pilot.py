"""Focused regression checks for observed calendar parsing/traversal failures."""
import unittest
from zoneinfo import ZoneInfo

from data_pipeline.calendar_pilot import candidate, event_nodes, links, timestamp

WINDOW = {'start': '2026-09-07', 'end_exclusive': '2026-10-05',
          'timezone': 'America/New_York'}
SOURCE = {'city_terms': ['new york', 'queens']}


class CalendarPilotTests(unittest.TestCase):
    def test_compact_offset_and_missing_end_remain_distinct(self):
        start, note = timestamp('2026-09-20T13:00:00-0400', ZoneInfo(WINDOW['timezone']))
        self.assertIsNone(note)
        self.assertEqual(start.isoformat(), '2026-09-20T13:00:00-04:00')
        row = candidate({'name': 'Coffee', 'startDate': '2026-09-20T13:00:00-0400',
                         'location': {'address': {'addressLocality': 'Queens'}}},
                        'https://example.org/event', SOURCE, WINDOW)
        self.assertTrue(row['overlaps_window'])
        self.assertIsNone(row['end_local'])
        self.assertIn('end_missing_or_date_only', row['flags'])
        self.assertEqual(row['status'], 'review_required')

    def test_dates_prioritize_current_detail_without_fetching_export(self):
        page = '''<a href="/events/aaa-old">Old event</a>
        <article><time datetime="2026-09-20"></time>
        <a href="/events/zzz-new">Event</a>
        <a href="/events/zzz-new?format=ical">Calendar</a></article>'''
        found, _ = links(page, 'https://example.org/events', WINDOW)
        self.assertEqual(found, ['https://example.org/events/zzz-new',
                                 'https://example.org/events/aaa-old'])

    def test_footer_does_not_supply_missing_event_location(self):
        page = '''<footer>New York</footer><script type="application/ld+json">
        {"@graph":[{"@type":"Event","name":"Coffee", "startDate":"2026-09-20T12:00:00-04:00",
        "endDate":"2026-09-20T13:00:00-04:00","location":{"name":""}}]}</script>'''
        events, errors = event_nodes(page)
        self.assertEqual(errors, 0)
        row = candidate(events[0], 'https://example.org/events', SOURCE, WINDOW)
        self.assertFalse(row['region_evidence'])

    def test_cancelled_event_is_not_made_attendable_by_public_phrase(self):
        row = candidate({'name': 'Tasting', 'description': 'Open to the public',
                         'eventStatus': 'https://schema.org/EventCancelled'},
                        'https://example.org/events', SOURCE, WINDOW)
        self.assertTrue(row['cancelled_or_postponed'])
        self.assertIn('outside_window_or_unknown', row['flags'])


if __name__ == '__main__':
    unittest.main()
