# 权限、执行操作和退出码

以下是技术说明，不会在应用界面显示。

## Root 前置检查

模块会确认 `su` 执行后为 `uid=0`，并核对 `app.lawnchair` 的版本是否为 `15.0.0.7`。版本不同则拒绝执行，避免直接修改未知布局。

## 实际操作范围

| 操作 | 类型 |
| --- | --- |
| 搜索框控制 | `settings put global sahanaz_mumu_hide_search 1/0`，需要 Vector Hook 实际读取 |
| 广告组件控制 | `pm disable/enable --user 0`，仅控制 `AdBannerWidgetProvider` 与 `DailyDiscoveryWidgetProvider` |
| 长按菜单 | 对 `launcher_preferences.preferences_pb` 已存在的 `+widgets` / `-widgets` 项做**等长修改**，先备份 |
| 「小工具」Dock 文件夹 | 使用 SQLite 保存整行记录后事务移除/恢复 `_id=6` 和 `container=6` 的关联项 |
| 桌面刷新 | `am force-stop app.lawnchair` 后 `am start -n app.lawnchair/.LawnchairLauncher` |

### 文件夹目标位置

已在原设备核对的记录：

| 字段 | 值 |
| --- | --- |
| SQLite 数据库 | `/data/user/0/app.lawnchair/databases/launcher_4_7_6_1.db` |
| 表名 | `favorites` |
| `_id` | `6` |
| `title` | `小工具` |
| `itemType` | `2` |
| `container` | `-101` |
| `screen` | `5` |
| `cellX` | `5` |
| `cellY` | `0` |

**不可**将这些固定坐标当成适用所有模拟器实例的通用配置。恢复时检查 ID 和 Dock 位置是否与其他项目冲突，否则拒绝写入。

### 错误码摘要

| 范围 | 常见含义 |
| --- | --- |
| `40–42` | Root 未授权、Lawnchair 不存在或版本不匹配 |
| `51–53` | 广告组件或搜索框标记写入失败 |
| `61–67` | 长按菜单 DataStore 文件找不到、标记异常或无法写入 |
| `71–72` | Lawnchair 重新启动失败 |
| `81–100` | SQLite 数据库、备份、文件夹记录或 Dock 恢复位置校验失败 |
| `10–13` | 状态检查结果，属于非普通操作退出码 |

注意：Root 命令成功不等于用户界面的广告立刻消失。特别是 Vector Hook 可能还受框架启动时序、作用域和进程重启影响。
