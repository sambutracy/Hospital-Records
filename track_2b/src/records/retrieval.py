"""Lexical preselection across authorized current versions; never a clinical conclusion."""
import re
from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.db.models import TextField
from django.db.models.functions import Cast

STOP_WORDS = {'a', 'an', 'and', 'at', 'for', 'from', 'i', 'in', 'is', 'me', 'my',
              'of', 'on', 'please', 'record', 'records', 'show', 'the', 'to', 'with', 'find'}


def ranked_candidates(records, query):
    """Computed PostgreSQL full-text rank. No embedding index or complete semantic recall claim."""
    words = list(dict.fromkeys(word.casefold() for word in re.findall(r'\w+', query)
                              if word.casefold() not in STOP_WORDS))[:12]
    if not words:
        words = [query]
    search = SearchQuery(words[0], config='simple')
    for word in words[1:]:
        search |= SearchQuery(word, config='simple')
    vector = SearchVector('current_version__original_filename',
        'current_version__metadata_head__facility_name__value_text',
        'current_version__metadata_head__document_type__value_text',
        Cast('current_version__extraction__pages', TextField()), config='simple')
    ranked = records.annotate(relevance=SearchRank(vector, search))
    return ranked.order_by('-relevance', '-created_at', 'id'), ranked.filter(relevance__gt=0).count()
