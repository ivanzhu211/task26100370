# task26100370

## subbill：订阅账期折算库

纯进程内存的 Python 库（仅依赖标准库 `zoneinfo`），用于录入合同及有序变更、
计算指定连续账期的账单。

### 结构

- `subbill/types.py` — `Change`（改价/暂停/恢复/取消）与 `Bill` 数据类型
- `subbill/schedule.py` — 账期边界推算：日历月加法、月末截短、夏令时缺失/重复时刻解析
- `subbill/contract.py` — `Contract`：录入变更（UTC 生效时刻非递减）、按期出账
- `tests/` — 自动化测试（unittest，无第三方依赖）

### 用法

```python
from datetime import datetime, timezone
from subbill import Contract, Change, ChangeKind

c = Contract("America/New_York", datetime(2024, 1, 31, 10, 0, 0), 1, 1000)
c.add_change(Change(ChangeKind.PAUSE, datetime(2024, 2, 15, tzinfo=timezone.utc)))
c.add_change(Change(ChangeKind.RESUME, datetime(2024, 2, 20, tzinfo=timezone.utc)))

bill = c.bill(1)          # 第 2 期账单（None 表示不生成）
bills = c.bills(0, 6)     # 前 6 期全部账单
```

规则要点：

- 第 n 期边界 = 原始起订时刻 + n 倍账期月数；目标月无原始日号时取月末，锚点不变。
- 边界落在夏令时缺失区间按缺口向后平移；重复时刻取 UTC 较早的一次。
- 每期左闭右开；每段费用 = 当时每期价 × 该段 UTC 秒数 / 整期 UTC 秒数；
  同一期各段精确金额相加后四舍五入到分（半分向上）；暂停区段为零。
- 期中取消仍以原完整账期为分母；起点不早于取消时刻的账期不出账；
  整期暂停但未取消的账期保留零金额账单。

### 运行测试

```sh
python3 -m unittest discover -s tests -v
```
