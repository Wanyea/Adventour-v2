from adventour_backend.data.chain_list import CHAIN_NAMES

def is_chain(place_name):
    name = place_name.lower()
    for chain in CHAIN_NAMES:
        if chain.lower() in name:
            return True
    return False

def is_hidden_gem(place):
    # Hidden gem: high rating, low review count, not a chain
    rating = place.get('rating') or 0
    reviews = place.get('user_ratings_total') or 0
    name = place.get('name', '')
    return (
        rating >= 4.5 and
        reviews < 100 and
        not is_chain(name)
    )

def review_sentiment_score(reviews):
    # Simple keyword-based sentiment analysis
    if not reviews:
        return 0
    positive_keywords = [
        'authentic', 'local', 'unique', 'hidden gem', 'cozy', 'charming', 'off the beaten path', 'family-owned', 'mom and pop', 'underrated', 'must visit', 'favorite', 'best kept secret'
    ]
    score = 0
    for review in reviews:
        text = review.get('text', '').lower()
        for kw in positive_keywords:
            if kw in text:
                score += 1
    # Normalize by number of reviews
    return score / len(reviews) if reviews else 0 
