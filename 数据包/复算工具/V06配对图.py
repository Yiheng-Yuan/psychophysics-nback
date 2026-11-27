"""Plot V06 within-run distraction differences and absolute induction scores."""

import argparse

from 绘图 import EMOS, INK, select_font, style
from V06反馈图 import COLORS, MARKERS
from V06反馈复核 import DATA, archives, load, summarize_run
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D


def finish(fig, runs, title, filename):
    fig.suptitle(title, x=.08, ha='left', color=INK, fontsize=16, fontweight='bold')
    handles = [Line2D([], [], color=color, marker=marker, label=run['run_id'])
               for run, color, marker in zip(runs, COLORS, MARKERS)]
    fig.legend(handles=handles, loc='lower center', ncols=len(handles), frameon=False)
    fig.tight_layout(rect=(.02, .09, .99, .9))
    fig.savefig(DATA / 'V06' / '图表' / filename, dpi=165, facecolor='white')
    plt.close(fig)


def plot_distraction(runs):
    fig, axes = plt.subplots(1, 2, figsize=(10.7, 4.45))
    for ax, key, title, ylabel in [
        (axes[0], 'accuracy_pp', '准确率差', '有干扰 − 无干扰（百分点）'),
        (axes[1], 'rt_ms', '正确反应时差', '有干扰 − 无干扰（毫秒）'),
    ]:
        style(ax, title, ylabel)
        ax.set_xticks(range(len(EMOS)), list(EMOS.values()))
        ax.axhline(0, color='#8293a1', ls='--', lw=1)
        for i, (run, color, marker) in enumerate(zip(runs, COLORS, MARKERS)):
            offset = (i - (len(runs) - 1) / 2) * .045
            ax.plot([j + offset for j in range(len(EMOS))],
                    [run['distraction_by_emotion'][e][key] for e in EMOS],
                    marker=marker, color=color, lw=1.6)
    finish(fig, runs, 'V06 · 同一情绪和等级下的干扰差值', 'V06-逐次干扰差值.png')


def plot_ratings(runs):
    fig, axes = plt.subplots(2, len(EMOS), figsize=(10.7, 6.2), sharey=True)
    for row, label in enumerate(('效价', '唤醒度')):
        for col, (emotion, name) in enumerate(EMOS.items()):
            ax = axes[row, col]
            style(ax, f'{name} · {label}', '自评分数' if col == 0 else '')
            ax.set_ylim(.65, 9.35)
            ax.set_yticks((1, 3, 5, 7, 9))
            ax.set_xlim(-.27, 1.27)
            ax.set_xticks((0, 1), ('片前', '片后'))
            for i, (run, color, marker) in enumerate(zip(runs, COLORS, MARKERS)):
                # A small horizontal offset distinguishes coincident ratings.
                offset = (i - (len(runs) - 1) / 2) * .047
                scores = run['video'][emotion]
                ax.plot([offset, 1 + offset], [scores['pre'][row], scores['post'][row]],
                        marker=marker, color=color, lw=1.5)
    finish(fig, runs, 'V06 · 三种影片的片前片后评分', 'V06-自评原始分.png')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--font', help='可选中文字体文件或字体族')
    args = parser.parse_args()
    plt.rcParams.update({'font.family': select_font(args.font), 'axes.unicode_minus': False})
    runs = [summarize_run(load(path)) for path in archives() if path.stem.startswith('V06-R')]
    assert len(runs) == len(COLORS)
    plot_distraction(runs)
    plot_ratings(runs)
