"""Explicit source dispatch shared by scheduled collection and user rechecks."""


def adapter(source):
    if source['method'] == 'documented_json_feed':
        from data_pipeline import ucf_events
        return ucf_events
    if source['method'] == 'nyc_parks_open_data':
        from data_pipeline import nyc_parks_events
        return nyc_parks_events
    raise ValueError('Unsupported event source method')
