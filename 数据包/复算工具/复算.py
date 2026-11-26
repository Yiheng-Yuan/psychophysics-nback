import csv, io, json, statistics as stats, zipfile
from collections import Counter, defaultdict
from pathlib import Path
from statistics import NormalDist
from itertools import groupby

DATA=Path(__file__).resolve().parent.parent
def archives():
    """Find versioned run archives without scanning figures or analysis files."""
    return sorted(DATA.glob('V[0-9][0-9]/运行包/*.zip'))

EMOS={'positive':'积极','neutral':'中性','negative':'消极'}
V_NAMES={'V01':'早期 Builder','V02':'图片加音频、同字号同颜色、80%','V03':'十词和 8/8/8 配额、80%','V04':'短版和局部词序约束、85%','V05':'束搜索与词序配对 v0.1、85%','V06':'120 秒单次影片、前后自评（已有预测试）'}
STRATA=('匹配','诱饵','其他非匹配·曾出现','其他非匹配·首次出现','其他非匹配·熟悉度不详')

def flag(value):
    return value in ('True','true','1')

def num(value):
    return float(value) if value not in (None,'') else None

def avg(vals):
    return stats.mean(vals) if vals else None

def median(vals):
    return stats.median(vals) if vals else None

def read_csv(z,name):
    if name not in z.namelist():
        return []
    return list(csv.DictReader(io.TextIOWrapper(z.open(name),encoding='utf-8-sig',newline='')))

def load(p):
    with zipfile.ZipFile(p) as z:
        assert z.testzip() is None
        if 'manifest.json' not in z.namelist():
            assert 'failure-summary.txt' in z.namelist()
            return None
        m=json.loads(z.read('manifest.json'))
        assert p.stem==m['run_id']
        m['raw']={n:read_csv(z,n+'.csv') for n in (
            'trials','blocks','level_results','summary','sequence_pairs',
            'emotion_ratings','video_log','audio_log','image_log','stage_log')}
    raw=m['raw']
    m['scored']=[r for r in raw['trials'] if flag(r['scored'])]
    assert m['recorded_trials']==len(raw['trials'])
    assert m['scored_trials']==len(m['scored'])
    assert m['correct_trials']==sum(flag(t['correct']) for t in m['scored'])
    assert m['completed_blocks']==len(raw['blocks'])
    assert (m['status']=='完成')==(len({r['emotion'] for r in raw['summary']})==3)
    m['groups']=defaultdict(list)
    for row in raw['trials']:
        m['groups'][tuple(row[k] for k in ('session','emotion','n','distractor_level','repetition'))].append(row)
    return m

def category(row):
    if flag(row['is_match']):return STRATA[0]
    if flag(row['is_lure']):return STRATA[1]
    seen=row.get('seen_before','')
    if seen=='':return STRATA[4]
    return STRATA[2] if flag(seen) else STRATA[3]

def metrics(rows):
    n=len(rows); right=sum(flag(r['correct']) for r in rows)
    answered=[r for r in rows if r['response_key'] in ('j','f')]
    hits=sum(r['response_key']=='j' and r['correct_key']=='j' for r in answered)
    fas=sum(r['response_key']=='j' and r['correct_key']=='f' for r in answered)
    targ=sum(r['correct_key']=='j' for r in answered)
    non=sum(r['correct_key']=='f' for r in answered)
    dprime=NormalDist().inv_cdf((hits+.5)/(targ+1))-NormalDist().inv_cdf((fas+.5)/(non+1)) if targ and non else None
    rts=[float(r['rt_seconds'])*1000 for r in answered if flag(r['correct']) and num(r['rt_seconds']) is not None]
    return dict(n=n,right=right,answered=len(answered),omitted=n-len(answered),acc=right/n if n else None,RT=median(rts),rtmean=avg(rts),rtcount=len(rts),hit=hits,targ=targ,fa=fas,non=non,dp=dprime)

def main_pair(run, n=None):
    pairs=defaultdict(dict)
    for lev in run['raw']['level_results']:
        if n and lev['n']!=str(n): continue
        key=tuple(lev[k] for k in ('session','emotion','n'))
        pairs[key]={
            side:metrics([r for r in run['scored'] if
                tuple(r[k] for k in ('session','emotion','n'))==key and r['distractor_level']==side])
            for side in ('with','without')
        }
        for side,met in pairs[key].items():
            assert met['n']==int(lev[side+'_scored'])
            assert met['right']==int(lev[side+'_correct'])
            assert flag(lev[side+'_pass'])==(met['right']/met['n']>=float(lev['upgrade_threshold']))
        assert flag(lev['level_pass'])==any(flag(lev[side+'_pass']) for side in ('with','without'))
    return pairs

def checks(runs):
    result=Counter()
    for run in runs:
        block_keys={tuple(r[k] for k in ('session','emotion','n','distractor_level','repetition')):r for r in run['raw']['blocks']}
        assert len(block_keys)==len(run['raw']['blocks'])
        for key,rows in run['groups'].items():
            seq=[r['word'] for r in rows]
            scored=[r for r in rows if flag(r['scored'])]
            n=int(key[2])
            result['incomplete_blocks']+=key not in block_keys
            if key in block_keys:
                block=block_keys[key]
                assert len(scored)==int(block['scored_trials'])
                assert sum(flag(r['correct']) for r in scored)==round(float(block['accuracy'])*len(scored))
                result['blocks']+=1
                if Counter(category(r) for r in scored)[STRATA[0]]==8 and Counter(category(r) for r in scored)[STRATA[1]]==8 and len(scored)==24:
                    result['8/8/8']+=1
                if n>=2 and all('lure_direction' in r for r in scored):
                    result['direction_blocks']+=1
                    result['4/4']+=Counter(r['lure_direction'] for r in scored if category(r)==STRATA[1])=={'lure_minus':4,'lure_plus':4}
            for i,r in enumerate(rows):
                assert r['trial_index']==str(i+1)
                assert flag(r['scored'])==(i>=n)
                if i<n:continue
                match=r['word']==seq[i-n]
                assert r['correct_key']==('j' if match else 'f')
                assert flag(r['is_match'])==match
                assert flag(r['correct'])==(r['response_key']==r['correct_key'])
                if r.get('seen_before','')!='':
                    assert flag(r['seen_before'])==(r['word'] in seq[:i])
                result['scored']+=1
        result['levels']+=len(main_pair(run))
    return result

def sequence_stats(complete_runs):
    grouped=defaultdict(list)
    for run in complete_runs:
        for key,rows in run['groups'].items():
            scored=[r for r in rows if flag(r['scored'])]
            if len(scored)!=24 or any(r.get('seen_before','')=='' for r in scored):
                continue
            words=[r['word'] for r in rows]
            longest_f=max((len(list(group)) for key_value,group in groupby(
                r['correct_key'] for r in scored) if key_value=='f'),default=0)
            grouped[key[2]].append({
                'new':sum(not flag(r['seen_before']) for r in scored),
                'vocabulary':len(set(words)),
                'low_diversity':any(len(set(words[i:i+6]))<=2 for i in range(len(words)-5)),
                'longest_f':longest_f,
                'familiarity_strategy_correct':sum(
                    (r['correct_key']=='j')==flag(r['seen_before']) for r in scored),
                'all_f_correct':sum(r['correct_key']=='f' for r in scored),
            })
    return {n:{
        'blocks':len(blocks),
        'new_mean':avg([b['new'] for b in blocks]),
        'vocabulary_mean':avg([b['vocabulary'] for b in blocks]),
        'low_diversity_blocks':sum(b['low_diversity'] for b in blocks),
        'longest_f':max(b['longest_f'] for b in blocks),
        'familiarity_strategy_mean':avg([b['familiarity_strategy_correct'] for b in blocks]),
        'all_f_strategy_mean':avg([b['all_f_correct'] for b in blocks]),
    } for n,blocks in grouped.items()}


def version_stats(runs):
    full=[r for r in runs if r['status']=='完成']
    s=[r for run in full for r in run['scored']]
    byn=defaultdict(list)
    for row in s:byn[row['n']].append(row)
    pos=[]
    for i in range(3):
        rows=[r for run in full for r in run['scored'] if r['n']=='1' and r['emotion']==run['emotion_order'][i]]
        pos.append(metrics(rows))
    pairs=[p for run in full for p in main_pair(run).values()]
    pairs1=[p for run in full for p in main_pair(run,1).values()]
    def pair_stat(ps):
        delta=[100*(p['with']['acc']-p['without']['acc']) for p in ps]
        return dict(n=len(delta),win=sum(x>0 for x in delta),lose=sum(x<0 for x in delta),tie=sum(x==0 for x in delta),mean=avg(delta),median=median(delta))
    result={'check':dict(checks(runs)),'status':dict(Counter(r['status'] for r in runs)),
    'sequence':sequence_stats(full),'all':metrics([r for run in runs for r in run['scored']]),'full':metrics(s),'N':{n:metrics(rows) for n,rows in byn.items()},
    'strata':{k:metrics([r for r in s if category(r)==k]) for k in STRATA},'by_n_strata':{},
    'pairs':pair_stat(pairs),'pairs1':pair_stat(pairs1),'position':pos,
    'conditions1':{f'{e}_{d}':metrics([r for r in s if r['n']=='1' and r['emotion']==e and r['distractor_level']==d]) for e in EMOS for d in ('without','with')},'runs':[],
    'pair_distances':[float(r['pair_distance']) for run in full for r in run['raw']['sequence_pairs']],
    'stage_counts':dict(Counter(r['stage'] for run in runs for r in run['raw']['stage_log']))}
    for n, rows in byn.items():
        result['by_n_strata'][n]={k:metrics([r for r in rows if category(r)==k]) for k in STRATA}
    for r in runs:
        task=[float(t['trial_elapsed_seconds']) for t in r['raw']['trials'] if num(t.get('trial_elapsed_seconds')) is not None]
        omits={}
        for e in EMOS:
            for n in sorted({row['n'] for row in r['scored'] if row['emotion']==e}):
                met=metrics([row for row in r['scored'] if row['n']==n and row['emotion']==e])
                if met['omitted']: omits[e+'-'+n]=(met['omitted'],met['n'])
        pos1=[metrics([row for row in r['scored'] if row['emotion']==e and row['n']=='1']) for e in r['emotion_order']]
        result['runs'].append(dict(id=r['run_id'],status=r['status'],total=len(r['raw']['trials']),blocks=len(r['raw']['blocks']),levels=len(r['raw']['level_results']),met=metrics(r['scored']),maxn={row['emotion']:row['highest_either_n'] for row in r['raw']['summary']},
          position=pos1,order=r['emotion_order'],omits=omits,task_sec=sum(task) if task and len(task)==len(r['raw']['trials']) else None,
          ratings=[{k:row[k] for k in ('emotion','stage','valence','arousal')} for row in r['raw']['emotion_ratings']],
          videos=[{k:row[k] for k in ('emotion','media_duration_seconds','actual_elapsed_seconds','status')} for row in r['raw']['video_log']],
          end_stage=r['raw']['stage_log'][-1]['stage'] if r['raw']['stage_log'] else None))
    return result

if __name__=='__main__':
    groups=defaultdict(list)
    for p in archives():
        r=load(p)
        if r:groups[p.stem[:3]].append(r)
    result={v:version_stats(rs) for v,rs in groups.items()}
    print(json.dumps(result,ensure_ascii=False,indent=2))
