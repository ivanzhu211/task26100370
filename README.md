# task26100370

订阅账期折算库（纯进程内存，无外部服务，仅依赖 Python 3.9+ 标准库）。

## 结构

- `subbill/contract.py` — 数据类型：`Contract`（IANA 时区、本地起订时刻、账期月数 1/3/12、初始每期价/分）、`Change`（改价/暂停/恢复/取消，UTC 生效时刻非递减录入）。
- `subbill/billing.py` — `period_boundary_utc(contract, n)` 由原始锚点直接推算第 n 期边界（目标月无原始日号取月末，锚点不变；本地时分秒保持；DST 缺失时刻按缺口向后平移，重复时刻取较早 UTC）；`bill_periods(contract, from_index, to_index)` 生成 `[from_index, to_index)` 各期账单，期内按变更切分段，每段 `当时每期价 * 段实际UTC秒数 / 整期实际UTC秒数`，暂停/取消段为零，期内精确求和后半分向上取整到分。

## 运行测试

```sh
python3 -m unittest discover -s tests -v
```

## 用法示例

```python
from datetime import datetime, timezone
from subbill import Contract, Change, ChangeKind, bill_periods

c = Contract("America/New_York", datetime(2024, 1, 31, 9, 0), 1, 1000)
c.add_change(Change(datetime(2024, 2, 15, tzinfo=timezone.utc), ChangeKind.SET_PRICE, 1200))
c.add_change(Change(datetime(2024, 3, 1, tzinfo=timezone.utc), ChangeKind.PAUSE))
c.add_change(Change(datetime(2024, 3, 10, tzinfo=timezone.utc), ChangeKind.RESUME))
for bill in bill_periods(c, 0, 4):
    print(bill.period_index, bill.start_utc, bill.end_utc, bill.amount_cents)
```
