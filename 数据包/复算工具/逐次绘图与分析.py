"""Generate the trajectory plots and tables for each archived run."""

import argparse
from collections import defaultdict

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from 绘图 import INK, SIDES, select_font, style
from 复算 import DATA, EMOS, STRATA, archives, category, flag, load, main_pair, metrics

SIDESTYLES = {'without': ('-', 'o'), 'with': ('--', 's')}

def table(headers, rows):
    return '\n'.join([
        '| ' + ' | '.join(headers) + ' |',
        '| ' + ' | '.join('---' for _ in headers) + ' |',
        *['| ' + ' | '.join(map(str, row)) + ' |' for row in rows],
    ])

def format_value(value, decimals=1):
    return '—' if value is None else f'{value:.{decimals}f}'

def ratio(correct, count):
    return '—' if not count else f'{correct}/{count}（{100*correct/count:.1f}%）'

def cells_for(run):
    """Condition-level cells, with completeness determined from block logs."""
    expected = run['configuration'].get('repeat_blocks', 1)
    by_condition = defaultdict(list)
    complete = defaultdict(set)
    for row in run['scored']:
        by_condition[row['emotion'], int(row['n']), row['distractor_level']].append(row)
    for block in run['raw']['blocks']:
        complete[block['emotion'], int(block['n']), block['distractor_level']].add(block['repetition'])
    cells = {}
    for key, rows in by_condition.items():
        count = len(complete[key])
        cells[key] = {**metrics(rows), 'block_count': count, 'expected': expected,
                      'complete': count == expected}
    return cells

def ordered_emotions(run):
    return list(dict.fromkeys((run['emotion_order'] or []) + list(EMOS)))

def draw_run(run, cells):
    if not cells:
        return
    emotions = ordered_emotions(run)
    levels = sorted({n for _,n,_ in cells})
    rt_top = max(1300, max((m['RT'] or 0) for m in cells.values())*1.18)
    fig, axes = plt.subplots(2, 3, figsize=(11.5, 6.7), sharex=True)
    fig.subplots_adjust(left=.085, right=.98, top=.82, bottom=.18, wspace=.34, hspace=.61)
    fig.suptitle(f"{run['run_id']} · 按情绪和 N 的逐次表现", x=.085, y=.965, ha='left', color=INK, fontsize=18)
    fig.text(.085,.900,'  →  '.join(EMOS[e] for e in emotions)+'   |   '+run['status'],fontsize=10,color=INK)
    handles = [
        Line2D([],[],color=c,linestyle=SIDESTYLES[s][0],marker=SIDESTYLES[s][1],label=label)
        for s,(label,c) in SIDES.items()
    ]
    fig.legend(handles=handles, loc='lower left', bbox_to_anchor=(.078,.055),
               ncol=2, frameon=False)
    for col, emotion in enumerate(emotions):
        for row in range(2):
            ax=axes[row,col]
            label='正确率（%）' if row==0 else '正确 RT 中位数（ms）'
            style(ax, f"{EMOS[emotion]} · {'准确率' if row==0 else '反应时'}",label if col==0 else '')
            ax.set_ylim(0, 105 if row==0 else rt_top)
            ax.set_xlim(min(levels)-.38, max(levels)+.38)
            ax.set_xticks(levels)
            if row==1:
                ax.set_xlabel('N-back 等级')
            any_value=False
            for side,(_,color) in SIDES.items():
                line, marker = SIDESTYLES[side]
                offset = -.06 if side=='without' else .06
                xs, ys = [], []
                for n in levels:
                    m=cells.get((emotion,n,side))
                    value=None if m is None else (100*m['acc'] if row==0 else m['RT'])
                    xs.append(n+offset)
                    ys.append(value if value is not None and m['complete'] else float('nan'))
                    if value is not None:
                        any_value=True
                        ax.scatter(n+offset,value,marker=marker,s=30,color=color,
                                   facecolors=color if m['complete'] else 'white',zorder=4)
                ax.plot(xs,ys,color=color,linestyle=line,linewidth=1.5)
            if not any_value:
                ax.text(.5,.48,'无可用数据',transform=ax.transAxes,ha='center',color='#758593',fontsize=10)
    fig.text(.085,.036,'空心点表示该情绪 × N × 干扰组合未完成计划区块；漏答计入准确率，反应时仅统计正确作答。',
             fontsize=9,color='#526578')
    output = DATA / run['run_id'][:3] / '图表'
    output.mkdir(exist_ok=True)
    fig.savefig(output/f"{run['run_id']}.png",dpi=145,facecolor='white')
    plt.close(fig)

def paired_section(run):
    pairs = main_pair(run)
    if not pairs:
        return ['未达到可配对比较的等级。部分区块保留在上表。']
    rows = []
    for (_, emotion, n), pair in pairs.items():
        a, b = pair['without'], pair['with']
        rt_delta = None if a['RT'] is None or b['RT'] is None else b['RT']-a['RT']
        dp_delta = None if a['dp'] is None or b['dp'] is None else b['dp']-a['dp']
        rows.append((EMOS[emotion], n, f"{100*(b['acc']-a['acc']):+.1f}",
                     '—' if rt_delta is None else f'{rt_delta:+.0f}',
                     '—' if dp_delta is None else f'{dp_delta:+.2f}',
                     b['omitted']-a['omitted']))
    directions=[(m['with']['acc']>m['without']['acc'])-(m['with']['acc']<m['without']['acc'])
                for m in pairs.values()]
    return [
        f"有干扰准确率较高／较低／持平为 **{directions.count(1)}／{directions.count(-1)}／{directions.count(0)}**。"
        '下表均为同一情绪、同一 N 内的「有干扰减无干扰」。',
        '',
        table(['情绪','N','准确率差（百分点）','正确 RT 中位数差（ms）','校正 d′ 差','漏答数差'],rows),
    ]

def describe(run, cells):
    rid=run['run_id']
    lines=[f'### {rid}', '',
           f"[原始数据 ZIP](运行包/{rid}.zip) · 状态：{run['status']} · 计划顺序："+
           ' → '.join(EMOS[e] for e in ordered_emotions(run)), '']
    if not cells:
        return lines+['没有计分试次，无法估计准确率或反应时。', '']
    overall=metrics(run['scored'])
    summary={r['emotion']:r['highest_either_n'] for r in run['raw']['summary']}
    highest='／'.join(summary.get(e,'—') for e in EMOS)
    lines += [
        f"整体正确 **{ratio(overall['right'],overall['n'])}**，漏答 {overall['omitted']}，"
        f"正确 RT 中位数 {format_value(overall['RT'],0)} ms，最高通过 N（积极／中性／消极）为 {highest}。",
        '',
        f'![{rid} 按情绪、难度与有无干扰的准确率和反应时](图表/{rid}.png)',
        '',
    ]
    order={e:i for i,e in enumerate(ordered_emotions(run))}
    sorted_cells=sorted(cells.items(),key=lambda item:(order[item[0][0]],item[0][1],item[0][2]!='without'))
    lines.extend([table(
        ['情绪','N','干扰','完成／计划区块','正确／计分','漏答','正确 RT 中位数（ms）','命中／有效匹配','虚报／有效非匹配','校正 d′'],
        [(EMOS[e],n,SIDES[side][0],f"{m['block_count']}/{m['expected']}",ratio(m['right'],m['n']),
          m['omitted'],format_value(m['RT'],0),ratio(m['hit'],m['targ']),ratio(m['fa'],m['non']),format_value(m['dp'],2))
         for (e,n,side),m in sorted_cells]), ''])
    issues=[(k,m) for k,m in sorted_cells if m['omitted']]
    if issues:
        (e,n,side),m=max(issues,key=lambda item:item[1]['omitted']/item[1]['n'])
        lines.extend([f"漏答比例最高的组合是 **{EMOS[e]} · {n}-back · {SIDES[side][0]}**（{ratio(m['omitted'],m['n'])}）。", ''])
    levels_one = [(emotion, [cells.get((emotion, 1, side)) for side in SIDES])
                  for emotion in ordered_emotions(run)]
    if all(all(cell and cell['complete'] for cell in parts) for _,parts in levels_one):
        position_scores = [
            f"{EMOS[emotion]} {ratio(sum(m['right'] for m in parts),sum(m['n'] for m in parts))}"
            for emotion, parts in levels_one
        ]
        lines.extend(['**固定 1-back 的实际组序**：'+' → '.join(position_scores)+'。', ''])
    lines.extend([*paired_section(run), ''])


    types=defaultdict(list)
    for scored in run['scored']:
        types[category(scored)].append(scored)
    lines.extend([table(['试次类型','正确／计分','正确 RT 中位数（ms）'],
        [(label,ratio(m['right'],m['n']),format_value(m['RT'],0))
         for label in STRATA if (m:=metrics(types[label]))['n']]), ''])

    ratings={(r['emotion'],r['stage']):(r['valence'],r['arousal']) for r in run['raw']['emotion_ratings']}
    if ratings:
        lines.extend([table(['影片条件','效价前→后','唤醒度前→后'],
            [(EMOS[e],f'{pre[0]}→{post[0]}',f'{pre[1]}→{post[1]}') for e in ordered_emotions(run)
             if (pre:=ratings.get((e,'pre_induction'))) and (post:=ratings.get((e,'post_induction')))]), ''])
    return lines

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--font',help='可选中文字体文件或字体族')
    args=parser.parse_args()
    plt.rcParams.update({'font.family':select_font(args.font),'axes.unicode_minus':False})
    groups=defaultdict(list)
    for archive in archives():
        if run:=load(archive):
            groups[archive.stem[:3]].append(run)
    for version,runs in groups.items():
        lines=[f'# {version} 逐次运行分析', '',
               '[返回版本汇总](README.md) · [逐次分析索引](../README.md)', '',
               '每个编号是一次去标识化运行。档案无法确认哪些编号属于同一人。'
               '漏答计入正确率分母，RT 中位数仅用正确且有记录的 J/F 作答，校正 d′ 按有效作答计算。'
               '有完整区块日志且达到计划区块数的条件才在图中连线。', '',
               ' · '.join(f"[{r['run_id']}](#{r['run_id'].lower()})" for r in runs), '']
        for run in runs:
            cells=cells_for(run)
            draw_run(run,cells)
            lines.extend(describe(run,cells))
        if version=='V06':
            lines.extend(['### V06-FAIL-01', '',
                          '[故障摘要 ZIP](运行包/V06-FAIL-01.zip)。影片结束时退出，无计分试次。', ''])
        (DATA/version/'逐次分析.md').write_text('\n'.join(lines))

if __name__=='__main__':
    main()
