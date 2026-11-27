"""Recompute V06 induction, response-order and 2-back sequence diagnostics."""

import argparse
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


def distraction_pairs(run, emotion):
    """One with-minus-without difference at each common level."""
    pairs = []
    for n in sorted(COMMON_LEVELS):
        rows = fixed_rows(run, emotion, {n})
        without, with_distractors = (
            metrics([row for row in rows if row['distractor_level'] == side])
            for side in SIDES
        )
        assert without['n'] == with_distractors['n'] == 24
        pairs.append((
            100 * (with_distractors['right'] - without['right']) / 24,
            with_distractors['RT'] - without['RT'],
        ))
    return pairs


def distraction_summary(pairs):
    return {'accuracy_pp': mean(a for a, _ in pairs),
            'rt_ms': median(rt for _, rt in pairs)}


def false_alarms(rows):
    """Return J presses and valid F/J answers for each nonmatching category."""
    label_to_rows = {key: [] for key in ('lure_minus', 'lure_plus', *STRATA[2:4])}
    for row in rows:
        kind = category(row)
        if kind == STRATA[1]:
            kind = row['lure_direction']
        if kind != STRATA[0]:
            label_to_rows[kind].append(row)
    result = {}
    for kind, trials in label_to_rows.items():
        stat = metrics(trials)
        result[kind] = (stat['fa'], stat['non'])
    return result


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
    pairs = {e: distraction_pairs(run, e) for e in EMOS}
    fixed = [row for e in EMOS for row in fixed_rows(run, e)]
    return {
        'run_id': run['run_id'],
        'order': order,
        'duration_seconds': float(run['raw']['stage_log'][-1]['elapsed_from_start_seconds']),
        'n1_order': [summarize(fixed_rows(run, e, {'1'})) for e in order],
        'n123_order': [summarize(fixed_rows(run, e)) for e in order],
        'by_emotion': {e: summarize(fixed_rows(run,e)) for e in EMOS},
        'distraction_by_emotion': {e: distraction_summary(p) for e, p in pairs.items()},
        'distraction_all': distraction_summary([pair for p in pairs.values() for pair in p]),
        'false_alarms': false_alarms(fixed),
        'halves': [summarize(within_early), summarize(within_late)],
        'last_condition_halves': [summarize(within_last_early), summarize(within_last_late)],
        'video': video_diagnostics(run),
        'abb': summarize(patterns['abb']),
        'other_lure_2back': summarize(patterns['other_lure']),
    }


def summarize_all(runs):
    by_emotion = {e: [r for run in runs for r in fixed_rows(run,e)] for e in EMOS}
    by_e_without_abb = {}
    paired_deltas = [pair for run in runs for e in EMOS for pair in distraction_pairs(run, e)]
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


def markdown(runs):
    lines = [
        '# V06 · 逐次配对与作答类型',
        '',
        '> 由 [V06反馈复核.py](../复算工具/V06反馈复核.py) 生成。'
        '分析对象为四次正式运行共同完成的 1–3-back。',
        '',
        '## 有干扰减去无干扰',
        '',
        '同一次运行、同一情绪、同一 N 内配对。准确率列为各对准确率差的均值（百分点），'
        '反应时列为各对正确反应时中位数之差的中位数（毫秒）。'
        '每种情绪每次含 3 对，合计列含 9 对。正的反应时差表示有干扰时更慢。',
        '',
        '| 运行 | 积极（百分点 / ms） | 中性（百分点 / ms） | 消极（百分点 / ms） | 三种情绪合计（百分点 / ms） |',
        '| --- | ---: | ---: | ---: | ---: |',
    ]
    for run in runs:
        comparisons = [*run['distraction_by_emotion'].values(), run['distraction_all']]
        cells = [f"{d['accuracy_pp']:+.2f} / {d['rt_ms']:+.1f}" for d in comparisons]
        lines.append('| ' + ' | '.join([run['run_id'], *cells]) + ' |')
    lines += [
        '',
        '![各运行在三种影片条件下的干扰差值](图表/V06-逐次干扰差值.png)',
        '',
        '## 各次运行的情绪条件表现',
        '',
        '每格为正确率（%）/ 校正辨别力 d′。每次每种情绪有 144 个计分试次。'
        '最后一行按运行等权求平均，d′ 先在各次运行内计算。',
        '',
        '| 运行 | 积极 | 中性 | 消极 |',
        '| --- | ---: | ---: | ---: |',
    ]
    for run in runs:
        cells = [f"{100*m['right']/m['n']:.1f} / {m['dp']:.2f}"
                 for m in run['by_emotion'].values()]
        lines.append('| ' + ' | '.join([run['run_id'], *cells]) + ' |')
    cells = []
    for emotion in EMOS:
        values = [r['by_emotion'][emotion] for r in runs]
        accuracy = mean(100 * m['right'] / m['n'] for m in values)
        dprime = mean(m['dp'] for m in values)
        cells.append(f'{accuracy:.1f} / {dprime:.2f}')
    lines.append('| ' + ' | '.join(['运行等权均值', *cells]) + ' |')
    lines += [
        '',
        '## 匹配与非匹配的作答',
        '',
        '合并三种情绪及有无干扰。每格为按 J 的次数 / 该类有效 J/F 作答数。'
        '匹配列是命中，其余是误报。N−1 诱饵只取 2–3-back，1-back 不适用。漏答不进这些比率的分母。',
        '',
        '| 运行 | 匹配命中 | N−1 诱饵误报 | N+1 诱饵误报 | 熟悉非匹配误报 | 首次出现非匹配误报 |',
        '| --- | ---: | ---: | ---: | ---: | ---: |',
    ]
    for run in runs:
        emotions = list(run['by_emotion'].values())
        hits = (sum(m['hit'] for m in emotions), sum(m['targ'] for m in emotions))
        cells = [f'{numerator}/{denominator}' for numerator, denominator
                 in (hits, *run['false_alarms'].values())]
        lines.append('| ' + ' | '.join([run['run_id'], *cells]) + ' |')
    lines += [
        '',
        '## 看片前后自评',
        '',
        '每条线连接同一次运行在同一影片条件下的片前与片后绝对分数。纵轴统一为 1–9 分。',
        '',
        '![各次运行片前片后效价与唤醒度绝对分](图表/V06-自评原始分.png)',
        '',
        '[返回 V06 汇总](README.md)',
    ]
    return '\n'.join(lines)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--markdown', action='store_true', help='输出逐次配对与作答类型表')
    args = parser.parse_args()
    runs = [load(path) for path in archives() if path.stem.startswith('V06-R')]
    assert all(r['status']=='完成' for r in runs)
    summaries = [summarize_run(r) for r in runs]
    if args.markdown:
        print(markdown(summaries))
    else:
        print(json.dumps({'runs': summaries, 'aggregate': summarize_all(runs)},
                         ensure_ascii=False, indent=2))
