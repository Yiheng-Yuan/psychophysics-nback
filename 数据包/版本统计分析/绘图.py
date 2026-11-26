"""Render static figures for the existing pilot reports from de-identified data."""

import argparse
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Patch

from 复算 import DATA, EMOS, flag, load, metrics

OUT = Path(__file__).resolve().parent / '图表'
SIDES = {'without': ('无干扰', '#176c7b'), 'with': ('有干扰', '#ad5325')}
PALETTE = {'positive': '#98650e', 'neutral': '#176c7b', 'negative': '#8252a6'}
INK = '#203346'

def select_font(path):
    candidates = [
        path,
        '/System/Library/Fonts/STHeiti Medium.ttc',
        '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
        'Noto Sans CJK SC',
        'Microsoft YaHei',
    ]
    for candidate in filter(None, candidates):
        font = Path(candidate)
        if font.is_file():
            font_manager.fontManager.addfont(str(font))
            return font_manager.FontProperties(fname=str(font)).get_name()
        if any(item.name == str(candidate) for item in font_manager.fontManager.ttflist):
            return str(candidate)
    raise SystemExit('需要中文字体。可用 --font 指定 Noto Sans CJK 的文件路径。')

def included_rows(version, runs):
    if version != 'V01':
        return [row for run in runs if run['status'] == '完成' for row in run['scored']]
    # The early pilot has no full run. Plot only trial rows with a block summary.
    keys = ('session', 'emotion', 'n', 'distractor_level', 'repetition')
    rows = []
    for run in runs:
        for block in run['raw']['blocks']:
            block_key = tuple(block[k] for k in keys)
            rows.extend(r for r in run['groups'][block_key] if flag(r['scored']))
    return rows

def style(ax, title, ylabel):
    ax.set_title(title, loc='left', pad=7, fontsize=13, color=INK, fontweight='bold')
    ax.set_ylabel(ylabel)
    ax.grid(axis='y', color='#dfe7ee', linewidth=.75)
    ax.set_axisbelow(True)
    ax.spines[['top', 'right']].set_visible(False)
    ax.spines[['left', 'bottom']].set_color('#abb9c6')

def bar_panel(ax, grouped, title, label, value, units, top, count_key):
    style(ax, title, label)
    ax.set_ylim(0, top)
    ax.set_xticks(range(3), EMOS.values())
    ax.set_xlim(-.55, 2.55)
    for i, side in enumerate(SIDES):
        _, color = SIDES[side]
        for j, emotion in enumerate(EMOS):
            m = grouped[emotion, side]
            y = value(m)
            xpos = j + (-.18 if i == 0 else .18)
            if y is None:
                ax.annotate('—', (xpos, 0), xytext=(0, 4), textcoords='offset points',
                            ha='center', color='#778694', fontsize=10)
                continue
            ax.bar(xpos, y, width=.31, color=color)
            ax.annotate(f'{y:{units}}\nn={m[count_key]}', (xpos, y), xytext=(0, 4),
                        textcoords='offset points', ha='center', color=INK, fontsize=8)

def trend_panel(ax, series, levels, title, ylabel, value, top):
    style(ax, title, ylabel)
    ax.set_ylim(0, top)
    ax.set_xticks(levels)
    ax.set_xlabel('N-back 等级')
    for emotion, name in EMOS.items():
        values = [value(series[emotion, n]) for n in levels]
        ax.plot(levels, [float('nan') if v is None else v for v in values],
                marker='o', markersize=5, linewidth=1.8, color=PALETTE[emotion], label=name)
    ax.legend(loc='lower right' if ylabel == '正确率（%）' else 'upper right',
              frameon=False, ncol=3)

def rating(x):
    return None if x['acc'] is None else x['acc'] * 100

def omission(x):
    return 100 * x['omitted'] / x['n'] if x['n'] else None

def render(version, runs):
    rows = included_rows(version, runs)
    levels = sorted({int(r['n']) for r in rows})
    assert levels and levels[0] == 1, version
    grouped = {(e, s): metrics([r for r in rows if r['n']=='1'
                                 and r['emotion']==e and r['distractor_level']==s])
               for e in EMOS for s in SIDES}
    series = {(e, n): metrics([r for r in rows if int(r['n'])==n and r['emotion']==e])
              for e in EMOS for n in levels}

    has_trend = len(levels) > 1
    fig, axs = plt.subplots(3 if has_trend else 2, 2, figsize=(11.4, 12.0 if has_trend else 8.4))
    fig.subplots_adjust(top=.865 if has_trend else .79, bottom=.102,
                        left=.095, right=.97, hspace=.64, wspace=.32)
    fig.suptitle(f'{version}  情绪条件下的准确率、反应时与漏答',
                 x=.095, y=.975, ha='left', fontsize=20, color=INK, fontweight='bold')
    scope = ('仅一块完成记录：积极情绪、无干扰。其他条件缺数据。'
             if version=='V01' else f"仅纳入完成三种情绪的运行（{sum(x['status']=='完成' for x in runs)} 次）。前四图固定 1-back。")
    fig.text(.095, .935 if has_trend else .913, scope, color=INK, fontsize=11)
    fig.legend(handles=[Patch(color=c,label=t) for t,c in SIDES.values()],
               loc='upper left', bbox_to_anchor=(.09, .920 if has_trend else .89), frameon=False, ncol=2)

    rt_cap = max(1800, max((m['RT'] or 0 for m in (*grouped.values(), *series.values())), default=0)*1.2)
    bar_panel(axs[0,0], grouped, '1-back 准确率', '正确率（%）', rating, '.1f', 122, 'n')
    bar_panel(axs[0,1], grouped, '1-back 正确反应时', '中位数（ms）', lambda m:m['RT'], '.0f', rt_cap, 'rtcount')
    bar_panel(axs[1,0], grouped, '1-back 漏答率', '漏答率（%）', omission, '.1f', 122, 'n')
    for m in grouped.values():
        m['有效作答'] = m['targ'] + m['non']
    bar_panel(axs[1,1], grouped, '1-back 辨别力', '校正 d′', lambda m:m['dp'], '.2f', 5.3, '有效作答')
    percent_axes = [axs[0,0], axs[1,0]]
    footnote = '柱上 n 为该指标使用的试次数；— 表示缺失。'
    if has_trend:
        trend_panel(axs[2,0], series, levels, '各 N 的准确率 · 合并有无干扰', '正确率（%）', rating, 110)
        trend_panel(axs[2,1], series, levels, '各 N 的正确反应时 · 合并有无干扰', '中位数（ms）', lambda m:m['RT'], rt_cap)
        percent_axes.append(axs[2,0])
        footnote += '折线按达到相应 N 的运行汇总，不能解释为同一批人随等级的变化。'
    for ax in percent_axes:
        ax.set_yticks((0,25,50,75,100))
    fig.text(.095,.045,footnote,fontsize=10,color='#526578')
    OUT.mkdir(exist_ok=True)
    fig.savefig(OUT/f'{version}-情绪表现.png', dpi=170, facecolor='white')
    plt.close(fig)
    print(f'{version}: {len(rows)} 个计分试次，N={levels}')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--font',help='可选中文字体文件或字体族')
    args=parser.parse_args()
    plt.rcParams.update({'font.family':select_font(args.font),
                         'axes.labelcolor':INK, 'xtick.color':INK,
                         'ytick.color':INK, 'axes.unicode_minus':False})
    groups=defaultdict(list)
    for p in sorted(DATA.glob('*.zip')):
        run=load(p)
        if run:
            groups[p.stem[:3]].append(run)
    for version,runs in groups.items():
        render(version,runs)

if __name__=='__main__':
    main()
