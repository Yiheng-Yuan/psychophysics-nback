"""Build or check the public run index and ZIP checksums."""

import argparse
import csv
from math import isclose
from hashlib import sha256
from io import StringIO

from 复算 import DATA, archives, checks, load, metrics

ROOT = DATA.parent
COLUMNS = (
    'run_id', 'version', 'archive', 'code_archive', 'status',
    'include_complete_run_summary', 'reason', 'recorded_trials', 'scored_trials',
    'correct_trials', 'completed_blocks', 'emotion_order',
)


def index_text(paths):
    output = StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=COLUMNS, lineterminator='\n')
    writer.writeheader()
    for path in paths:
        version = path.parent.parent.name
        code = f'代码包/{version}.zip'
        assert (ROOT / code).is_file(), code
        run = load(path)
        row = dict(run_id=path.stem, version=version, archive=path.relative_to(ROOT).as_posix(),
                   code_archive=code, include_complete_run_summary=0)
        if run is None:
            row.update(status='故障摘要', reason='仅归档故障摘要，无运行清单')
        else:
            row.update({key: run[key] for key in (
                'status', 'recorded_trials', 'scored_trials', 'correct_trials', 'completed_blocks')})
            row['emotion_order'] = '|'.join(run['emotion_order'])
            if run['status'] == '完成':
                row['include_complete_run_summary'] = 1
            elif run['scored_trials'] == 0:
                row['reason'] = '没有计分试次'
            else:
                row['reason'] = '未形成三种情绪的完整运行汇总'
        writer.writerow(row)
    return output.getvalue()


def checksums_text(paths):
    paths = sorted([*paths, *(ROOT / '代码包').glob('*.zip')])
    return ''.join(f'{sha256(p.read_bytes()).hexdigest()}  {p.relative_to(ROOT).as_posix()}\n'
                   for p in paths)


def check_reference_run():
    """Use the archived R01 as a regression fixture without duplicating its ZIP."""
    path = DATA / 'V06' / '运行包' / 'V06-R01.zip'
    run = load(path)
    expected = dict(incomplete_blocks=0, blocks=18, scored=432, direction_blocks=12,
                    levels=9, **{'8/8/8': 18, '4/4': 12})
    assert dict(checks([run])) == expected, 'V06-R01 区块、词序或晋级复算变化'
    met = metrics(run['scored'])
    assert (met['right'], met['omitted'], met['hit'], met['fa']) == (355, 1, 111, 43), (
        'V06-R01 计分、漏答或信号检测口径变化')
    assert isclose(met['RT'], 935.2) and isclose(met['dp'], 1.76742033396348), (
        'V06-R01 正确反应时或辨别力口径变化')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true', help='更新已审核的索引和校验和')
    args = parser.parse_args()
    paths = archives()
    check_reference_run()
    for path, content in (
        (DATA / 'runs.csv', index_text(paths)),
        (ROOT / 'SHA256SUMS', checksums_text(paths)),
    ):
        if args.write:
            path.write_bytes(content.encode('utf-8'))
        elif not path.is_file() or path.read_bytes() != content.encode('utf-8'):
            raise SystemExit(f'归档与 {path.relative_to(ROOT)} 不一致，请核对变更来源。')
    print(f'已核对 {len(paths)} 份运行归档、代码包校验和和 V06-R01 回归样例。')


if __name__ == '__main__':
    main()
