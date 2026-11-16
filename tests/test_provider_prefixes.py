"""Physical provenance, conservative discovery and legacy-path invariants."""
import random

import pytest

from Lineuparr.fuzzy_matcher import FuzzyMatcher

TITLES = ['Alpha Network', 'Bravo Service', 'Charlie Television', 'Delta Movies', 'Echo News']


def record(key, name, account=1, group=10, known=True, country='US| Test'):
    return {'key': key, 'name': name, 'accountId': account, 'groupId': group,
            'groupKnown': known, 'groupName': country}


def rows(prefix='ZetaNet', titles=TITLES):
    return [record(str(i), prefix + ': ' + title + ' HD') for i, title in enumerate(titles)]


def context(matcher, records, references=TITLES):
    return matcher.prepare_stream_context(records, references)


def variants(ctx):
    return {key: v.comparison for v in ctx.views if v.origin != 'original' for key in v.keys}


@pytest.mark.parametrize('prefix', ['ZetaNet', 'X&Y', 'Opaque Service', 'n7.net'])
def test_distinct_complete_identity_and_scope(prefix):
    m = FuzzyMatcher(70)
    data = rows(prefix)
    data += [record('other', data[0]['name'], account=2), record('unknown', data[1]['name'], known=False)]
    assert len(variants(context(m, data))) == 5
    actual = m.match_stream_occurrences(TITLES[0], context(m, data), {}, lineup_country='US')
    assert [(v.key, v.score, v.origin) for v in actual] == [('0', 100, 'discovered-prefix')]
    assert not variants(context(m, [record(str(i), data[0]['name']) for i in range(20)]))


def test_missing_ambiguous_sparse_and_semantic_refused():
    m = FuzzyMatcher(70)
    assert not variants(context(m, rows()[:4]))
    assert not variants(context(m, rows(), ['Alpha']))
    for prefix in ['US', 'West', 'HD', 'WABC', 'Alpha', 'ZetaNet: Other']:
        assert not variants(context(m, rows(prefix)))
    data = rows() + [record('conflict', 'Unwrapped title') for _ in range(2)]
    # A repeated duplicate is only one physical record, not extra evidence.
    assert len(variants(context(m, data))) == 5
    with pytest.raises(ValueError, match='conflicting'):
        context(m, rows() + [record('0', 'Other physical name')])


def test_permutation_duplicate_rows_and_capture_isolation():
    m = FuzzyMatcher(70)
    data = rows()
    original = context(m, data)
    shuffled = data + [data[0]]
    random.Random(9).shuffle(shuffled)
    assert original == context(m, shuffled, list(reversed(TITLES)))
    data[0]['name'] = 'mutated'
    assert variants(original)['0'] == 'Alpha Network HD'
    assert not variants(context(m, rows()[:2]))


def test_original_path_all_occurrences_and_actual_best_score():
    m = FuzzyMatcher(70)
    # Short unknown wrapper gives a genuine fuzzy original score; variants exact.
    titles = ['Alpha Documentary Television Network', *TITLES[1:]]
    data = rows('X&Y', titles)
    data.append(record('other', data[0]['name'], account=2))
    ctx = context(m, data, titles)
    baseline = m.match_all_streams(titles[0], [data[0]['name']], {})
    assert baseline and 70 <= baseline[0][1] < 100
    matches = {v.key: v for v in m.match_stream_occurrences(titles[0], ctx, {})}
    assert matches['0'].score == 100
    assert matches['other'].score == baseline[0][1]
    assert matches['other'].origin == 'original'
    # An explicit raw alias remains effective for EVERY occurrence, ties original.
    matches = m.match_stream_occurrences('Unrelated', ctx, {'Unrelated': [data[0]['name']]})
    assert {v.key for v in matches} == {'0', 'other'}
    assert all(v.score == 100 and v.origin == 'original' for v in matches)


def test_raw_exclusion_cannot_be_bypassed_by_variant():
    m = FuzzyMatcher(70)
    data = rows()
    ctx = context(m, data)
    assert not m.match_stream_occurrences(TITLES[0], ctx, {}, excluded_aliases=[data[0]['name']])
    assert not m.match_stream_occurrences(TITLES[0], ctx, {}, excluded_aliases=['ZetaNet:*'])
    # A tail-only exclusion does not silently become an exclusion of raw names.
    assert m.match_stream_occurrences(TITLES[0], ctx, {}, excluded_aliases=[TITLES[0]])


@pytest.mark.parametrize('tail', ['Alpha Network West', 'Alpha Network +1', 'Alpha Network 2',
                                  'Alpha Network International', 'Alpha Network UHD',
                                  'UK: Alpha Network', 'Alpha Network (WABC)'])
def test_new_path_never_erases_identity(tail):
    m = FuzzyMatcher(70)
    data = rows() + [record('guard', 'ZetaNet: '+tail)]
    ctx = context(m, data, TITLES + [tail])
    actual = {v.key: v for v in m.match_stream_occurrences(TITLES[0], ctx, {}, lineup_country='US', quality_aware=True)}
    assert 'guard' not in actual or actual['guard'].origin == 'original'


def test_scoped_group_country_never_uses_all_removed_escape():
    m = FuzzyMatcher(70)
    data = rows()
    for row in data:
        row['groupName'] = 'UK| Test'
    assert not m.match_stream_occurrences(TITLES[0], context(m, data), {}, lineup_country='US')


def test_single_scoring_invocation_and_no_context_epg(monkeypatch):
    m = FuzzyMatcher(70)
    ctx = context(m, rows())
    calls = []
    original = m._match_views
    def spy(*args, **kwargs):
        calls.append(args)
        return original(*args, **kwargs)
    monkeypatch.setattr(m, '_match_views', spy)
    monkeypatch.setattr(m, 'match_all_streams', lambda *a, **k: pytest.fail('recursive public scoring'))
    assert m.match_stream_occurrences(TITLES[0], ctx, {})
    assert len(calls) == 1
    legacy = FuzzyMatcher(70)
    assert legacy.match_all_streams(TITLES[0], [rows()[0]['name']], {}) == []


def test_consumer_apply_resolves_physical_winners_without_name_expansion():
    from Lineuparr.plugin import Plugin
    m = FuzzyMatcher(70)
    data = rows()
    data += [record('other', data[0]['name'], account=2)]
    matches = m.match_stream_occurrences(TITLES[0], context(m, data), {})
    by_key = {row['key']: row for row in data}
    actual = Plugin._matched_stream_objects(matches, by_key)
    assert [s['key'] for s in actual] == ['0']
    assert actual[0]['_match_score'] == matches[0].score
    assert '_match_score' not in by_key['0']


def test_literal_star_backslash_and_exact_alias_attribution():
    m = FuzzyMatcher(70)
    titles = [r'Alpha * \\ path', *TITLES[1:]]
    data = rows('X&Y', titles)
    ctx = context(m, data, titles)
    raw = data[0]['name']
    aliases = {'Target': [titles[0]]}
    match = m.match_stream_occurrences('Target', ctx, aliases)[0]
    assert match.exact_alias == titles[0] and match.key == '0'
    escaped = raw.replace('\\', '\\\\').replace('*', r'\*')
    assert not m.match_stream_occurrences('Target', ctx, aliases, excluded_aliases=[escaped])


def test_precomputed_and_fallback_results_equivalent(monkeypatch):
    import Lineuparr.matching_core as core
    m = FuzzyMatcher(70)
    data = rows()
    ctx = context(m, data)
    expected = m.match_stream_occurrences(TITLES[0], ctx, {})
    m.precompute_normalizations([v.comparison for v in ctx.views])
    assert m.match_stream_occurrences(TITLES[0], ctx, {}) == expected
    # Core selects RapidFuzz through its module-level availability flag.
    monkeypatch.setattr(core, '_USE_RAPIDFUZZ', False)
    assert FuzzyMatcher(70).match_stream_occurrences(TITLES[0], ctx, {}) == expected


def test_quality_copies_do_not_inflate_group_coverage_or_label_length():
    m = FuzzyMatcher(70)
    data = rows()
    for i, row in enumerate(rows()):
        for quality in ['SD', 'FHD', 'RAW']:
            data.append(record(f'{i}-{quality}', row['name'].removesuffix('HD')+quality))
    data.extend([record('u1', 'Unwrapped title'), record('u2', 'Another unwrapped title')])
    assert not variants(context(m, data))
    assert not variants(context(m, rows('X ')))
