"""Render the V06 individual feedback comparisons from the public run archives."""

import argparse

from 绘图 import INK, select_font, style
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from 复算 import DATA, EMOS, archives, load
from V06反馈复核 import summarize_run

COLORS = ('#176c7b','#98650e','#8252a6','#314663')
MARKERS = ('o','s','^','D')


def accuracy(m):
    return 100*m['right']/m['n']


def draw(runs, font):
    plt.rcParams.update({'font.family':select_font(font),'axes.unicode_minus':False})
    fig, axes = plt.subplots(3,2,figsize=(11.4,11.3))
    fig.subplots_adjust(top=.865,bottom=.10,left=.10,right=.96,wspace=.30,hspace=.68)
    fig.suptitle('V06 · 逐次表现、片后自评与词序线索',x=.10,y=.975,ha='left',color=INK,fontsize=20)
    fig.text(.10,.933,'4 次完成运行 · 每条线代表同一次运行，不代表组平均',color=INK,fontsize=11)
    panels = [
        ('固定 1-back · 实际组序','正确率（%）',['第一组','第二组','第三组'],
         lambda r:[accuracy(m) for m in r['n1_order']],(85,101)),
        ('固定 1–3-back · 实际组序','正确 RT 中位数（ms）',['第一组','第二组','第三组'],
         lambda r:[m['RT'] for m in r['n123_order']],(0,1500)),
        ('最后一个情绪组 · 区块内前后半','正确率（%）',['前 12 题','后 12 题'],
         lambda r:[accuracy(m) for m in r['last_condition_halves']],(80,101)),
        ('2-back · 两种诱饵','正确率（%）',['ABB','其他方向诱饵'],
         lambda r:[accuracy(r[k]) for k in ('abb','other_lure_2back')],(80,101)),
        ('看片前后 · 效价变化','片后 − 片前（分）',list(EMOS.values()),
         lambda r:[r['video'][e]['post'][0]-r['video'][e]['pre'][0] for e in EMOS],(-2.8,5.6)),
        ('看片前后 · 唤醒度变化','片后 − 片前（分）',list(EMOS.values()),
         lambda r:[r['video'][e]['post'][1]-r['video'][e]['pre'][1] for e in EMOS],(-2.1,3.7)),
    ]
    for ax,(title,ylabel,labels,get_values,ylim) in zip(axes.flat,panels):
        style(ax,title,ylabel)
        ax.set_xticks(range(len(labels)),labels)
        ax.set_xlim(-.23,len(labels)-.77)
        ax.set_ylim(*ylim)
        if ylim[0]<0:
            ax.axhline(0,color='#8293a1',linestyle='--',linewidth=.9)
        for i,run in enumerate(runs):
            xpos=[j+(i-1.5)*.033 for j in range(len(labels))]
            ax.plot(xpos,get_values(run),color=COLORS[i],marker=MARKERS[i],markersize=5,linewidth=1.5)
    fig.legend(handles=[
        Line2D([],[],color=c,marker=m,label=run['run_id'])
        for c,m,run in zip(COLORS,MARKERS,runs)
    ],loc='upper left',bbox_to_anchor=(.092,.914),ncols=4,frameon=False)
    fig.text(.10,.042,'前后半图只比较 1–3-back 同一区块内的位置。各半题型比例可能不同，下降不能直接归因于疲劳。',
             fontsize=9,color='#526578')
    fig.savefig(DATA/'V06'/'图表'/'V06-反馈复核.png',dpi=165,facecolor='white')
    plt.close(fig)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--font',help='可选中文字体文件或字体族')
    args=parser.parse_args()
    runs=[summarize_run(load(p)) for p in archives() if p.stem.startswith('V06-R')]
    assert len(runs)==4
    draw(runs,args.font)
