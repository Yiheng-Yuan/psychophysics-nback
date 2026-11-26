"""Recompute V06 induction, response-order and 2-back sequence diagnostics."""

from collections import Counter
import json
from statistics import median, mean

from 复算 import DATA, EMOS, STRATA, archives, category, flag, load, metrics

SIDES = ('without', 'with')
COMMON_LEVELS = {'1', '2', '3'}


def scored(rows):
    return [row for row in rows if flag(row['scored'])]


def summarize(rows):
    data = metrics(rows)
    return {key: data[key] for key in ('n', 'right', 'omitted', 'RT', 'rtmean', 'dp', 'hit', 'targ', 'fa', 'non')}


def fixed_rows(run, emotion, levels=COMMON_LEVELS):
    return [r for r in run['scored'] if r['emotion'] == emotion and r['n'] in levels]


def word_patterns(run):
    patterns = {kind: [] for kind in ('abb', 'other_lure', 'all', 'adjacent_match')}
    by_emotion = Counter()
    for key, rows in run['groups'].items():
        if key[2] != '2':
            continue
        words = [r['word'] for r in rows]
        for i, row in enumerate(rows):
            if not flag(row['scored']):
                continue
            patterns['all'].append(row)
            if words[i] == words[i-1] and words[i] != words[i-2]:
                patterns['abb'].append(row)
                by_emotion[row['emotion']] += 1
                assert row['correct_key'] == 'f' and row['lure_direction'] == 'lure_minus'
            elif flag(row['is_lure']):
                patterns['other_lure'].append(row)
            if words[i] == words[i-1] and flag(row['is_match']):
                patterns['adjacent_match'].append(row)
    assert len(patterns['all']) == 144
    assert len(patterns['abb']) == 24
    assert all(by_emotion[e] == 8 for e in EMOS)
    return patterns


def video_diagnostics(run):
    stages = run['raw']['stage_log']
    summaries = {}
    for emotion in EMOS:
        ratings = {
            r['stage']: [int(r['valence']), int(r['arousal'])]
            for r in run['raw']['emotion_ratings'] if r['emotion'] == emotion
        }
        start = float(next(r['elapsed_from_start_seconds'] for r in stages
                           if r['emotion'] == emotion and r['stage'] == 'induction_end'))
        after = {
            r['n']: float(r['elapsed_from_start_seconds']) - start for r in stages
            if r['emotion'] == emotion and r['stage'] == 'level_start'
        }
        assert len(ratings) == 2 and COMMON_LEVELS.issubset(after)
        summaries[emotion] = {
            'pre': ratings['pre_induction'], 'post': ratings['post_induction'],
            'seconds_to_level': after,
        }
    return summaries


def summarize_run(run):
    order = run['emotion_order']
    within_early, within_late = [], []
    within_last_early, within_last_late = [], []
    for k, block in run['groups'].items():
        if k[2] not in COMMON_LEVELS:
            continue
        rows = scored(block)
        assert len(rows) == 24
        within_early.extend(rows[:12])
        within_late.extend(rows[12:])
        if k[1] == order[-1]:
            within_last_early.extend(rows[:12])
            within_last_late.extend(rows[12:])
    patterns = word_patterns(run)
    assert not patterns['adjacent_match']
    return {
        'run_id': run['run_id'],
        'order': order,
        'duration_seconds': float(run['raw']['stage_log'][-1]['elapsed_from_start_seconds']),
        'n1_order': [summarize(fixed_rows(run, e, {'1'})) for e in order],
        'n123_order': [summarize(fixed_rows(run, e)) for e in order],
        'by_emotion': {e: summarize(fixed_rows(run,e)) for e in EMOS},
        'halves': [summarize(within_early), summarize(within_late)],
        'last_condition_halves': [summarize(within_last_early), summarize(within_last_late)],
        'video': video_diagnostics(run),
        'abb': summarize(patterns['abb']),
        'other_lure_2back': summarize(patterns['other_lure']),
    }


def summarize_all(runs):
    by_emotion = {e: [r for run in runs for r in fixed_rows(run,e)] for e in EMOS}
    by_e_without_abb = {}
    paired_deltas = []
    for run in runs:
        for e in EMOS:
            for n in ('1','2','3'):
                rows = fixed_rows(run,e,{n})
                conditions = [summarize([r for r in rows if r['distractor_level']==s]) for s in SIDES]
                left, right = conditions
                assert left['n']==right['n']==24
                paired_deltas.append((100*(right['right']-left['right'])/24, right['RT']-left['RT']))
    for e, rows in by_emotion.items():
        keys = {(run['run_id'], r['session'], r['distractor_level'],r['trial_index'])
                for run in runs for r in word_patterns(run)['abb'] if r['emotion']==e}
        by_e_without_abb[e] = summarize([
            r for r in rows if r['n']!='2' or
            (r['participant'],r['session'],r['distractor_level'],r['trial_index']) not in keys
        ])
    dd = [p[0] for p in paired_deltas]
    rt = [p[1] for p in paired_deltas]
    halves = [[], []]
    last_halves = [[], []]
    for run in runs:
        for key, block in run['groups'].items():
            if key[2] not in COMMON_LEVELS:
                continue
            block = scored(block)
            for i, part in enumerate((block[:12], block[12:])):
                halves[i].extend(part)
                if key[1] == run['emotion_order'][-1]:
                    last_halves[i].extend(part)
    return {
        'halves': [summarize(rows) for rows in halves],
        'last_condition_halves': [summarize(rows) for rows in last_halves],
        'halves_by_type': [{kind:summarize([r for r in rows if category(r)==kind])
                            for kind in STRATA if any(category(r)==kind for r in rows)}
                           for rows in halves],
        'by_emotion': {e:summarize(rows) for e,rows in by_emotion.items()},
        'by_emotion_without_abb':by_e_without_abb,
        'n1_order': [summarize([r for run in runs for r in fixed_rows(
            run,run['emotion_order'][i],{'1'})]) for i in range(3)],
        'n123_order': [summarize([r for run in runs for r in fixed_rows(
            run,run['emotion_order'][i])]) for i in range(3)],
        'overall_by_side':{side:summarize([r for rows in by_emotion.values()
                                          for r in rows if r['distractor_level']==side]) for side in SIDES},
        'paired_correctness_direction': dict(Counter((x>0)-(x<0) for x in dd)),
        'paired_rt_direction': dict(Counter((x>0)-(x<0) for x in rt)),
        'median_paired_rt_ms':median(rt),
        'mean_paired_accuracy_pp':mean(dd),
        'abb':summarize([r for run in runs for r in word_patterns(run)['abb']]),
        'other_lure_2back':summarize([r for run in runs for r in word_patterns(run)['other_lure']]),
    }


if __name__ == '__main__':
    runs = [load(path) for path in archives() if path.stem.startswith('V06-R')]
    assert all(r['status']=='完成' for r in runs)
    result = {'runs':[summarize_run(r) for r in runs], 'aggregate':summarize_all(runs)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
