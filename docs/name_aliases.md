# 名称输入与社区常用名映射

工作台把名称输入转换成版本目录中的稳定 ID。英雄输入同时接受：

- 当前补丁目录中的中文名、英文名和稳定 ID；
- `workbench/name_aliases.py` 中的社区常用名。

映射表是数据表而不是英雄专用决策算法。它只负责识别名称，识别后仍以所选补丁目录中的英雄资料为准。当前示例包括：

| 社区常用名 | 版本目录 ID | 标准中文名 |
| --- | --- | --- |
| 大头、大发明家 | Heimerdinger | 黑默丁格 |
| 剑魔、暗裔剑魔 | Aatrox | 亚托克斯 |
| 武器、武器大师 | Jax | 贾克斯 |
| 小法、维迦 | Veigar | 维迦 |
| 亚索 | Yasuo | 疾风剑豪 |
| 永恩 | Yone | 封魔剑魂 |
| 沙皇 | Azir | 沙漠皇帝 |

完整映射表位于 `workbench/name_aliases.py`，工作台也通过 `/api/name-aliases` 提供给前端。没有映射的名称仍可使用目录中的正式中文名、英文名或 ID；不建议把可能同时指向多个英雄的泛称加入映射。

装备输入不依赖这张英雄别名表。装备栏可输入锁定补丁目录中的中文名、英文名或 ID，后台保存稳定 ID，界面在已识别时显示中文名、英文名和 ID。名称无法唯一匹配时会保留错误提示，不会猜测装备。装备被识别只表示名称匹配成功；是否已经购买、数量和该时点是否生效，仍由用户在对应截图的状态快照中确认。

## English

The workbench resolves champion input to a stable ID. It accepts the patch catalog's localized names and IDs plus the community aliases in `workbench/name_aliases.py`. The alias table is a name-resolution table, not a champion-specific decision algorithm. Item fields accept the localized item name, English name, or item ID; the saved state uses the stable item ID and keeps the observed inventory/time confirmation separate.
