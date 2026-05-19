# AutoUnityTest

AutoUnityTest 是一个本地运行的 Unity 配置检测监控台。它可以监听多个 Git 项目，当命中文件规则时自动更新本地仓库、运行对应 Unity Editor 检测方法，并把结果汇总发送到飞书。

适合团队把“配置提交后自动检查”从 Jenkins 迁移到一台本地 Mac 或局域网共享机器上。

## 功能

- 多项目管理：每个项目可配置独立 Git 仓库、分支、监听规则、Unity 工程路径、检测方法和报告文件。
- Git 监听：支持监听远端分支，例如 `origin/dev`。
- 文件规则：支持多行 glob，例如 `LevelData/**/*.csv`、`Assets/**/*.asset`。
- Unity BatchMode 检测：自动生成临时 Editor Runner，按“规则检测 / 语言检测 / 图片检测”顺序执行。
- 飞书通知：检测结束后发送汇总卡片，标题颜色会根据检测结果显示成功或异常。
- 局域网共享：可配置只读账号和管理账号。
- 后台常驻：支持 macOS LaunchAgent，关闭终端和浏览器后仍可继续监听。

## 环境要求

- macOS
- Python 3.10 或更高版本
- Git
- Unity Hub / Unity Editor
- 本机 Git 已有目标仓库访问权限

> 本项目不包含任何私有项目配置、飞书 webhook、Git 账号密码或 Unity 工程文件。首次运行后会在本地生成配置文件，这些文件已被 `.gitignore` 排除。

## 快速开始

```bash
git clone https://github.com/Y-Fenix/AutoUnityTest.git
cd AutoUnityTest
chmod +x *.command
./本地运行.command
```

默认本机地址：

```text
http://127.0.0.1:9990/
```

打开页面后，点击“新增项目”，填写当前项目参数。

## 项目参数说明

常用字段：

- `项目名称`：显示在页面和飞书报告标题中。
- `Git 仓库路径`：要监听的本地 Git 仓库根目录。
- `远端名`：通常是 `origin`。留空时只监听本地分支。
- `分支`：例如 `dev`、`master`。
- `文件监听规则`：每行一个 glob。命中文件变更后才会触发检测。
- `Unity 工程路径`：包含 `Assets` 和 `ProjectSettings` 的 Unity 工程目录。
- `飞书 Webhook`：飞书机器人 webhook。不需要飞书时可留空。
- `规则检测方法 / 语言检测方法 / 图片检测方法`：Unity Editor 静态方法名。
- `报告文件`：检测方法生成的报告文件名。

检测方法需要是无参静态方法，例如：

```csharp
public static class MyLevelValidator
{
    public static void RunConfigCheck() {}
    public static void RunLanguageCheck() {}
    public static void RunImageCheck() {}
}
```

## 文件监听规则示例

```text
LevelData/**/*.csv
Assets/Resources/Config/Localization/*.asset
```

规则使用 Git changed files 的相对路径匹配。建议按项目固定配置，不要依赖自动猜测。

## 局域网共享

先复制示例用户文件：

```bash
cp examples/ui_users.example.json wordgroup_ui_users.json
```

修改 `wordgroup_ui_users.json` 中的用户名和密码，然后运行：

```bash
./局域网运行.command
```

脚本会提示输入端口，并输出局域网访问地址。

## 后台服务

本地运行和局域网运行都会通过 macOS LaunchAgent 启动后台服务。

查看状态：

```bash
./查看后台服务状态.command
```

停止服务：

```bash
./停止后台服务.command
```

## 示例配置

`examples/projects.example.json` 是脱敏示例。你可以参考里面的字段在页面中填写，或复制为 `wordgroup_projects.json` 后自行修改。

注意：`wordgroup_projects.json` 可能包含本地路径和飞书 webhook，不要提交到公开仓库。

## 安全说明

以下文件默认不会提交：

- `wordgroup_projects.json`
- `wordgroup_ui_users.json`
- `wordgroup_monitor_store.json`
- `wordgroup_monitor_states/`
- `*.log`
- Unity `Result/`、`Library/`、`Temp/`

如果你准备二次发布，请先运行：

```bash
rg -n "open-apis|hook/|password|token|/Users/|pt-" .
```

确认没有私密数据后再推送。

## 常见问题

### 点击“立即检查”没有运行 Unity

先确认：

- Unity 工程路径是否正确。
- Unity 工程没有编译错误。
- 检测方法名是否存在并可被 Unity Editor 编译。
- 报告文件名是否和检测方法实际生成的文件一致。

### Unity 版本不完全一致怎么办

工具会优先查找项目声明的 Unity 版本。如果找不到精确版本，会在同一 Unity 大版本系列内回退，例如 `2022.3.x`。

### GitHub 包下载失败

如果 Unity Package Manager 依赖 GitHub 包，而本机无法访问 GitHub，Unity BatchMode 会在包解析阶段失败。建议将这些包改成本地包或内网可访问源。

## License

MIT

