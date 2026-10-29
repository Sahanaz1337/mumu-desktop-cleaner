# MuMu Desktop Cleaner

**MuMu 安卓模拟器桌面净化工具** · 正式版本 **v1.0**

针对 **MuMu Android 15 / 定制 Lawnchair 15.0.0.7** 的桌面清理模块，支持 **Vector 2.2 (API 102) / LSPosed 兼容的传统 Xposed Hook** 与 **KernelSU Root**。

该项目只针对已确认的 MuMu 系统组件，不会替换原始 Lawnchair APK，也不会卸载任何应用。

> [!IMPORTANT]
> 这是基于特定 MuMu Android 15 环境开发和验收的工具，不保证适用于其他模拟器、不同 Lawnchair 构建或未来更新。执行涉及桌面数据库的操作前，请先克隆/备份模拟器实例。

## 功能

| 功能 | 实现方式 |
| --- | --- |
| 隐藏顶部游戏推广搜索框 | 作用域仅为 `app.lawnchair` 的 Xposed Hook，配合 Root 全局开关 |
| 关闭左侧推广卡片 | 停用指定 `AdBannerWidgetProvider` 组件 |
| 关闭「每日新发现」 | 停用指定 `DailyDiscoveryWidgetProvider` 组件 |
| 隐藏长按菜单中的「微件」 | 定长切换 Lawnchair DataStore 菜单配置 |
| 移除 Dock 中的「小工具」文件夹 | SQLite 事务保存记录并从桌面布局中移除，**不卸载**内部应用 |
| 分项恢复、一键恢复、状态检查 | 应用内操作按钮；恢复需满足原位置未被占用等条件 |
| 重新加载桌面 | 结束并启动 Lawnchair 进程，不清除应用数据 |

## 发布版本说明

**v1.0** 是对此前测试构建 V1.2 的正式版本命名。安装包的 Android `versionCode` 为 **5**，因此可以覆盖 `versionCode=4` 的先前安装包（前提是签名证书一致）。

- 界面显示：**MuMu 桌面净化 V1.0**。
- 初始提示：**准备就绪**。
- 操作成功：**执行成功。请返回桌面查看效果。**
- 执行失败：显示简洁错误码，详细实现见 [`docs/COMMANDS.md`](docs/COMMANDS.md)。
- 界面中已删除以前显示的长篇底层命令摘要。

## 环境要求

- MuMu Android 15（测试设备：`model: 2206123SC`）
- 定制系统桌面：`app.lawnchair` / `versionName=15.0.0.7`
- 已授予 Root 权限的 KernelSU
- Vector 2.2 / 可兼容传统 Xposed API 的框架
- Vector 模块作用域：**仅 `app.lawnchair`**，无需勾选「系统框架」

## 安装

1. 建议先通过 MuMu 多开器克隆当前实例。
2. 从本仓库右侧 **Releases** 页面下载 `MuMu-Desktop-Cleaner-v1.0.apk`，直接安装。若先前版本使用相同签名，可覆盖升级。
3. 打开 Vector → 模块 → **MuMu 桌面净化 V1.0**，启用模块，只勾选 **Lawnchair (`app.lawnchair`)**。
4. 重启 MuMu；打开「MuMu 桌面净化 V1.0」。
5. 在 KernelSU 中允许该应用获取 Root，按需使用“一键净化”或分项操作。
6. 返回桌面检查实际效果。

Windows CMD 安装命令（请根据实际路径修改 APK 文件位置）：

```cmd
"D:\Program Files\Netease\MuMu\nx_main\adb.exe" install -r "%USERPROFILE%\Downloads\MuMu-Desktop-Cleaner-v1.0.apk"
```

> 如果 Android 返回 `INSTALL_FAILED_UPDATE_INCOMPATIBLE`，表示签名证书不一致。**不要为了升级直接清除 Lawnchair 数据或卸载系统桌面**；请核对旧模块的包名、签名和升级来源。

## 使用及恢复

- **一键净化**：搜索框、两个广告组件、长按菜单微件入口、`小工具` Dock 文件夹。
- **分项操作**：仅控制单一功能，适合排查问题。
- **一键恢复**：尝试恢复所有配置；若 Dock 原位置已被其他图标占用，会拒绝覆盖现有布局并返回错误码。
- **状态检查**：检查已知配置标记，**不等同于实际截图或 Hook 生效证明**。

### 文件夹备份

针对已确认的 Dock 文件夹，移除前会保存 SQLite 记录和数据库快照（位置在 Lawnchair 应用私有数据目录）：

- `/data/user/0/app.lawnchair/files/sahanaz_tools_v12_rows.db`
- `/data/user/0/app.lawnchair/files/sahanaz_tools_v12_before.db`

这两个文件名为了兼容既有备份，**在公开 v1.0 中仍沿用 `v12` 后缀**。请勿手动删除或重命名。**清除 Lawnchair 数据或重置模拟器会使这些备份丢失。**

注意：恢复广告组件并不保证此前已移除的广告卡片被自动加回桌面。恢复文件夹也要求原文件夹 ID、Dock 位置等没有冲突。

## 开发与源码

本项目采用 **Python 3 的离线 DEX / AndroidManifest 构建脚本**，不是 Gradle/Android Studio Java 工程；不包含 MuMu、Lawnchair、Vector 或 KernelSU 的第三方二进制文件。

源码位于 [`src/`](src/)，构建说明见 [`docs/BUILD.md`](docs/BUILD.md)，具体设备操作及退出码见 [`docs/COMMANDS.md`](docs/COMMANDS.md)。

**签名私钥不在源码仓库内。** 本地源码构建默认使用新生成的开发证书，不能直接覆盖已发布的 APK；发布升级必须继续使用同一个私有签名证书。不要向 GitHub 提交 `*.jks`、`*.keystore` 或包含密码的构建配置。

## 安全与兼容性

- 模块仅 Hook 已知的 `app.lawnchair`；不要在作用域里额外选择其他应用。
- Root 命令仅面向已识别的 MuMu 广告组件、Lawnchair 菜单配置和**精确定位的** `_id=6` / `小工具` / Dock 坐标。其他布局必须重新审查，不能沿用这些固定 ID。
- 修改之前建议保存模拟器快照。UI 的“执行成功”表示命令成功结束，不代表每一项视觉效果已在当前设备自动验收。
- 如果出现桌面异常，可在 Vector 停用本模块并重启；如已修改布局，仍需使用模块内的恢复功能或先前保存的数据库快照。

## 仓库定位

**MuMu Desktop Cleaner — Android 15 Desktop Cleanup Module**

这是针对 MuMu 定制 Lawnchair 的社区工具，与 MuMu 官方、Vector、Lawnchair 和 KernelSU 项目无隶属关系。

> 本仓库目前未指定开源许可证。公开上传代码不等于自动授予第三方复制、修改和再发布许可；如需正式开源，请在发布时选择适合的 `LICENSE`。
