# 从源码构建

## 准备

- Python 3.10 或更新版本
- JDK（需要 `java`、`keytool`、`jarsigner`）
- **不需要** Android SDK 或 Gradle

所有源代码均为可直接执行的 Python 生成器：

- `src/ui_builder.py`：生成 Root 管理界面 DEX；
- `src/hook_builder.py`：生成传统 Xposed Hook DEX；
- `src/assemble.py`：合并 DEX、生成 AndroidManifest、签名 APK。

## 本地开发构建

在仓库根目录运行：

```powershell
python build.py
```

成功后生成：

`dist/MuMu-Desktop-Cleaner-v1.0.apk`

第一次构建会自动创建本地 **开发签名** 文件。`.gitignore` 已排除签名密钥及编译中间产物；不要手动把密钥上传到 GitHub。

## 使用已有签名构建升级版本

如需生成与此前 APK 可覆盖安装的升级包，必须持有原始签名密钥，并在构建前设置这些环境变量：

- `MUMU_SIGN_KEYSTORE`：本地私钥库的绝对路径。
- `MUMU_SIGN_STOREPASS`：私钥库密码。
- `MUMU_SIGN_KEYPASS`：签名条目密码（默认与库密码相同）。
- `MUMU_SIGN_ALIAS`：签名别名，之前的项目默认 `vectorcleaner`。

请在你自己的开发环境私密配置；**不要将真实密码写进公开脚本、日志或仓库**。

源码默认的本地开发证书仅用于测试。使用不同证书签名时，Android 通常拒绝直接覆盖已安装版本。请保留正式发布证书并离线备份。

## 版本号

本次公开发布：

- 用户可见版本：`1.0`
- Android `versionName`：`1.0`
- Android `versionCode`：`5`（高于之前内部测试版的 4）

以后更新，请同时修改 `src/assemble.py` 的 `versionCode` / `versionName` 和 `src/ui_builder.py` 中的显示版本，然后重新构建和测试。

## 验证

```powershell
python tests/check_apk.py dist/MuMu-Desktop-Cleaner-v1.0.apk
```

如果有 JDK，可额外执行：

```powershell
jarsigner -verify dist/MuMu-Desktop-Cleaner-v1.0.apk
```

这些检查只能证明 APK 结构/签名格式正常，不能替代 MuMu 实机安装、Root、Hook 和恢复验收。
